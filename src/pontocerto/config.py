"""Carregamento da configuracao do Ponto Certo.

Le o config.yaml da raiz do projeto e devolve um objeto com acesso por ponto
(`cfg.treino.epocas`) e por chave (`cfg["treino"]["epocas"]`). Todos os caminhos
declarados no YAML sao resolvidos em relacao a raiz do projeto, entao qualquer
script pode ser chamado de qualquer diretorio.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

import yaml

# <repo>/src/pontocerto/config.py -> raiz = <repo> (raiz do repositorio)
RAIZ = Path(__file__).resolve().parents[2]
CONFIG_PADRAO = RAIZ / "config.yaml"

# Chaves cujo valor e um caminho e por isso precisa ser resolvido.
_CHAVES_DE_CAMINHO = {
    "raiz", "manifesto", "saida", "historico", "saida_dir", "modelo",
    "pasta_capturas", "pasta_relatorios", "correcoes", "pendentes",
}


class Secao(dict):
    """dict com acesso por atributo, recursivo."""

    def __getattr__(self, nome: str) -> Any:
        try:
            return self[nome]
        except KeyError as exc:
            raise AttributeError(
                f"chave '{nome}' nao existe nesta secao do config.yaml "
                f"(disponiveis: {', '.join(sorted(self))})"
            ) from exc

    def __setattr__(self, nome: str, valor: Any) -> None:
        self[nome] = valor

    def __iter__(self) -> Iterator[str]:
        return super().__iter__()


def _envolver(valor: Any, chave: str | None = None) -> Any:
    if isinstance(valor, dict):
        return Secao({k: _envolver(v, k) for k, v in valor.items()})
    if isinstance(valor, list):
        return [_envolver(v) for v in valor]
    if chave in _CHAVES_DE_CAMINHO and isinstance(valor, str):
        return str((RAIZ / valor).resolve())
    return valor


def carregar_config(caminho: str | os.PathLike | None = None) -> Secao:
    """Le e devolve a configuracao. Sem argumento usa o config.yaml da raiz."""
    destino = Path(caminho) if caminho else CONFIG_PADRAO
    if not destino.exists():
        raise FileNotFoundError(
            f"config.yaml nao encontrado em {destino}. "
            "Rode os comandos a partir da pasta 'pontocerto' do projeto."
        )
    with open(destino, "r", encoding="utf-8") as fh:
        bruto = yaml.safe_load(fh) or {}
    cfg = _envolver(bruto)
    cfg["_raiz"] = str(RAIZ)
    cfg["_arquivo"] = str(destino)
    return cfg


def caminho(relativo: str) -> Path:
    """Resolve um caminho relativo a raiz do projeto."""
    return (RAIZ / relativo).resolve()


def garantir_pasta(p: str | os.PathLike) -> Path:
    """Cria a pasta (e as pastas pai) se ainda nao existir e devolve o Path."""
    destino = Path(p)
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def variavel_env(nome: str) -> str | None:
    """Le uma variavel do ambiente ou, se nao houver, do .env da raiz do projeto.

    O valor lido do .env e copiado para os.environ (sem sobrescrever) para que
    as proximas leituras nao precisem abrir o arquivo de novo. Valor vazio conta
    como ausente.
    """
    valor = os.environ.get(nome)
    if valor and valor.strip():
        return valor.strip()
    env = RAIZ / ".env"
    if env.exists():
        # utf-8-sig: o Bloco de Notas do Windows pode gravar o .env com BOM.
        for linha in env.read_text(encoding="utf-8-sig").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, bruto = linha.partition("=")
            if chave.strip() == nome:
                bruto = bruto.strip().strip('"').strip("'")
                if bruto:
                    os.environ.setdefault(nome, bruto)
                    return bruto
    return None


def chave_openrouter() -> str | None:
    """Le a chave do OpenRouter do ambiente (ou do .env da raiz do projeto)."""
    return variavel_env("OPENROUTER_API_KEY")


def credenciais_supabase() -> dict[str, str | None]:
    """Le as variaveis do Supabase (ambiente ou .env). Ausentes viram None.

    - SUPABASE_DB_URL: connection string do Session pooler (porta 5432)
    - SUPABASE_URL: https://<projeto>.supabase.co (usado so para o Storage)
    - SUPABASE_SECRET_KEY: chave secreta (sb_secret_...) para o Storage
    - SUPABASE_BUCKET: nome do bucket privado das capturas

    Esses valores sao segredos: quem os recebe nunca deve imprimi-los.
    """
    return {
        "db_url": variavel_env("SUPABASE_DB_URL"),
        "url": variavel_env("SUPABASE_URL"),
        "secret_key": variavel_env("SUPABASE_SECRET_KEY"),
        "bucket": variavel_env("SUPABASE_BUCKET"),
    }
