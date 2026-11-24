"""Modo online (Vercel): nada fica no disco do servidor, tudo vai para o Supabase.

Ligado com PONTOCERTO_NUVEM=1. Na Vercel cada pedido pode cair numa máquina
diferente e o disco é apagado, então:
  - histórico das peças, sessões de login e tentativas de senha ficam em
    tabelas `pc_*` do Postgres do Supabase;
  - ajustes, lote ativo e gasto da IA ficam em `pc_config`;
  - fotos das peças ficam no Storage (bucket SUPABASE_BUCKET, pasta capturas/).

Para mexer pouco no resto do sistema, `ConexaoPostgres` aceita os mesmos
comandos SQLite que o código já usa (com `?`, INSERT OR REPLACE, PRAGMA...) e
os traduz para Postgres.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

PASTA_TEMP = Path(tempfile.gettempdir()) / "pontocerto"


def ativo() -> bool:
    return os.environ.get("PONTOCERTO_NUVEM", "").strip().lower() in ("1", "true", "sim", "yes")


DDL = """
create table if not exists public.pc_eventos (
    id text primary key, "timestamp" double precision not null, data text not null, payload text not null);
create index if not exists pc_eventos_data on public.pc_eventos (data);
create index if not exists pc_eventos_ts on public.pc_eventos ("timestamp");
create table if not exists public.pc_sessoes (token text primary key, email text, expires double precision);
create table if not exists public.pc_tentativas (ip text primary key, count integer, until double precision);
create table if not exists public.pc_config (chave text primary key, valor jsonb, atualizado_em timestamptz default now());
alter table public.pc_eventos enable row level security;
alter table public.pc_sessoes enable row level security;
alter table public.pc_tentativas enable row level security;
alter table public.pc_config enable row level security;
revoke all on public.pc_eventos, public.pc_sessoes, public.pc_tentativas, public.pc_config from anon, authenticated;
"""

TABELAS = {"eventos": "pc_eventos", "sessions": "pc_sessoes", "attempts": "pc_tentativas"}
SUBSTITUIR = {
    "pc_eventos": ' on conflict (id) do update set "timestamp"=excluded."timestamp", data=excluded.data, payload=excluded.payload',
    "pc_tentativas": " on conflict (ip) do update set count=excluded.count, until=excluded.until",
    "pc_sessoes": " on conflict (token) do update set email=excluded.email, expires=excluded.expires",
}


class _CursorVazio:
    rowcount = 0

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())


class ConexaoPostgres:
    """Uma conexão por processo, reaberta se cair. Aceita SQL no dialeto do SQLite."""

    _trava = threading.RLock()
    _conexao = None
    _pronto = False

    def __init__(self, db_url: str):
        self.db_url = db_url

    def _abrir(self):
        import psycopg
        cls = type(self)
        if cls._conexao is None or cls._conexao.closed:
            cls._conexao = psycopg.connect(self.db_url, autocommit=True, prepare_threshold=None, connect_timeout=10)
            if not cls._pronto:
                cls._conexao.execute(DDL)
                cls._pronto = True
        return cls._conexao

    @staticmethod
    def traduzir(sql: str) -> str | None:
        texto = sql.strip().rstrip(";")
        topo = texto.upper()
        if topo.startswith(("CREATE TABLE", "PRAGMA", "ALTER TABLE", "BEGIN")):
            return None  # as tabelas já existem (DDL acima); o resto é coisa do SQLite
        for velho, novo in TABELAS.items():
            texto = re.sub(rf"\b{velho}\b", novo, texto)
        if topo.startswith("INSERT OR REPLACE INTO"):
            texto = "INSERT INTO" + texto[len("INSERT OR REPLACE INTO"):]
            tabela = texto.split()[2]
            texto += SUBSTITUIR.get(tabela, "")
        texto = re.sub(r'(?<!")\btimestamp\b(?!")', '"timestamp"', texto)
        return texto.replace("?", "%s")

    def execute(self, sql: str, params: Any = ()):
        texto = self.traduzir(sql)
        if texto is None:
            return _CursorVazio()
        import psycopg
        with self._trava:
            for tentativa in (1, 2):
                try:
                    return self._abrir().execute(texto, tuple(params or ()))
                except psycopg.OperationalError:
                    type(self)._conexao = None
                    if tentativa == 2:
                        raise

    def executescript(self, script: str):
        for parte in script.split(";"):
            if parte.strip():
                self.execute(parte)

    # O código usa "with conexao:" como no SQLite; aqui cada comando já é gravado na hora.
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


@contextmanager
def conexao():
    from pontocerto.config import credenciais_supabase
    url = (credenciais_supabase().get("db_url") or "").strip()
    if not url:
        raise RuntimeError("Modo online sem SUPABASE_DB_URL.")
    yield ConexaoPostgres(url)


# ------------------------------------------------------------------ config
_cache: dict[str, tuple[float, Any]] = {}


def ler(chave: str, padrao: Any = None, cache_s: float = 3.0) -> Any:
    guardado = _cache.get(chave)
    if guardado and time.time() - guardado[0] < cache_s:
        return guardado[1]
    with conexao() as db:
        linha = db.execute("select valor from public.pc_config where chave = ?", (chave,)).fetchone()
    valor = linha[0] if linha else padrao
    _cache[chave] = (time.time(), valor)
    return valor


def gravar(chave: str, valor: Any) -> None:
    with conexao() as db:
        db.execute("insert into public.pc_config (chave, valor, atualizado_em) values (?, ?::jsonb, now()) "
                   "on conflict (chave) do update set valor = excluded.valor, atualizado_em = now()",
                   (chave, json.dumps(valor)))
    _cache[chave] = (time.time(), valor)


def somar_uso_ia(dia: str, custo: float) -> dict:
    """Conta uma leitura por IA no dia, sem perder contagem entre máquinas."""
    with conexao() as db:
        linha = db.execute(
            "insert into public.pc_config (chave, valor) values ('uso_ia', "
            "jsonb_build_object('data', ?::text, 'chamadas', 1, 'custo_usd', ?::float8)) "
            "on conflict (chave) do update set atualizado_em = now(), valor = case "
            "when pc_config.valor->>'data' = ?::text then jsonb_build_object('data', ?::text, "
            "'chamadas', (pc_config.valor->>'chamadas')::int + 1, "
            "'custo_usd', (pc_config.valor->>'custo_usd')::float8 + ?::float8) "
            "else jsonb_build_object('data', ?::text, 'chamadas', 1, 'custo_usd', ?::float8) end "
            "returning valor", (dia, custo, dia, dia, custo, dia, custo)).fetchone()
    _cache.pop("uso_ia", None)
    return linha[0]


def corrigir_datas_fuso() -> int:
    """Recalcula o dia (coluna `data`) das peças no horário de Brasília. Roda uma vez só.

    Até 25/11/2026 o servidor online gravava o dia em UTC: peças depois das 21h
    caíam no dia seguinte. O instante de cada peça (`timestamp`) está certo e não
    muda; só o dia usado nos filtros é refeito a partir dele.
    """
    if ler("fuso_datas", None, cache_s=0) == "-03":
        return 0
    with conexao() as db:
        cur = db.execute(
            "update public.pc_eventos set data = to_char((to_timestamp(\"timestamp\") at time zone 'UTC') "
            "- interval '3 hours', 'YYYY-MM-DD') where data <> to_char((to_timestamp(\"timestamp\") "
            "at time zone 'UTC') - interval '3 hours', 'YYYY-MM-DD')")
        n = cur.rowcount or 0
    gravar("fuso_datas", "-03")
    return n


# ------------------------------------------------------------------ fotos
def _storage():
    from pontocerto.config import credenciais_supabase
    c = credenciais_supabase()
    url, chave, bucket = (c.get("url") or "").rstrip("/"), (c.get("secret_key") or "").strip(), (c.get("bucket") or "").strip()
    if not (url and chave and bucket):
        raise RuntimeError("Modo online sem SUPABASE_URL, SUPABASE_SECRET_KEY ou SUPABASE_BUCKET.")
    return f"{url}/storage/v1/object", bucket, {"apikey": chave, "Authorization": f"Bearer {chave}"}


def enviar_foto(nome: str, dados: bytes) -> None:
    import httpx
    base, bucket, cab = _storage()
    r = httpx.post(f"{base}/{bucket}/capturas/{nome}", content=dados, timeout=20,
                   headers={**cab, "Content-Type": "image/jpeg", "x-upsert": "true"})
    r.raise_for_status()


def baixar_foto(nome: str) -> bytes | None:
    import httpx
    base, bucket, cab = _storage()
    r = httpx.get(f"{base}/authenticated/{bucket}/capturas/{nome}", headers=cab, timeout=20)
    return r.content if r.status_code == 200 else None


def apagar_foto(nome: str) -> None:
    import httpx
    base, bucket, cab = _storage()
    httpx.request("DELETE", f"{base}/{bucket}", headers=cab, json={"prefixes": [f"capturas/{nome}"]}, timeout=20)
