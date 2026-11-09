"""Acesso ao Supabase (PostgreSQL + Storage) do Ponto Certo.

Mesma filosofia do cliente do OpenRouter: o sistema funciona SEM banco. Este
modulo nunca estoura na subida do servidor. Sem as variaveis no .env, ou sem
internet, o objeto `BancoSupabase` nasce com `disponivel == False` e `erro`
preenchido, e quem chama decide o que fazer (a interface mostra "Banco
desconectado").

Decisoes importantes:

  - O banco e acessado direto pelo PostgreSQL (psycopg + pool), conectando como
    o dono das tabelas. O RLS esta ligado e sem policies de proposito: a API REST
    publica do Supabase NAO e usada para as tabelas.
  - O Storage (fotos das inspecoes) e acessado por HTTP com a chave secreta,
    porque o PostgreSQL nao guarda arquivos.
  - O pool e preguicoso: nenhuma conexao e aberta ate a primeira consulta, e
    nenhuma conexao fica sendo refeita em segundo plano quando a internet cai.
  - Credenciais (connection string, senha, chave secreta) nunca sao impressas,
    logadas nem devolvidas em mensagem de erro: tudo passa por `mascarar`.
  - `classe_final` e `aprovada` sao colunas geradas pelo banco: este modulo
    nunca escreve nelas.

Este modulo NAO roda na thread de inferencia. Quem grava inspecoes a partir de
eventos ao vivo deve fazer isso por uma fila com thread propria.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote, urlsplit

from pontocerto.config import credenciais_supabase
from pontocerto.labels import CLASS_KEYS

try:  # dependencias opcionais: sem elas o sistema segue sem banco
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from psycopg_pool import ConnectionPool

    _ERRO_IMPORT: str | None = None
except Exception as _exc:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]
    _ERRO_IMPORT = (
        f"pacote do PostgreSQL nao instalado ({type(_exc).__name__}): "
        "rode pip install -r requirements.txt"
    )

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

# O pool registra um WARNING a cada tentativa de conexao que falha. Sem internet
# isso inunda o terminal; o motivo real ja chega por `erro` / /api/db/status.
logging.getLogger("psycopg.pool").setLevel(logging.ERROR)

# Mensagens do driver/Storage -> explicacao em portugues para a interface.
_TRADUCOES = (
    ("password authentication failed", "senha do banco recusada - confira a SUPABASE_DB_URL no .env"),
    ("failed to resolve host", "endereco do banco nao encontrado - sem internet ou host errado na SUPABASE_DB_URL"),
    ("getaddrinfo failed", "endereco do banco nao encontrado - sem internet ou host errado na SUPABASE_DB_URL"),
    ("Tenant or user not found", "usuario/projeto nao encontrado no pooler - confira a SUPABASE_DB_URL"),
    ("timeout expired", "o banco nao respondeu a tempo - internet lenta ou fora do ar"),
    ("couldn't get a connection", "o banco nao respondeu a tempo - internet lenta ou fora do ar"),
    ("Connection refused", "conexao recusada pelo servidor do banco"),
    ("server closed the connection", "a conexao com o banco caiu"),
    ("Invalid Compact JWS", "chave SUPABASE_SECRET_KEY recusada pelo Storage"),
    ("Bucket not found", "bucket nao existe no Storage - confira SUPABASE_BUCKET (maiusculas contam)"),
)


STATUS_LOTE = ("aberto", "em_inspecao", "concluido")
ORIGENS = ("ao_vivo", "upload")
# Colunas de `inspecoes` que o app pode atualizar depois de criada a linha.
_COLUNAS_ATUALIZAVEIS = ("classe_confirmada", "diagnostico", "revisao_llm", "imagem_path")
_COLUNAS_JSON = ("diagnostico", "revisao_llm")

_RE_URL_POSTGRES = re.compile(r"postgres(?:ql)?://[^\s'\"<>]+", re.IGNORECASE)
_RE_CHAVE_SECRETA = re.compile(r"sb_secret_[A-Za-z0-9_\-]+")
_RE_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")


class ErroBanco(RuntimeError):
    """Falha de banco ou Storage com mensagem ja mascarada (pode ir para a tela)."""


def _cfg_banco(cfg: Any) -> dict:
    try:
        return dict(cfg["banco"] or {})
    except Exception:
        return {}


def _jsonavel(valor: Any) -> Any:
    """Converte Decimal/data/hora em tipos que o JSON da API entende."""
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: _jsonavel(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_jsonavel(v) for v in valor]
    return valor


def _linhas(cursor) -> list[dict]:
    return [_jsonavel(dict(r)) for r in cursor.fetchall()]


class BancoSupabase:
    """Pool de conexoes + funcoes de acesso as tabelas e ao Storage."""

    def __init__(self, cfg: Any = None, credenciais: dict | None = None) -> None:
        self._cfg = _cfg_banco(cfg) if cfg is not None else {}
        cred = credenciais if credenciais is not None else credenciais_supabase()
        self._db_url: str | None = (cred.get("db_url") or "").strip() or None
        self._url: str | None = (cred.get("url") or "").strip().rstrip("/") or None
        self._chave: str | None = (cred.get("secret_key") or "").strip() or None
        self._bucket: str | None = (cred.get("bucket") or "").strip() or None

        self._ativo = bool(self._cfg.get("ativo", True))
        self._timeout_conexao = float(self._cfg.get("timeout_conexao_s", 6))
        self._timeout_storage = float(self._cfg.get("timeout_storage_s", 20))
        self._intervalo_status = float(self._cfg.get("intervalo_status_s", 15))
        self._pool_max = max(1, int(self._cfg.get("pool_max", 4)))
        self._arquivo_pendentes = self._cfg.get("pendentes")

        self._segredos = self._coletar_segredos()
        self._trava = threading.RLock()          # criacao/fechamento do pool
        self._trava_status = threading.Lock()    # so o cache de status
        self._pool = None
        self._disponivel = False
        self._erro: str | None = None
        self._ultimo_teste = 0.0
        self._status_cache: dict | None = None

        if not self._ativo:
            self._erro = "banco desligado no config.yaml (banco.ativo: false)"
        elif _ERRO_IMPORT:
            self._erro = _ERRO_IMPORT
        elif not self._db_url:
            self._erro = "SUPABASE_DB_URL nao definida no .env - o sistema segue sem banco"
        elif not self._db_url.lower().startswith(("postgres://", "postgresql://")):
            self._erro = "SUPABASE_DB_URL nao parece uma connection string do PostgreSQL"
            self._db_url = None

    # ------------------------------------------------------------ segredos
    def _coletar_segredos(self) -> list[str]:
        segredos: list[str] = []
        if self._db_url:
            segredos.append(self._db_url)
            try:
                senha = urlsplit(self._db_url).password
            except Exception:
                senha = None
            if senha:
                segredos.append(senha)
                segredos.append(unquote(senha))
                segredos.append(quote(senha, safe=""))
        if self._chave:
            segredos.append(self._chave)
        # mais longos primeiro, para nao sobrar pedaco de um segredo maior
        return sorted({s for s in segredos if s and len(s) >= 4}, key=len, reverse=True)

    def mascarar(self, texto: Any) -> str:
        """Remove credenciais de qualquer texto antes de ele circular."""
        texto = str(texto or "")
        for segredo in self._segredos:
            texto = texto.replace(segredo, "***")
        texto = _RE_URL_POSTGRES.sub("postgresql://***", texto)
        texto = _RE_CHAVE_SECRETA.sub("***", texto)
        return _RE_JWT.sub("***", texto)

    def _explicar(self, texto: str) -> str:
        """Mascara e, se for um erro conhecido, troca pela explicacao em portugues."""
        texto = " ".join(self.mascarar(texto).split())
        for trecho, explicacao in _TRADUCOES:
            if trecho.lower() in texto.lower():
                return explicacao
        return texto[:300]

    def _erro_de(self, exc: BaseException, contexto: str) -> ErroBanco:
        detalhe = self._explicar(str(exc) or exc.__class__.__name__)
        return ErroBanco(f"{contexto}: {detalhe}" if detalhe else contexto)

    # ---------------------------------------------------------- propriedades
    @property
    def configurado(self) -> bool:
        """True quando ha connection string valida e o banco esta ligado."""
        return bool(self._ativo and self._db_url and _ERRO_IMPORT is None)

    @property
    def storage_configurado(self) -> bool:
        return bool(self.configurado and self._url and self._chave and self._bucket and httpx)

    @property
    def disponivel(self) -> bool:
        """True se o ultimo contato com o banco deu certo."""
        return self._disponivel

    @property
    def erro(self) -> str | None:
        return self._erro

    @property
    def bucket(self) -> str | None:
        return self._bucket

    # ----------------------------------------------------------------- pool
    def _obter_pool(self):
        if not self.configurado:
            raise ErroBanco(self._erro or "banco nao configurado")
        with self._trava:
            if self._pool is None:
                self._pool = ConnectionPool(
                    self._db_url,
                    min_size=0,  # nada de reconexao em segundo plano sem internet
                    max_size=self._pool_max,
                    max_idle=300,
                    timeout=self._timeout_conexao,
                    # sem internet, desiste de crescer o pool logo (padrao: 5 min)
                    reconnect_timeout=self._timeout_conexao * 3,
                    check=ConnectionPool.check_connection,  # descarta conexao morta
                    kwargs={
                        "connect_timeout": max(1, int(self._timeout_conexao)),
                        "application_name": "ponto-certo",
                        "row_factory": dict_row,
                        # compatibilidade com o pooler do Supabase
                        "prepare_threshold": None,
                    },
                    open=False,
                    name="ponto-certo",
                )
                self._pool.open(wait=False)
            return self._pool

    def _executar(self, sql: str, params: Iterable | dict | None = None, *,
                  contexto: str, buscar: str = "todas") -> Any:
        """Roda uma consulta numa conexao do pool, com commit e erro mascarado."""
        try:
            pool = self._obter_pool()
            with pool.connection() as conexao:
                with conexao.cursor() as cur:
                    cur.execute(sql, params)
                    if buscar == "todas":
                        resultado = _linhas(cur)
                    elif buscar == "uma":
                        linha = cur.fetchone()
                        resultado = _jsonavel(dict(linha)) if linha else None
                    else:
                        resultado = cur.rowcount
            self._marcar_ok()
            return resultado
        except ErroBanco:
            raise
        except Exception as exc:
            erro = self._erro_de(exc, contexto)
            if self._e_falha_de_conexao(exc):
                self._marcar_falha(str(erro))
            raise erro from None

    @staticmethod
    def _e_falha_de_conexao(exc: BaseException) -> bool:
        if psycopg is None:
            return True
        nome = type(exc).__name__
        return isinstance(exc, psycopg.OperationalError) or nome in ("PoolTimeout", "TooManyRequests")

    def _marcar_ok(self) -> None:
        self._disponivel = True
        self._erro = None

    def _marcar_falha(self, mensagem: str) -> None:
        self._disponivel = False
        self._erro = mensagem
        self._status_cache = None

    def fechar(self) -> None:
        with self._trava:
            if self._pool is not None:
                try:
                    self._pool.close(timeout=2)
                except Exception:
                    pass
                self._pool = None

    # --------------------------------------------------------------- status
    def testar(self) -> bool:
        """Faz um `select 1` de verdade e atualiza `disponivel` / `erro`."""
        if not self.configurado:
            self._disponivel = False
            return False
        if self._disponivel:  # pool provavelmente tem conexao viva: caminho rapido
            try:
                self._executar("select 1 as ok", contexto="sem conexao com o banco", buscar="uma")
                return True
            except ErroBanco:
                pass
        # O pool so diz "nao consegui conexao a tempo". Uma tentativa direta,
        # unica e curta, revela o motivo real (senha, DNS, timeout...).
        try:
            with psycopg.connect(self._db_url, connect_timeout=max(1, int(self._timeout_conexao)),
                                 prepare_threshold=None) as conexao:
                conexao.execute("select 1")
            self._marcar_ok()  # voltou entre uma tentativa e outra
            return True
        except Exception as exc:
            self._marcar_falha(str(self._erro_de(exc, "sem conexao com o banco")))
            return False

    def contar_pendentes(self) -> int:
        """Quantas gravacoes esperam reenvio no arquivo local de pendencias."""
        if not self._arquivo_pendentes:
            return 0
        caminho = Path(self._arquivo_pendentes)
        if not caminho.exists():
            return 0
        try:
            with open(caminho, "r", encoding="utf-8") as fh:
                return sum(1 for linha in fh if linha.strip())
        except Exception:
            return 0

    def status(self, forcar: bool = False, pendentes: int | None = None) -> dict:
        """Estado do banco para a interface. O teste real fica em cache por alguns segundos."""
        agora = time.time()
        with self._trava_status:
            cache_valido = (
                self._status_cache is not None
                and not forcar
                and agora - self._ultimo_teste < self._intervalo_status
            )
            if not cache_valido:
                inicio = time.perf_counter()
                conectado = self.testar()
                latencia = round((time.perf_counter() - inicio) * 1000, 1) if conectado else None
                storage = self.checar_storage() if conectado else {
                    "configurado": self.storage_configurado,
                    "ok": False,
                    "bucket": self._bucket,
                    "erro": None if not self.storage_configurado else "banco desconectado",
                }
                self._ultimo_teste = agora
                self._status_cache = {
                    "configurado": self.configurado,
                    "conectado": conectado,
                    "erro": None if conectado else self._erro,
                    "latencia_ms": latencia,
                    "storage": storage,
                    "verificado_em": datetime.now().isoformat(timespec="seconds"),
                }
            resultado = dict(self._status_cache)
        resultado["pendentes"] = self.contar_pendentes() if pendentes is None else int(pendentes)
        return resultado

    # ------------------------------------------------------------- clientes
    def listar_clientes(self) -> list[dict]:
        return self._executar(
            "select id, nome, cnpj, criado_em from public.clientes order by nome",
            contexto="falha ao listar clientes",
        )

    def criar_cliente(self, nome: str, cnpj: str | None = None) -> dict:
        nome = (nome or "").strip()
        if not nome:
            raise ErroBanco("o nome do cliente e obrigatorio")
        cnpj = (cnpj or "").strip() or None
        return self._executar(
            "insert into public.clientes (nome, cnpj) values (%s, %s) "
            "returning id, nome, cnpj, criado_em",
            (nome, cnpj), contexto="falha ao cadastrar cliente", buscar="uma",
        )

    # ---------------------------------------------------------------- lotes
    def listar_lotes(self) -> list[dict]:
        """Lotes com os numeros da view `resumo_lotes`, mais recentes primeiro."""
        return self._executar(
            "select r.*, l.cliente_id, l.observacoes, l.criado_em "
            "from public.resumo_lotes r join public.lotes l on l.id = r.id "
            "order by l.criado_em desc",
            contexto="falha ao listar lotes",
        )

    def obter_lote(self, lote_id: int) -> dict | None:
        return self._executar(
            "select r.*, l.cliente_id, l.observacoes, l.criado_em "
            "from public.resumo_lotes r join public.lotes l on l.id = r.id "
            "where r.id = %s",
            (int(lote_id),), contexto="falha ao ler o lote", buscar="uma",
        )

    def criar_lote(self, dados: dict) -> dict:
        """Cadastra um lote. Campos: cliente_id, codigo, modelo_peca, quantidade,
        prazo_entrega (AAAA-MM-DD) obrigatorios; tecido, limite_defeito, observacoes opcionais."""
        faltando = [c for c in ("cliente_id", "codigo", "modelo_peca", "quantidade", "prazo_entrega")
                    if dados.get(c) in (None, "")]
        if faltando:
            raise ErroBanco("campos obrigatorios ausentes: " + ", ".join(faltando))
        try:
            quantidade = int(dados["quantidade"])
            cliente_id = int(dados["cliente_id"])
            prazo = date.fromisoformat(str(dados["prazo_entrega"])[:10])
        except (TypeError, ValueError):
            raise ErroBanco("quantidade/cliente_id devem ser numeros e prazo_entrega AAAA-MM-DD") from None
        if quantidade <= 0:
            raise ErroBanco("a quantidade deve ser maior que zero")
        limite = dados.get("limite_defeito")
        if limite in (None, ""):
            limite = 0.05
        try:
            limite = float(limite)
        except (TypeError, ValueError):
            raise ErroBanco("limite_defeito deve ser um numero entre 0 e 1 (ex.: 0.05)") from None
        if not 0 < limite < 1:
            raise ErroBanco("limite_defeito deve ficar entre 0 e 1 (ex.: 0.05 para 5%)")
        try:
            return self._executar(
                "insert into public.lotes (cliente_id, codigo, modelo_peca, tecido, quantidade, "
                "prazo_entrega, limite_defeito, observacoes) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s) returning id",
                (cliente_id, str(dados["codigo"]).strip(), str(dados["modelo_peca"]).strip(),
                 (str(dados.get("tecido") or "").strip() or None), quantidade, prazo, limite,
                 (str(dados.get("observacoes") or "").strip() or None)),
                contexto="falha ao cadastrar lote", buscar="uma",
            )
        except ErroBanco as exc:
            texto = str(exc)
            if "lotes_codigo_key" in texto or "duplicate key" in texto:
                raise ErroBanco(f"ja existe um lote com o codigo '{dados['codigo']}'") from None
            if "lotes_cliente_id_fkey" in texto:
                raise ErroBanco(f"cliente {cliente_id} nao existe") from None
            raise

    def atualizar_status_lote(self, lote_id: int, status: str) -> bool:
        if status not in STATUS_LOTE:
            raise ErroBanco("status invalido: use " + ", ".join(STATUS_LOTE))
        n = self._executar(
            "update public.lotes set status = %s where id = %s",
            (status, int(lote_id)), contexto="falha ao mudar o status do lote", buscar="nenhuma",
        )
        return bool(n)

    def defeitos_por_classe(self, lote_id: int) -> list[dict]:
        """Contagem por `classe_final` (ja considera a correcao do operador)."""
        return self._executar(
            "select classe_final, count(*)::int as quantidade from public.inspecoes "
            "where lote_id = %s group by classe_final order by quantidade desc",
            (int(lote_id),), contexto="falha ao contar defeitos",
        )

    def ultimas_inspecoes(self, lote_id: int, limite: int = 30) -> list[dict]:
        return self._executar(
            "select id, evento_id, origem, classe_predita, confianca, classe_confirmada, "
            "classe_final, aprovada, imagem_path, criado_em from public.inspecoes "
            "where lote_id = %s order by criado_em desc limit %s",
            (int(lote_id), max(1, min(int(limite), 500))), contexto="falha ao listar inspecoes",
        )

    # ------------------------------------------------------------ inspecoes
    def inserir_inspecao(self, dados: dict) -> dict | None:
        """Grava uma inspecao. Idempotente por `evento_id`: reenviar nao duplica.

        Devolve a linha criada, ou None se o evento ja estava no banco.
        """
        classe = dados.get("classe_predita")
        if classe not in CLASS_KEYS:
            raise ErroBanco(f"classe_predita invalida: {classe!r}")
        origem = dados.get("origem") or "ao_vivo"
        if origem not in ORIGENS:
            raise ErroBanco(f"origem invalida: {origem!r}")
        confirmada = dados.get("classe_confirmada")
        if confirmada is not None and confirmada not in CLASS_KEYS:
            raise ErroBanco(f"classe_confirmada invalida: {confirmada!r}")
        confianca = min(1.0, max(0.0, float(dados.get("confianca") or 0.0)))
        criado_em = dados.get("criado_em")
        return self._executar(
            "insert into public.inspecoes (lote_id, evento_id, origem, classe_predita, confianca, "
            "classe_confirmada, imagem_path, diagnostico, revisao_llm, criado_em) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now())) "
            "on conflict (evento_id) do nothing "
            "returning id, lote_id, evento_id, classe_final, aprovada, criado_em",
            (int(dados["lote_id"]), dados.get("evento_id"), origem, classe, confianca, confirmada,
             dados.get("imagem_path"), self._json(dados.get("diagnostico")),
             self._json(dados.get("revisao_llm")), criado_em),
            contexto="falha ao gravar inspecao", buscar="uma",
        )

    def atualizar_inspecao(self, evento_id: str, **campos: Any) -> bool:
        """Atualiza colunas de uma inspecao achada pelo `evento_id`.

        So aceita classe_confirmada, diagnostico, revisao_llm e imagem_path.
        Devolve False se o evento nao existe no banco.
        """
        desconhecidas = set(campos) - set(_COLUNAS_ATUALIZAVEIS)
        if desconhecidas:
            raise ErroBanco("colunas nao atualizaveis: " + ", ".join(sorted(desconhecidas)))
        if not campos:
            return False
        if "classe_confirmada" in campos and campos["classe_confirmada"] not in (None, *CLASS_KEYS):
            raise ErroBanco(f"classe_confirmada invalida: {campos['classe_confirmada']!r}")
        colunas = sorted(campos)
        valores = [self._json(campos[c]) if c in _COLUNAS_JSON else campos[c] for c in colunas]
        sql = ("update public.inspecoes set "
               + ", ".join(f"{c} = %s" for c in colunas)  # nomes vem da lista fixa acima
               + " where evento_id = %s")
        n = self._executar(sql, (*valores, evento_id),
                           contexto="falha ao atualizar inspecao", buscar="nenhuma")
        return bool(n)

    @staticmethod
    def _json(valor: Any):
        if valor is None:
            return None
        return Jsonb(_jsonavel(valor))

    # -------------------------------------------------------------- storage
    def _cabecalhos_storage(self) -> dict:
        # Chave nova (sb_secret_...): vai no apikey e, igual, no Authorization.
        return {"apikey": str(self._chave), "Authorization": f"Bearer {self._chave}"}

    def _storage(self, metodo: str, rota: str, contexto: str, **kwargs) -> "httpx.Response":
        if not self.storage_configurado:
            raise ErroBanco("Storage nao configurado: defina SUPABASE_URL, "
                            "SUPABASE_SECRET_KEY e SUPABASE_BUCKET no .env")
        try:
            resposta = httpx.request(
                metodo, f"{self._url}/storage/v1/{rota}",
                headers={**self._cabecalhos_storage(), **kwargs.pop("headers", {})},
                timeout=self._timeout_storage, **kwargs,
            )
        except Exception as exc:
            raise self._erro_de(exc, contexto) from None
        if resposta.status_code >= 400:
            try:
                corpo = resposta.json()
                detalhe = corpo.get("message") or corpo.get("error") or json.dumps(corpo)
            except Exception:
                detalhe = resposta.text[:200]
            raise ErroBanco(f"{contexto}: HTTP {resposta.status_code} - {self._explicar(str(detalhe))}")
        return resposta

    def _rota_objeto(self, caminho: str) -> str:
        return quote(f"{self._bucket}/{caminho.lstrip('/')}", safe="/")

    def checar_storage(self) -> dict:
        """Confere se o bucket existe e se a chave tem acesso a ele."""
        info = {"configurado": self.storage_configurado, "ok": False,
                "bucket": self._bucket, "erro": None}
        if not self.storage_configurado:
            info["erro"] = "SUPABASE_URL / SUPABASE_SECRET_KEY / SUPABASE_BUCKET ausentes no .env"
            return info
        try:
            self._storage("GET", f"bucket/{quote(self._bucket, safe='')}",
                          contexto=f"bucket '{self._bucket}' inacessivel")
            info["ok"] = True
        except ErroBanco as exc:
            info["erro"] = str(exc)
        return info

    @staticmethod
    def caminho_foto(lote_id: int, evento_id: str) -> str:
        """Caminho padrao da foto no bucket: lote_<id>/<evento_id>.jpg"""
        seguro = re.sub(r"[^A-Za-z0-9_\-]", "_", str(evento_id))
        return f"lote_{int(lote_id)}/{seguro}.jpg"

    def upload_foto(self, lote_id: int, evento_id: str, jpeg: bytes) -> str:
        """Envia o JPEG para o bucket (sobrescreve se ja existir) e devolve o caminho."""
        caminho = self.caminho_foto(lote_id, evento_id)
        self._storage("POST", f"object/{self._rota_objeto(caminho)}",
                      contexto="falha ao enviar a foto", content=jpeg,
                      headers={"Content-Type": "image/jpeg", "x-upsert": "true"})
        return caminho

    def foto_da_inspecao(self, evento_id: str) -> bytes | None:
        """Baixa a foto de uma inspecao pelo servidor. None se nao existe/foi apagada.

        Por que nao URL assinada: a CDN do Supabase continua servindo uma URL
        assinada ja emitida por ~60 s depois que a foto e apagada (medido em
        11/2026). Aqui o navegador so recebe /api/inspecoes/<evento>/foto, e cada
        pedido consulta o banco antes: foto apagada da 404 na hora.
        """
        linha = self._executar(
            "select imagem_path from public.inspecoes where evento_id = %s",
            (str(evento_id),), contexto="falha ao procurar a inspecao", buscar="uma",
        )
        if not linha or not linha.get("imagem_path"):
            return None
        try:
            resposta = self._storage("GET", f"object/authenticated/{self._rota_objeto(linha['imagem_path'])}",
                                     contexto="falha ao baixar a foto")
        except ErroBanco as exc:
            if "not found" in str(exc).lower():
                return None
            raise
        return resposta.content

    def remover_foto_inspecao(self, evento_id: str) -> bool:
        """Apaga do bucket a foto de uma inspecao e limpa `imagem_path`.

        Devolve False quando o evento nao esta no banco ou ja estava sem foto.
        A ordem (Storage primeiro, depois a coluna) garante que, se o Storage
        falhar, o banco continua apontando para a foto e da para tentar de novo.
        """
        linha = self._executar(
            "select imagem_path from public.inspecoes where evento_id = %s",
            (str(evento_id),), contexto="falha ao procurar a inspecao", buscar="uma",
        )
        if not linha or not linha.get("imagem_path"):
            return False
        self.apagar_fotos([linha["imagem_path"]])
        self.atualizar_inspecao(str(evento_id), imagem_path=None)
        return True

    def apagar_fotos(self, caminhos: list[str]) -> None:
        """Remove objetos do bucket (usado na limpeza de dados de teste)."""
        if caminhos:
            self._storage("DELETE", f"object/{quote(self._bucket, safe='')}",
                          contexto="falha ao apagar fotos", json={"prefixes": caminhos})
