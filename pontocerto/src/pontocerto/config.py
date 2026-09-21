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

# .../pontocerto/src/pontocerto/config.py -> raiz = .../pontocerto
RAIZ = Path(__file__).resolve().parents[2]
CONFIG_PADRAO = RAIZ / "config.yaml"

# Chaves cujo valor e um caminho e por isso precisa ser resolvido.
_CHAVES_DE_CAMINHO = {
    "raiz", "manifesto", "saida", "historico", "saida_dir", "modelo",
    "pasta_capturas", "pasta_relatorios", "correcoes",
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


def chave_openrouter() -> str | None:
    """Le a chave do OpenRouter do ambiente (ou do .env da raiz do projeto)."""
    chave = os.environ.get("OPENROUTER_API_KEY")
    if chave:
        return chave.strip()
    env = RAIZ / ".env"
    if env.exists():
        for linha in env.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            nome, _, valor = linha.partition("=")
            if nome.strip() == "OPENROUTER_API_KEY":
                valor = valor.strip().strip('"').strip("'")
                if valor:
                    os.environ.setdefault("OPENROUTER_API_KEY", valor)
                    return valor
    return None
