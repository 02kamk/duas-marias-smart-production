"""Arquiteturas, checkpoint e dispositivo do Ponto Certo.

Este e o unico lugar do projeto que sabe montar a rede, trocar a cabeca de
classificacao e gravar/ler o checkpoint. O treino, a avaliacao, a exportacao e
o `Preditor` da inferencia passam todos por aqui, de modo que o formato do
arquivo `artifacts/modelo.pt` tem uma definicao so.

FORMATO DO CHECKPOINT (um dict salvo com ``torch.save``)::

    {
        "state_dict":     OrderedDict dos pesos,
        "backbone":       "mobilenet_v3_small" | "mobilenet_v3_large" | "resnet18",
        "num_classes":    11,
        "classes":        ["normal", "skipped_stitch", ...]   # CLASS_KEYS
        "tamanho_imagem": 224,
        "metricas":       {"acuracia": ..., "macro_f1": ..., ...},
        "criado_em":      "2025-01-31T14:22:05",
    }

Qualquer chave extra passada em ``meta`` e preservada (o treino grava
``epocas``, ``historico`` e afins), mas as sete acima estao sempre presentes -
``carregar_checkpoint`` as preenche com valores seguros se faltarem.

Sem GPU nesta maquina: ``resolver_dispositivo("auto")`` devolve CPU e nada no
projeto assume CUDA.
"""

from __future__ import annotations

import os
import pathlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import torch
from torch import nn
from torchvision import models

from pontocerto.labels import CLASS_KEYS, NUM_CLASSES

# Backbones suportados -> (construtor torchvision, nome do enum de pesos)
BACKBONES: dict[str, str] = {
    "mobilenet_v3_small": "MobileNet_V3_Small_Weights",
    "mobilenet_v3_large": "MobileNet_V3_Large_Weights",
    "resnet18": "ResNet18_Weights",
}

BACKBONE_PADRAO = "mobilenet_v3_small"

CHAVES_CHECKPOINT: tuple[str, ...] = (
    "state_dict",
    "backbone",
    "num_classes",
    "classes",
    "tamanho_imagem",
    "metricas",
    "criado_em",
)


# ---------------------------------------------------------------------------
# Dispositivo
# ---------------------------------------------------------------------------
def resolver_dispositivo(pref: str = "auto") -> torch.device:
    """Traduz "auto" | "cpu" | "cuda" no ``torch.device`` realmente utilizavel.

    Nunca devolve CUDA quando CUDA nao esta disponivel: a maquina do projeto
    roda em CPU e um pedido de "cuda" so imprime um aviso e cai para CPU.
    """
    escolha = str(pref or "auto").strip().lower()
    if escolha.startswith("cuda:"):
        escolha = "cuda"

    try:
        tem_cuda = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
    except Exception:  # pragma: no cover - driver quebrado
        tem_cuda = False

    if escolha == "cpu":
        return torch.device("cpu")
    if escolha == "cuda":
        if tem_cuda:
            return torch.device("cuda")
        print("[aviso] CUDA indisponivel nesta maquina; usando CPU.")
        return torch.device("cpu")
    # "auto" e qualquer valor desconhecido
    return torch.device("cuda") if tem_cuda else torch.device("cpu")


def _normalizar_backbone(backbone: str | None) -> str:
    nome = str(backbone or BACKBONE_PADRAO).strip().lower().replace("-", "_")
    if nome in BACKBONES:
        return nome
    apelidos = {
        "mobilenet": "mobilenet_v3_small",
        "mobilenetv3": "mobilenet_v3_small",
        "mobilenet_v3": "mobilenet_v3_small",
        "small": "mobilenet_v3_small",
        "large": "mobilenet_v3_large",
        "resnet": "resnet18",
    }
    if nome in apelidos:
        return apelidos[nome]
    raise ValueError(
        f"backbone '{backbone}' nao suportado. "
        f"Use um destes: {', '.join(sorted(BACKBONES))}."
    )


# ---------------------------------------------------------------------------
# Construcao do modelo
# ---------------------------------------------------------------------------
def _pesos_imagenet(backbone: str):
    """Devolve o enum de pesos ImageNet do torchvision (ou None se nao houver)."""
    nome_enum = BACKBONES[backbone]
    enum = getattr(models, nome_enum, None)
    if enum is None:  # pragma: no cover - torchvision muito antigo
        return None
    return getattr(enum, "IMAGENET1K_V1", None) or getattr(enum, "DEFAULT", None)


def _construir(backbone: str, pesos) -> nn.Module:
    if backbone == "resnet18":
        return models.resnet18(weights=pesos)
    if backbone == "mobilenet_v3_large":
        return models.mobilenet_v3_large(weights=pesos)
    return models.mobilenet_v3_small(weights=pesos)


def _trocar_cabeca(modelo: nn.Module, backbone: str, num_classes: int) -> nn.Module:
    """Substitui a ultima camada linear por uma de ``num_classes`` saidas."""
    if backbone == "resnet18":
        modelo.fc = nn.Linear(modelo.fc.in_features, num_classes)
    else:  # familia mobilenet_v3
        modelo.classifier[-1] = nn.Linear(
            modelo.classifier[-1].in_features, num_classes
        )
    return modelo


def criar_modelo(
    backbone: str = BACKBONE_PADRAO,
    num_classes: int = NUM_CLASSES,
    pretrained: bool = True,
) -> nn.Module:
    """Monta a rede com a cabeca trocada para ``num_classes`` saidas.

    Com ``pretrained=True`` tenta baixar os pesos ImageNet. Se nao houver
    internet (ou o cache do torch estiver vazio), avisa e segue com pesos
    aleatorios em vez de quebrar o treino.
    """
    nome = _normalizar_backbone(backbone)
    n = int(num_classes)
    if n < 2:
        raise ValueError(f"num_classes deve ser >= 2; recebi {num_classes}.")

    pesos = None
    if pretrained:
        pesos = _pesos_imagenet(nome)
        if pesos is None:
            print(f"[aviso] torchvision sem pesos ImageNet para '{nome}'; "
                  "treinando do zero.")

    if pesos is not None:
        try:
            modelo = _construir(nome, pesos)
            print(f"[ok] {nome} com pesos ImageNet.")
        except Exception as exc:
            print(f"[aviso] nao consegui baixar os pesos ImageNet de '{nome}' "
                  f"({type(exc).__name__}: {exc}).")
            print("        Seguindo com pesos aleatorios (pretrained=False).")
            modelo = _construir(nome, None)
    else:
        modelo = _construir(nome, None)

    modelo = _trocar_cabeca(modelo, nome, n)
    # Guarda o nome no proprio modulo: o Grad-CAM e o export podem consultar.
    try:
        modelo.pontocerto_backbone = nome  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass
    return modelo


def contar_parametros(modelo: nn.Module) -> dict:
    """Parametros totais e treinaveis (usado no log do treino)."""
    total = sum(p.numel() for p in modelo.parameters())
    treinaveis = sum(p.numel() for p in modelo.parameters() if p.requires_grad)
    return {"total": int(total), "treinaveis": int(treinaveis)}


# ---------------------------------------------------------------------------
# Camada alvo do Grad-CAM
# ---------------------------------------------------------------------------
def camada_alvo_gradcam(modelo: nn.Module, backbone: str = "") -> nn.Module:
    """Ultimo bloco convolucional da rede - onde o Grad-CAM pendura os hooks.

    mobilenet_v3_*  -> ``modelo.features[-1]``  (Conv2dNormActivation final)
    resnet18        -> ``modelo.layer4[-1]``    (ultimo BasicBlock)

    Se o backbone nao for informado, tenta descobrir pela estrutura do modelo e,
    em ultimo caso, devolve a ultima ``nn.Conv2d`` encontrada.
    """
    if modelo is None:
        raise ValueError("camada_alvo_gradcam precisa de um modelo.")

    nome = str(backbone or getattr(modelo, "pontocerto_backbone", "") or "").lower()

    if nome.startswith("resnet"):
        camada = getattr(modelo, "layer4", None)
        if camada is not None and len(camada) > 0:
            return camada[-1]
    if nome.startswith("mobilenet"):
        features = getattr(modelo, "features", None)
        if features is not None and len(features) > 0:
            return features[-1]

    # Sem backbone declarado: deduz pela estrutura.
    features = getattr(modelo, "features", None)
    if features is not None and len(features) > 0:
        return features[-1]
    camada = getattr(modelo, "layer4", None)
    if camada is not None and len(camada) > 0:
        return camada[-1]

    ultima = None
    for modulo in modelo.modules():
        if isinstance(modulo, nn.Conv2d):
            ultima = modulo
    if ultima is None:
        raise ValueError(
            "nao encontrei camada convolucional para o Grad-CAM neste modelo."
        )
    return ultima


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------
def _limpar_para_salvar(valor: Any) -> Any:
    """Converte tensores/numpy em tipos puros do Python (checkpoint portatil)."""
    if isinstance(valor, torch.Tensor):
        return valor.detach().to("cpu").tolist()
    if isinstance(valor, dict):
        return {str(k): _limpar_para_salvar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_limpar_para_salvar(v) for v in valor]
    if isinstance(valor, Path):
        return str(valor)
    try:  # numpy escalar
        import numpy as np

        if isinstance(valor, np.generic):
            return valor.item()
        if isinstance(valor, np.ndarray):
            return valor.tolist()
    except Exception:  # pragma: no cover
        pass
    return valor


def salvar_checkpoint(modelo: nn.Module, caminho: str | os.PathLike, meta: dict | None = None) -> None:
    """Grava pesos + metadados no formato unico do projeto.

    O ``state_dict`` vai sempre para CPU: um checkpoint gravado em GPU nao
    carregaria num ambiente so de CPU sem `map_location`.
    """
    if modelo is None:
        raise ValueError("salvar_checkpoint precisa de um modelo.")

    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)

    meta = dict(meta or {})
    backbone = _normalizar_backbone(
        meta.get("backbone") or getattr(modelo, "pontocerto_backbone", "") or BACKBONE_PADRAO
    )
    classes = meta.get("classes") or list(CLASS_KEYS)
    classes = [str(c) for c in classes]
    num_classes = int(meta.get("num_classes") or len(classes) or NUM_CLASSES)

    state_dict = {k: v.detach().to("cpu") for k, v in modelo.state_dict().items()}

    pacote: dict[str, Any] = {chave: _limpar_para_salvar(valor)
                              for chave, valor in meta.items()
                              if chave != "state_dict"}
    pacote.update(
        {
            "state_dict": state_dict,
            "backbone": backbone,
            "num_classes": num_classes,
            "classes": classes,
            "tamanho_imagem": int(meta.get("tamanho_imagem") or 224),
            "metricas": _limpar_para_salvar(dict(meta.get("metricas") or {})),
            "criado_em": str(meta.get("criado_em") or datetime.now().isoformat(timespec="seconds")),
        }
    )

    # Escrita atomica: um Ctrl+C no meio do save nao corrompe o modelo bom.
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    torch.save(pacote, temporario)
    os.replace(temporario, destino)


def carregar_checkpoint(
    caminho: str | os.PathLike,
    dispositivo: str | torch.device = "cpu",
) -> tuple[nn.Module, dict]:
    """Le o checkpoint e devolve ``(modelo_em_eval, meta)``.

    ``meta`` e tudo que estava no arquivo menos o ``state_dict``, com as chaves
    do contrato garantidas. O modelo volta em ``eval()`` e ja no dispositivo
    pedido - e o que o `Preditor` da inferencia espera.
    """
    arquivo = Path(caminho)
    if not arquivo.exists():
        raise FileNotFoundError(
            f"checkpoint nao encontrado: {arquivo}. "
            "Rode o treino (scripts/02_treinar.py) antes."
        )

    destino = dispositivo if isinstance(dispositivo, torch.device) else resolver_dispositivo(str(dispositivo))

    try:
        bruto = torch.load(arquivo, map_location=destino, weights_only=True)
    except Exception:
        # Checkpoints antigos (ou com objetos nao triviais no meta) exigem o
        # unpickle completo. O arquivo e gerado pelo proprio projeto.
        bruto = torch.load(arquivo, map_location=destino, weights_only=False)

    if not isinstance(bruto, dict) or "state_dict" not in bruto:
        raise ValueError(
            f"checkpoint invalido em {arquivo}: esperava um dict com a chave 'state_dict'."
        )

    classes = bruto.get("classes") or list(CLASS_KEYS)
    classes = [str(c) for c in classes]
    num_classes = int(bruto.get("num_classes") or len(classes) or NUM_CLASSES)
    backbone = _normalizar_backbone(bruto.get("backbone") or BACKBONE_PADRAO)

    modelo = criar_modelo(backbone, num_classes, pretrained=False)
    faltando, sobrando = modelo.load_state_dict(bruto["state_dict"], strict=False)
    if faltando or sobrando:
        raise ValueError(
            f"checkpoint {arquivo} nao casa com o backbone '{backbone}': "
            f"{len(faltando)} peso(s) faltando, {len(sobrando)} sobrando."
        )

    modelo.eval()
    modelo.to(destino)

    meta = {chave: valor for chave, valor in bruto.items() if chave != "state_dict"}
    meta["backbone"] = backbone
    meta["num_classes"] = num_classes
    meta["classes"] = classes
    meta["tamanho_imagem"] = int(meta.get("tamanho_imagem") or 224)
    meta["metricas"] = dict(meta.get("metricas") or {})
    meta["criado_em"] = str(meta.get("criado_em") or "")
    return modelo, meta


# ---------------------------------------------------------------------------
# Teste rapido
# ---------------------------------------------------------------------------
def _teste_rapido() -> None:
    import tempfile

    for nome in BACKBONES:
        modelo = criar_modelo(nome, NUM_CLASSES, pretrained=False)
        saida = modelo(torch.randn(2, 3, 224, 224))
        assert tuple(saida.shape) == (2, NUM_CLASSES), saida.shape
        alvo = camada_alvo_gradcam(modelo, nome)
        p = contar_parametros(modelo)
        print(f"{nome:<22} saida={tuple(saida.shape)} "
              f"alvo={type(alvo).__name__} params={p['total']:,}")

    modelo = criar_modelo(BACKBONE_PADRAO, NUM_CLASSES, pretrained=False)
    with tempfile.TemporaryDirectory() as pasta:
        destino = Path(pasta) / "teste.pt"
        salvar_checkpoint(
            modelo,
            destino,
            {"backbone": BACKBONE_PADRAO, "tamanho_imagem": 224,
             "metricas": {"macro_f1": 0.5}, "epocas": 1},
        )
        recarregado, meta = carregar_checkpoint(destino, "cpu")
        for chave in CHAVES_CHECKPOINT:
            if chave == "state_dict":
                continue
            assert chave in meta, f"meta sem a chave {chave}"
        assert meta["classes"] == list(CLASS_KEYS)
        assert meta["epocas"] == 1
        a = modelo(torch.zeros(1, 3, 224, 224))
        b = recarregado(torch.zeros(1, 3, 224, 224))
        assert torch.allclose(a, b, atol=1e-5), "pesos nao sobreviveram ao round-trip"
        print(f"round-trip ok; meta={sorted(meta)}")

    print(f"dispositivo auto -> {resolver_dispositivo('auto')}")
    print("[ok] model.py passou no teste rapido.")


if __name__ == "__main__":
    _teste_rapido()
