"""Varredura do dataset e divisao estratificada treino/validacao/teste.

O dataset bruto tem a forma:

    <raiz>/<tecido>/<classe>/<LETRA>_<CLASSE>_<SEQ>.jpg
    ex.: "A. Cotton-Poly/0. Normal/A_00_001.jpg"

Este modulo varre essa arvore e grava o manifesto unico do projeto em
``cfg.dados.manifesto`` (artifacts/splits.csv) com as colunas, nesta ordem:

    caminho,classe_idx,classe_key,classe_pasta,tecido_letra,tecido_pasta,split

A estratificacao e feita por par (tecido, classe): cada um dos 121 grupos
(11 tecidos x 11 classes) e embaralhado com uma semente derivada de
``cfg.divisao.semente`` e fatiado em 70% / 15% / 15%. Assim todo tecido e toda
classe aparecem nos tres splits, e o resultado e deterministico: rodar de novo
produz exatamente o mesmo CSV.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from pontocerto.config import carregar_config, garantir_pasta
from pontocerto.labels import (
    CLASSES,
    CLASS_KEYS,
    FABRIC_LETTERS,
    FABRICS,
)

# Ordem EXATA das colunas do manifesto (contrato do projeto).
COLUNAS: tuple[str, ...] = (
    "caminho",
    "classe_idx",
    "classe_key",
    "classe_pasta",
    "tecido_letra",
    "tecido_pasta",
    "split",
)

SPLITS: tuple[str, ...] = ("treino", "validacao", "teste")

EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# ---------------------------------------------------------------------------
# Varredura
# ---------------------------------------------------------------------------
def _varrer_dataset(raiz: Path, verboso: bool = True) -> list[dict]:
    """Percorre <raiz>/<tecido>/<classe> e devolve um registro por imagem."""
    raiz = Path(raiz)
    if not raiz.is_dir():
        raise FileNotFoundError(
            f"Pasta do dataset nao encontrada: {raiz}\n"
            "Confira a chave 'dados.raiz' no config.yaml."
        )

    registros: list[dict] = []
    faltando: list[str] = []

    for tecido in FABRICS:
        pasta_tecido = raiz / tecido.folder
        if not pasta_tecido.is_dir():
            faltando.append(tecido.folder)
            continue
        for classe in CLASSES:
            pasta_classe = pasta_tecido / classe.folder
            if not pasta_classe.is_dir():
                faltando.append(f"{tecido.folder}/{classe.folder}")
                continue
            arquivos = sorted(
                (
                    p
                    for p in pasta_classe.iterdir()
                    if p.is_file() and p.suffix.lower() in EXTENSOES_IMAGEM
                ),
                key=lambda p: p.name.lower(),
            )
            for arquivo in arquivos:
                registros.append(
                    {
                        # caminho RELATIVO a raiz do dataset, sempre com "/"
                        "caminho": f"{tecido.folder}/{classe.folder}/{arquivo.name}",
                        "classe_idx": classe.index,
                        "classe_key": classe.key,
                        "classe_pasta": classe.folder,
                        "tecido_letra": tecido.letter,
                        "tecido_pasta": tecido.folder,
                    }
                )

    if faltando and verboso:
        print(f"[aviso] {len(faltando)} pasta(s) esperada(s) nao foram encontradas:")
        for nome in faltando[:10]:
            print(f"        - {nome}")
        if len(faltando) > 10:
            print(f"        ... e mais {len(faltando) - 10}")

    if not registros:
        raise RuntimeError(
            f"Nenhuma imagem encontrada em {raiz}. "
            "Esperava pastas como 'A. Cotton-Poly/0. Normal/'."
        )
    return registros


# ---------------------------------------------------------------------------
# Fatiamento
# ---------------------------------------------------------------------------
def _limites(n: int, p_treino: float, p_validacao: float) -> tuple[int, int]:
    """Devolve (corte_treino, corte_validacao) para um grupo de tamanho n.

    Garante pelo menos uma imagem em cada split quando n >= 3.
    """
    if n <= 0:
        return 0, 0
    if n == 1:
        return 1, 1  # so da para treinar
    if n == 2:
        return 1, 2  # treino + validacao
    corte_treino = int(round(n * p_treino))
    corte_validacao = int(round(n * (p_treino + p_validacao)))
    corte_treino = min(max(corte_treino, 1), n - 2)
    corte_validacao = min(max(corte_validacao, corte_treino + 1), n - 1)
    return corte_treino, corte_validacao


def _proporcoes(cfg) -> tuple[float, float, float]:
    p_tr = float(cfg.divisao.treino)
    p_va = float(cfg.divisao.validacao)
    p_te = float(cfg.divisao.teste)
    soma = p_tr + p_va + p_te
    if soma <= 0:
        raise ValueError("As proporcoes de 'divisao' no config.yaml somam zero.")
    return p_tr / soma, p_va / soma, p_te / soma


def _semente_do_grupo(semente: int, tecido_letra: str, classe_idx: int) -> np.random.Generator:
    """Gerador independente e deterministico para cada par (tecido, classe).

    Usar uma semente derivada (em vez de um unico Generator compartilhado)
    mantem o sorteio de um grupo estavel mesmo que outro grupo mude de tamanho.
    """
    try:
        pos_tecido = FABRIC_LETTERS.index(tecido_letra)
    except ValueError:
        pos_tecido = abs(hash(tecido_letra)) % 1000
    return np.random.default_rng([int(semente), int(pos_tecido), int(classe_idx)])


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
def construir_manifesto(cfg=None, forcar: bool = False) -> pd.DataFrame:
    """Varre o dataset, estratifica por (tecido, classe) e grava o CSV.

    Se o manifesto ja existir e ``forcar`` for False, apenas o carrega de volta.
    """
    cfg = cfg if cfg is not None else carregar_config()
    destino = Path(cfg.dados.manifesto)

    if destino.exists() and not forcar:
        df = carregar_manifesto(cfg)
        print(f"[ok] Manifesto ja existe ({len(df)} linhas): {destino}")
        print("     Use forcar=True (ou --forcar na linha de comando) para refazer.")
        return df

    raiz = Path(cfg.dados.raiz)
    print(f"[..] Varrendo dataset em {raiz}")
    registros = _varrer_dataset(raiz)
    df = pd.DataFrame(registros).reset_index(drop=True)
    print(f"[ok] {len(df)} imagens encontradas em {df['tecido_letra'].nunique()} tecidos "
          f"e {df['classe_idx'].nunique()} classes.")

    semente = int(cfg.divisao.semente)
    p_tr, p_va, _p_te = _proporcoes(cfg)

    splits = np.empty(len(df), dtype=object)
    for (tecido_letra, classe_idx), grupo in df.groupby(
        ["tecido_letra", "classe_idx"], sort=True
    ):
        posicoes = grupo.index.to_numpy()
        rng = _semente_do_grupo(semente, str(tecido_letra), int(classe_idx))
        embaralhado = posicoes[rng.permutation(len(posicoes))]
        corte_tr, corte_va = _limites(len(embaralhado), p_tr, p_va)
        splits[embaralhado[:corte_tr]] = "treino"
        splits[embaralhado[corte_tr:corte_va]] = "validacao"
        splits[embaralhado[corte_va:]] = "teste"

    df["split"] = splits
    if df["split"].isna().any():
        raise RuntimeError("Falha interna: alguma imagem ficou sem split.")

    df = df[list(COLUNAS)]

    garantir_pasta(destino.parent)
    df.to_csv(destino, index=False, encoding="utf-8")
    print(f"[ok] Manifesto gravado em {destino}")
    return df


def carregar_manifesto(cfg=None) -> pd.DataFrame:
    """Le o manifesto do disco. Erro claro e acionavel se nao existir."""
    cfg = cfg if cfg is not None else carregar_config()
    destino = Path(cfg.dados.manifesto)
    if not destino.exists():
        raise FileNotFoundError(
            f"Manifesto nao encontrado em {destino}.\n"
            "Gere-o antes de treinar com:\n"
            "    python -m pontocerto.data.split --forcar\n"
            "ou chamando construir_manifesto(cfg, forcar=True)."
        )
    df = pd.read_csv(destino, encoding="utf-8")
    faltando = [c for c in COLUNAS if c not in df.columns]
    if faltando:
        raise ValueError(
            f"Manifesto {destino} esta com colunas faltando: {faltando}. "
            "Refaca com --forcar."
        )
    df["classe_idx"] = df["classe_idx"].astype(int)
    df["caminho"] = df["caminho"].astype(str)
    df["split"] = df["split"].astype(str)
    return df[list(COLUNAS)]


def resumo_manifesto(df: pd.DataFrame) -> dict:
    """Contagens por split, por classe e por tecido (para log e para a API)."""
    total = int(len(df))
    por_split = {s: int((df["split"] == s).sum()) for s in SPLITS}

    por_classe: dict[str, dict] = {}
    for key in CLASS_KEYS:
        sub = df[df["classe_key"] == key]
        por_classe[key] = {
            "total": int(len(sub)),
            **{s: int((sub["split"] == s).sum()) for s in SPLITS},
        }

    por_tecido: dict[str, dict] = {}
    for letra in FABRIC_LETTERS:
        sub = df[df["tecido_letra"] == letra]
        por_tecido[letra] = {
            "total": int(len(sub)),
            **{s: int((sub["split"] == s).sum()) for s in SPLITS},
        }

    return {
        "total": total,
        "classes": int(df["classe_key"].nunique()),
        "tecidos": int(df["tecido_letra"].nunique()),
        "por_split": por_split,
        "proporcao_split": {
            s: round(por_split[s] / total, 4) if total else 0.0 for s in SPLITS
        },
        "por_classe": por_classe,
        "por_tecido": por_tecido,
    }


def _imprimir_resumo(resumo: dict) -> None:
    from pontocerto.labels import class_by_key, fabric_by_letter

    print()
    print("=" * 72)
    print("RESUMO DO MANIFESTO")
    print("=" * 72)
    print(f"Total de imagens : {resumo['total']}")
    for s in SPLITS:
        n = resumo["por_split"][s]
        p = resumo["proporcao_split"][s]
        print(f"  {s:<10} {n:>6}  ({p:6.2%})")

    print()
    print(f"{'classe':<28}{'total':>7}{'treino':>9}{'valid.':>9}{'teste':>8}")
    print("-" * 72)
    for key, c in resumo["por_classe"].items():
        nome = class_by_key(key).pt
        print(f"{nome:<28}{c['total']:>7}{c['treino']:>9}{c['validacao']:>9}{c['teste']:>8}")

    print()
    print(f"{'tecido':<28}{'total':>7}{'treino':>9}{'valid.':>9}{'teste':>8}")
    print("-" * 72)
    for letra, t in resumo["por_tecido"].items():
        nome = f"{letra}. {fabric_by_letter(letra).pt}"
        print(f"{nome:<28}{t['total']:>7}{t['treino']:>9}{t['validacao']:>9}{t['teste']:>8}")
    print("=" * 72)


def _verificar(df: pd.DataFrame) -> None:
    """Teste rapido: sanidade do manifesto recem-gerado."""
    assert list(df.columns) == list(COLUNAS), f"colunas fora de ordem: {list(df.columns)}"
    assert df["caminho"].is_unique, "ha caminhos duplicados no manifesto"
    assert set(df["split"].unique()) <= set(SPLITS), "split invalido no manifesto"
    assert set(df["classe_key"].unique()) <= set(CLASS_KEYS), "classe_key invalida"
    assert not df["caminho"].str.contains("\\\\", regex=True).any(), \
        "caminho com barra invertida (deve usar '/')"

    incompletos = []
    for (letra, classe_idx), grupo in df.groupby(["tecido_letra", "classe_idx"], sort=True):
        presentes = set(grupo["split"].unique())
        if presentes != set(SPLITS):
            incompletos.append(f"{letra}/{classe_idx}: {sorted(presentes)}")
    if incompletos:
        print(f"[aviso] {len(incompletos)} grupo(s) (tecido, classe) sem os tres splits:")
        for item in incompletos[:10]:
            print(f"        - {item}")
    else:
        print("[ok] todos os 121 grupos (tecido x classe) aparecem nos tres splits.")

    n = len(df)
    prop_treino = (df["split"] == "treino").sum() / n
    assert 0.66 <= prop_treino <= 0.74, f"proporcao de treino fora do esperado: {prop_treino:.3f}"
    print(f"[ok] {n} linhas, proporcao de treino {prop_treino:.4f}.")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Gera o manifesto artifacts/splits.csv (divisao estratificada)."
    )
    parser.add_argument("--forcar", "-f", action="store_true",
                        help="refaz o manifesto mesmo que ele ja exista")
    parser.add_argument("--config", default=None,
                        help="caminho alternativo para o config.yaml")
    args = parser.parse_args(argv)

    cfg = carregar_config(args.config)
    df = construir_manifesto(cfg, forcar=args.forcar)
    _imprimir_resumo(resumo_manifesto(df))
    _verificar(df)
    print(f"\nArquivo: {Path(cfg.dados.manifesto)}")


if __name__ == "__main__":
    main()
