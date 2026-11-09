"""Dataset e DataLoaders do Ponto Certo.

Le o manifesto (artifacts/splits.csv), monta um ``torch.utils.data.Dataset``
por split e devolve os tres DataLoaders prontos, junto com os pesos de classe
que compensam o excesso de imagens "Normal" no dataset.

Tudo roda em CPU: ``pin_memory=False`` e ``persistent_workers`` so quando
``cfg.treino.workers > 0``. Em Windows os workers usam spawn, entao qualquer
codigo que crie DataLoaders precisa estar sob ``if __name__ == "__main__"``.
"""

from __future__ import annotations

import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from pontocerto.config import carregar_config
from pontocerto.data.split import SPLITS, carregar_manifesto, construir_manifesto
from pontocerto.data.transforms import transformes_eval, transformes_treino
from pontocerto.labels import CLASS_KEYS, NUM_CLASSES


class DatasetCostura(Dataset):
    """Um item = (tensor da imagem, indice da classe 0..10).

    ``df`` e um recorte do manifesto (geralmente um split). ``raiz_dados`` e a
    pasta onde ficam as pastas de tecido; a coluna ``caminho`` do manifesto e
    relativa a ela.
    """

    def __init__(self, df: pd.DataFrame, raiz_dados: str, transform=None):
        if not isinstance(df, pd.DataFrame):
            raise TypeError("DatasetCostura espera um pandas.DataFrame.")
        faltando = [c for c in ("caminho", "classe_idx") if c not in df.columns]
        if faltando:
            raise ValueError(f"DataFrame sem as colunas {faltando}.")

        self.raiz_dados = Path(raiz_dados)
        self.transform = transform
        self.classes = list(CLASS_KEYS)

        # Listas simples (sem pandas) porque cada worker recebe uma copia.
        # pathlib normaliza a "/" do manifesto para o separador do Windows.
        self.caminhos: list[str] = [
            str(self.raiz_dados / str(c)) for c in df["caminho"].tolist()
        ]
        self.rotulos: list[int] = [int(v) for v in df["classe_idx"].tolist()]
        self.tecidos: list[str] = (
            [str(v) for v in df["tecido_letra"].tolist()]
            if "tecido_letra" in df.columns
            else [""] * len(self.rotulos)
        )
        self._avisou_falha = False

    def __len__(self) -> int:
        return len(self.caminhos)

    def contagem_por_classe(self) -> np.ndarray:
        contagem = np.zeros(NUM_CLASSES, dtype=np.int64)
        for r in self.rotulos:
            if 0 <= r < NUM_CLASSES:
                contagem[r] += 1
        return contagem

    def _abrir(self, caminho: str) -> Image.Image:
        with Image.open(caminho) as img:
            return img.convert("RGB")

    def __getitem__(self, i: int):
        caminho = self.caminhos[i]
        rotulo = self.rotulos[i]
        try:
            imagem = self._abrir(caminho)
        except (OSError, ValueError) as exc:
            # Nao derruba uma epoca inteira por causa de um arquivo ruim.
            if not self._avisou_falha:
                print(f"[aviso] falha ao ler imagem, usando quadro preto: {caminho} ({exc})")
                self._avisou_falha = True
            imagem = Image.new("RGB", (224, 224), color=(0, 0, 0))

        if self.transform is not None:
            tensor = self.transform(imagem)
        else:
            import torchvision.transforms.functional as F

            tensor = F.to_tensor(imagem)
        return tensor, rotulo


# ---------------------------------------------------------------------------
# Pesos de classe
# ---------------------------------------------------------------------------
def calcular_pesos_classe(df_treino: pd.DataFrame) -> torch.Tensor:
    """peso[c] = total / (num_classes * contagem[c]), calculado SO no treino."""
    contagem = np.zeros(NUM_CLASSES, dtype=np.float64)
    for idx, n in df_treino["classe_idx"].value_counts().items():
        i = int(idx)
        if 0 <= i < NUM_CLASSES:
            contagem[i] = float(n)
    total = float(contagem.sum())
    pesos = np.ones(NUM_CLASSES, dtype=np.float32)
    if total > 0:
        for i in range(NUM_CLASSES):
            if contagem[i] > 0:
                pesos[i] = total / (NUM_CLASSES * contagem[i])
            else:
                pesos[i] = 1.0  # classe ausente: peso neutro, sem divisao por zero
    return torch.tensor(pesos, dtype=torch.float32)


# ---------------------------------------------------------------------------
# Subamostragem para testes rapidos
# ---------------------------------------------------------------------------
def _limitar(df: pd.DataFrame, limite: int, semente: int) -> pd.DataFrame:
    """Sorteia no maximo ``limite`` imagens por classe (deterministico)."""
    if limite is None or limite <= 0:
        return df
    partes = []
    for classe_idx, grupo in df.groupby("classe_idx", sort=True):
        if len(grupo) <= limite:
            partes.append(grupo)
            continue
        rng = np.random.default_rng([int(semente), int(classe_idx)])
        escolhidos = rng.permutation(len(grupo))[:limite]
        partes.append(grupo.iloc[np.sort(escolhidos)])
    if not partes:
        return df
    return pd.concat(partes).sort_index()


# ---------------------------------------------------------------------------
# DataLoaders
# ---------------------------------------------------------------------------
def construir_dataloaders(cfg=None, limite_por_classe: int | None = None) -> dict:
    """Monta os tres DataLoaders + pesos de classe + o DataFrame usado.

    Retorna um dict com as chaves:
        "treino", "validacao", "teste" -> DataLoader
        "pesos_classe"                 -> torch.Tensor (11,)
        "df"                           -> pandas.DataFrame efetivamente usado
    """
    cfg = cfg if cfg is not None else carregar_config()

    try:
        df = carregar_manifesto(cfg)
    except FileNotFoundError:
        print("[..] Manifesto ausente; gerando agora...")
        df = construir_manifesto(cfg, forcar=True)

    raiz_dados = str(Path(cfg.dados.raiz))
    semente = int(getattr(cfg.treino, "seed", None) or cfg.divisao.semente)
    batch_size = int(cfg.treino.batch_size)
    workers = max(0, int(cfg.treino.workers))

    # Subamostragem opcional: o limite vale integralmente para o treino e
    # proporcionalmente para validacao/teste (mantem a razao 70/15/15).
    p_tr = float(cfg.divisao.treino) or 1.0
    limites = {"treino": limite_por_classe}
    if limite_por_classe:
        for nome, prop in (("validacao", float(cfg.divisao.validacao)),
                           ("teste", float(cfg.divisao.teste))):
            limites[nome] = max(1, int(round(limite_por_classe * prop / p_tr)))
    else:
        limites["validacao"] = None
        limites["teste"] = None

    t_treino = transformes_treino(cfg)
    t_eval = transformes_eval(cfg)

    partes: dict[str, pd.DataFrame] = {}
    for split in SPLITS:
        sub = df[df["split"] == split].reset_index(drop=True)
        sub = _limitar(sub, limites.get(split), semente).reset_index(drop=True)
        partes[split] = sub
        if sub.empty:
            print(f"[aviso] o split '{split}' ficou vazio.")

    datasets = {
        "treino": DatasetCostura(partes["treino"], raiz_dados, t_treino),
        "validacao": DatasetCostura(partes["validacao"], raiz_dados, t_eval),
        "teste": DatasetCostura(partes["teste"], raiz_dados, t_eval),
    }

    gerador = torch.Generator()
    gerador.manual_seed(semente)

    comuns = dict(
        batch_size=batch_size,
        num_workers=workers,
        pin_memory=False,  # sem GPU nesta maquina
        drop_last=False,
    )
    if workers > 0:
        comuns["persistent_workers"] = True
        comuns["prefetch_factor"] = 2

    loaders = {
        "treino": DataLoader(
            datasets["treino"], shuffle=True, generator=gerador, **comuns
        ),
        "validacao": DataLoader(datasets["validacao"], shuffle=False, **comuns),
        "teste": DataLoader(datasets["teste"], shuffle=False, **comuns),
    }

    pesos = calcular_pesos_classe(partes["treino"])
    df_usado = pd.concat([partes[s] for s in SPLITS], ignore_index=True)

    print(
        "[ok] DataLoaders prontos: "
        f"treino={len(datasets['treino'])}, "
        f"validacao={len(datasets['validacao'])}, "
        f"teste={len(datasets['teste'])} "
        f"(batch={batch_size}, workers={workers})"
    )

    return {
        "treino": loaders["treino"],
        "validacao": loaders["validacao"],
        "teste": loaders["teste"],
        "pesos_classe": pesos,
        "df": df_usado,
    }


# ---------------------------------------------------------------------------
# Teste rapido
# ---------------------------------------------------------------------------
def _teste_rapido() -> None:
    import time

    cfg = carregar_config()

    # 1) Dataset direto, sem workers.
    df = carregar_manifesto(cfg)
    amostra = df[df["split"] == "treino"].head(16).reset_index(drop=True)
    ds = DatasetCostura(amostra, str(Path(cfg.dados.raiz)), transformes_eval(cfg))
    x, y = ds[0]
    print(f"item 0 -> tensor {tuple(x.shape)} dtype={x.dtype} rotulo={y} "
          f"({CLASS_KEYS[y]})")
    assert x.shape[0] == 3 and isinstance(y, int)
    assert len(ds) == 16

    # 2) DataLoaders completos, com limite por classe para ser rapido.
    inicio = time.perf_counter()
    pacote = construir_dataloaders(cfg, limite_por_classe=8)
    for chave in ("treino", "validacao", "teste", "pesos_classe", "df"):
        assert chave in pacote, f"chave ausente: {chave}"

    pesos = pacote["pesos_classe"]
    assert tuple(pesos.shape) == (NUM_CLASSES,), pesos.shape
    print("pesos_classe:", [round(float(v), 3) for v in pesos])

    xb, yb = next(iter(pacote["treino"]))
    print(f"batch treino -> x={tuple(xb.shape)} y={tuple(yb.shape)} "
          f"rotulos={sorted(set(int(v) for v in yb))}")
    assert xb.dim() == 4 and xb.shape[1] == 3

    print(f"[ok] dataset.py passou no teste rapido em {time.perf_counter() - inicio:.1f}s")


if __name__ == "__main__":
    _teste_rapido()
