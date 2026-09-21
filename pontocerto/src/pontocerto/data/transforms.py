"""Pre-processamento e aumentos de dados do Ponto Certo.

As imagens do dataset ja chegam em 224x224 e o sinal que interessa (ponto
falhado, linha frouxa, marca de agulha) e uma textura fina. Por isso os
aumentos aqui sao deliberadamente suaves: recorte com escala minima alta,
rotacao pequena, jitter de cor moderado e, com baixa probabilidade, borrao e
ruido -- que simulam camera fora de foco e ganho alto, os dois defeitos de
captura mais comuns na webcam do chao de fabrica.

Todos os parametros vem de ``cfg.treino.aug`` (config.yaml).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from typing import Callable

import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image
from torchvision.transforms import InterpolationMode

# Estatisticas do ImageNet (os backbones sao pre-treinados nela).
MEDIA = (0.485, 0.456, 0.406)
DESVIO = (0.229, 0.224, 0.225)

_MEDIA_T = torch.tensor(MEDIA).view(3, 1, 1)
_DESVIO_T = torch.tensor(DESVIO).view(3, 1, 1)


# ---------------------------------------------------------------------------
# Transformes customizados (baixa probabilidade, aplicados no fim da cadeia)
# ---------------------------------------------------------------------------
class BorrarAleatorio:
    """Desfoque gaussiano ocasional sobre a imagem PIL (camera fora de foco)."""

    def __init__(self, prob: float = 0.10, sigma: tuple[float, float] = (0.3, 1.1),
                 kernel: int = 3):
        self.prob = float(prob)
        self.sigma = (float(sigma[0]), float(sigma[1]))
        self.kernel = int(kernel) | 1  # kernel precisa ser impar
        self._blur = T.GaussianBlur(kernel_size=self.kernel, sigma=self.sigma)

    def __call__(self, img):
        if self.prob <= 0.0 or torch.rand(1).item() >= self.prob:
            return img
        return self._blur(img)

    def __repr__(self) -> str:  # pragma: no cover - so para log
        return f"BorrarAleatorio(prob={self.prob}, sigma={self.sigma})"


class RuidoAleatorio:
    """Ruido gaussiano ocasional sobre o tensor 0..1 (ganho alto / pouca luz)."""

    def __init__(self, prob: float = 0.10, sigma: tuple[float, float] = (0.01, 0.05)):
        self.prob = float(prob)
        self.sigma = (float(sigma[0]), float(sigma[1]))

    def __call__(self, tensor: torch.Tensor) -> torch.Tensor:
        if self.prob <= 0.0 or torch.rand(1).item() >= self.prob:
            return tensor
        baixo, alto = self.sigma
        desvio = baixo + (alto - baixo) * float(torch.rand(1).item())
        ruidoso = tensor + torch.randn_like(tensor) * desvio
        return ruidoso.clamp_(0.0, 1.0)

    def __repr__(self) -> str:  # pragma: no cover - so para log
        return f"RuidoAleatorio(prob={self.prob}, sigma={self.sigma})"


# ---------------------------------------------------------------------------
# Cadeias de transformacao
# ---------------------------------------------------------------------------
def _aug(cfg) -> dict:
    try:
        bruto = cfg.treino.aug
    except Exception:
        bruto = {}
    return dict(bruto or {})


def _tamanho(cfg) -> int:
    try:
        return int(cfg.dados.tamanho_imagem)
    except Exception:
        return 224


def transformes_treino(cfg) -> Callable:
    """Cadeia de aumentos do treino. Entrada: PIL.Image -> tensor normalizado."""
    tamanho = _tamanho(cfg)
    aug = _aug(cfg)

    escala_min = float(aug.get("random_resized_crop_min", 0.75))
    escala_min = min(max(escala_min, 0.30), 1.0)
    graus = float(aug.get("rotacao_graus", 0.0))
    p_h = float(aug.get("flip_horizontal", 0.0))
    p_v = float(aug.get("flip_vertical", 0.0))
    brilho = float(aug.get("brilho", 0.0))
    contraste = float(aug.get("contraste", 0.0))
    saturacao = float(aug.get("saturacao", 0.0))
    matiz = float(aug.get("matiz", 0.0))
    p_borrao = float(aug.get("borrao_prob", 0.0))
    p_ruido = float(aug.get("ruido_prob", 0.0))

    etapas: list = []

    if graus > 0:
        # Rotacao antes do recorte: o recorte seguinte descarta boa parte das
        # bordas pretas geradas pela rotacao.
        etapas.append(
            T.RandomRotation(
                degrees=graus,
                interpolation=InterpolationMode.BILINEAR,
                expand=False,
            )
        )

    etapas.append(
        T.RandomResizedCrop(
            size=tamanho,
            scale=(escala_min, 1.0),
            ratio=(0.90, 1.10),  # quase quadrado: nao distorce a carreira de pontos
            interpolation=InterpolationMode.BILINEAR,
        )
    )

    if p_h > 0:
        etapas.append(T.RandomHorizontalFlip(p=p_h))
    if p_v > 0:
        etapas.append(T.RandomVerticalFlip(p=p_v))

    if any(v > 0 for v in (brilho, contraste, saturacao, matiz)):
        etapas.append(
            T.ColorJitter(
                brightness=brilho,
                contrast=contraste,
                saturation=saturacao,
                hue=matiz,
            )
        )

    if p_borrao > 0:
        etapas.append(BorrarAleatorio(prob=p_borrao))

    etapas.append(T.ToTensor())

    if p_ruido > 0:
        etapas.append(RuidoAleatorio(prob=p_ruido))

    etapas.append(T.Normalize(mean=MEDIA, std=DESVIO))
    return T.Compose(etapas)


def transformes_eval(cfg) -> Callable:
    """Cadeia deterministica usada em validacao, teste e inferencia por arquivo."""
    tamanho = _tamanho(cfg)
    return T.Compose(
        [
            T.Resize((tamanho, tamanho), interpolation=InterpolationMode.BILINEAR),
            T.ToTensor(),
            T.Normalize(mean=MEDIA, std=DESVIO),
        ]
    )


# ---------------------------------------------------------------------------
# Ponte com o OpenCV (camera e upload)
# ---------------------------------------------------------------------------
def preparar_frame_bgr(frame_bgr: np.ndarray, tamanho: int) -> torch.Tensor:
    """Converte um frame BGR do OpenCV no tensor (1, 3, T, T) que o modelo espera."""
    if frame_bgr is None:
        raise ValueError("preparar_frame_bgr recebeu None.")

    arr = np.asarray(frame_bgr)
    if arr.ndim == 2:  # tons de cinza
        arr = np.stack([arr] * 3, axis=-1)
    elif arr.ndim == 3 and arr.shape[2] == 4:  # BGRA
        arr = arr[:, :, :3]
    elif arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"Formato de frame nao suportado: {arr.shape}")

    tamanho = int(tamanho)
    altura, largura = arr.shape[:2]
    if (altura, largura) != (tamanho, tamanho):
        import cv2  # import tardio: mantem o modulo leve para quem so treina

        interp = cv2.INTER_AREA if (altura > tamanho or largura > tamanho) else cv2.INTER_LINEAR
        arr = cv2.resize(arr, (tamanho, tamanho), interpolation=interp)

    # BGR -> RGB, HWC -> CHW, 0..255 -> 0..1
    rgb = np.ascontiguousarray(arr[:, :, ::-1])
    tensor = torch.from_numpy(rgb).permute(2, 0, 1).float().div_(255.0)
    tensor = (tensor - _MEDIA_T) / _DESVIO_T
    return tensor.unsqueeze(0)


def desnormalizar(tensor: torch.Tensor) -> np.ndarray:
    """Desfaz a normalizacao e devolve uma imagem RGB uint8 (H, W, 3)."""
    t = tensor.detach().cpu()
    if t.dim() == 4:
        t = t[0]
    if t.dim() != 3 or t.shape[0] != 3:
        raise ValueError(f"Esperava tensor (3,H,W) ou (1,3,H,W), recebi {tuple(tensor.shape)}")
    t = t * _DESVIO_T + _MEDIA_T
    t = t.clamp(0.0, 1.0).mul(255.0).round().byte()
    return t.permute(1, 2, 0).numpy()


# ---------------------------------------------------------------------------
# Teste rapido
# ---------------------------------------------------------------------------
def _teste_rapido() -> None:
    from pontocerto.config import carregar_config

    cfg = carregar_config()
    tamanho = _tamanho(cfg)

    tt = transformes_treino(cfg)
    te = transformes_eval(cfg)
    print("transformes_treino:")
    for etapa in tt.transforms:
        print(f"  - {etapa}")

    img = Image.fromarray(
        np.random.randint(0, 255, (tamanho, tamanho, 3), dtype=np.uint8), mode="RGB"
    )
    a = tt(img)
    b = te(img)
    assert a.shape == (3, tamanho, tamanho), a.shape
    assert b.shape == (3, tamanho, tamanho), b.shape
    print(f"treino  -> {tuple(a.shape)} min={a.min():.3f} max={a.max():.3f}")
    print(f"eval    -> {tuple(b.shape)} min={b.min():.3f} max={b.max():.3f}")

    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)  # BGR
    t = preparar_frame_bgr(frame, tamanho)
    assert t.shape == (1, 3, tamanho, tamanho), t.shape
    print(f"frame   -> {tuple(t.shape)} media={t.mean():.3f}")

    # ida e volta: eval + desnormalizar deve recuperar a imagem quase igual
    volta = desnormalizar(te(img))
    erro = np.abs(volta.astype(np.int16) - np.asarray(img).astype(np.int16)).mean()
    assert volta.shape == (tamanho, tamanho, 3) and volta.dtype == np.uint8
    print(f"desnormalizar -> {volta.shape} {volta.dtype} erro_medio={erro:.3f}")

    cinza = np.random.randint(0, 255, (100, 120), dtype=np.uint8)
    assert preparar_frame_bgr(cinza, tamanho).shape == (1, 3, tamanho, tamanho)
    bgra = np.random.randint(0, 255, (100, 120, 4), dtype=np.uint8)
    assert preparar_frame_bgr(bgra, tamanho).shape == (1, 3, tamanho, tamanho)
    print("[ok] transforms.py passou no teste rapido.")


if __name__ == "__main__":
    _teste_rapido()
