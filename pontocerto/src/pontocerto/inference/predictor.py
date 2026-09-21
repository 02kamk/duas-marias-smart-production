"""Preditor de frames do Ponto Certo.

Carrega o checkpoint treinado e classifica um frame da camera (ou uma imagem
enviada pela interface) em uma das 11 classes da taxonomia.

Regras de ouro deste modulo:

* O construtor NUNCA levanta excecao. Se o modelo ainda nao foi treinado, o
  objeto nasce com `disponivel == False` e `erro` preenchido - a API sobe do
  mesmo jeito e a interface mostra um aviso amigavel. `recarregar()` tenta de
  novo quando o arquivo aparecer.
* Caminho normal roda em `torch.inference_mode()` (rapido, sem grafo).
  Caminho com Grad-CAM roda em `torch.enable_grad()`, FORA do inference_mode -
  tensores criados dentro de inference_mode nao podem entrar no autograd.
* O modelo e usado por varias threads (loop de inferencia, MJPEG, rotas da
  API), entao todo forward acontece sob um lock.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import torch

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from pontocerto.labels import (
    CLASS_KEYS,
    CLASS_NAMES_PT,
    NUM_CLASSES,
    class_by_index,
    is_defect,
)
from pontocerto.inference.gradcam import GradCAM

# Deixa ao menos 2 nucleos livres para a camera e o servidor web.
try:
    torch.set_num_threads(max(1, (os.cpu_count() or 4) - 2))
except Exception:  # pragma: no cover
    pass


# ---------------------------------------------------------------------------
# Dependencias dos outros modulos, com fallback local
# ---------------------------------------------------------------------------
# Os modulos de treino/transformacoes sao escritos em paralelo. Se por algum
# motivo nao estiverem disponiveis, o Preditor continua funcionando com
# implementacoes locais equivalentes (mesma normalizacao ImageNet, mesma
# arquitetura) em vez de derrubar o servidor.

MEDIA_PADRAO = (0.485, 0.456, 0.406)
DESVIO_PADRAO = (0.229, 0.224, 0.225)

try:
    from pontocerto.data.transforms import preparar_frame_bgr as _preparar_oficial
except Exception:  # pragma: no cover
    _preparar_oficial = None

try:
    from pontocerto.training.model import (
        camada_alvo_gradcam as _camada_oficial,
        carregar_checkpoint as _checkpoint_oficial,
        resolver_dispositivo as _dispositivo_oficial,
    )
except Exception:  # pragma: no cover
    _camada_oficial = None
    _checkpoint_oficial = None
    _dispositivo_oficial = None


def _fb_resolver_dispositivo(pref: str) -> torch.device:
    escolha = str(pref or "auto").strip().lower()
    if escolha == "cpu":
        return torch.device("cpu")
    tem_cuda = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
    if escolha == "cuda":
        return torch.device("cuda") if tem_cuda else torch.device("cpu")
    return torch.device("cuda") if tem_cuda else torch.device("cpu")


def _fb_criar_modelo(backbone: str, num_classes: int) -> torch.nn.Module:
    from torch import nn
    from torchvision import models

    nome = str(backbone or "mobilenet_v3_small").lower()
    if nome == "resnet18":
        modelo = models.resnet18(weights=None)
        modelo.fc = nn.Linear(modelo.fc.in_features, num_classes)
    elif nome == "mobilenet_v3_large":
        modelo = models.mobilenet_v3_large(weights=None)
        modelo.classifier[-1] = nn.Linear(modelo.classifier[-1].in_features, num_classes)
    else:
        modelo = models.mobilenet_v3_small(weights=None)
        modelo.classifier[-1] = nn.Linear(modelo.classifier[-1].in_features, num_classes)
    return modelo


def _fb_carregar_checkpoint(caminho: str, dispositivo: str = "cpu") -> tuple[torch.nn.Module, dict]:
    try:
        bruto = torch.load(caminho, map_location=dispositivo, weights_only=True)
    except Exception:
        bruto = torch.load(caminho, map_location=dispositivo, weights_only=False)
    if not isinstance(bruto, dict) or "state_dict" not in bruto:
        raise ValueError(
            f"checkpoint invalido em {caminho}: esperava um dict com a chave 'state_dict'."
        )
    modelo = _fb_criar_modelo(
        bruto.get("backbone", "mobilenet_v3_small"),
        int(bruto.get("num_classes", NUM_CLASSES)),
    )
    modelo.load_state_dict(bruto["state_dict"])
    modelo.eval()
    meta = {chave: valor for chave, valor in bruto.items() if chave != "state_dict"}
    return modelo, meta


def _fb_camada_alvo(modelo: torch.nn.Module, backbone: str) -> torch.nn.Module:
    nome = str(backbone or "").lower()
    if nome.startswith("resnet") and hasattr(modelo, "layer4"):
        return modelo.layer4[-1]
    if hasattr(modelo, "features"):
        return modelo.features[-1]
    if hasattr(modelo, "layer4"):
        return modelo.layer4[-1]
    ultima = None
    for modulo in modelo.modules():
        if isinstance(modulo, torch.nn.Conv2d):
            ultima = modulo
    if ultima is None:
        raise ValueError("nao encontrei camada convolucional para o Grad-CAM.")
    return ultima


def _fb_preparar_frame_bgr(frame_bgr: np.ndarray, tamanho: int) -> torch.Tensor:
    quadro = np.ascontiguousarray(frame_bgr)
    if quadro.ndim == 2:
        quadro = np.stack([quadro] * 3, axis=2)
    if quadro.shape[2] == 4:
        quadro = quadro[:, :, :3]
    if cv2 is not None:
        quadro = cv2.resize(quadro, (int(tamanho), int(tamanho)), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(quadro, cv2.COLOR_BGR2RGB)
    else:  # pragma: no cover
        ys = np.linspace(0, quadro.shape[0] - 1, int(tamanho)).astype(np.int32)
        xs = np.linspace(0, quadro.shape[1] - 1, int(tamanho)).astype(np.int32)
        rgb = quadro[ys][:, xs][:, :, ::-1]
    arr = np.asarray(rgb, dtype=np.float32) / 255.0
    arr = (arr - np.asarray(MEDIA_PADRAO, dtype=np.float32)) / np.asarray(DESVIO_PADRAO, dtype=np.float32)
    tensor = torch.from_numpy(np.ascontiguousarray(arr.transpose(2, 0, 1)))
    return tensor.unsqueeze(0)


def _resolver_dispositivo(pref: str) -> torch.device:
    if _dispositivo_oficial is not None:
        try:
            return _dispositivo_oficial(pref)
        except Exception:
            pass
    return _fb_resolver_dispositivo(pref)


def _carregar_checkpoint(caminho: str, dispositivo: str = "cpu") -> tuple[torch.nn.Module, dict]:
    if _checkpoint_oficial is not None:
        return _checkpoint_oficial(caminho, dispositivo)
    return _fb_carregar_checkpoint(caminho, dispositivo)


def _camada_alvo(modelo: torch.nn.Module, backbone: str) -> torch.nn.Module:
    if _camada_oficial is not None:
        try:
            return _camada_oficial(modelo, backbone)
        except Exception:
            pass
    return _fb_camada_alvo(modelo, backbone)


def preparar_frame(frame_bgr: np.ndarray, tamanho: int) -> torch.Tensor:
    """Frame BGR (H, W, 3) uint8 -> tensor (1, 3, T, T) normalizado."""
    if _preparar_oficial is not None:
        return _preparar_oficial(frame_bgr, tamanho)
    return _fb_preparar_frame_bgr(frame_bgr, tamanho)


# ---------------------------------------------------------------------------
# Predicao
# ---------------------------------------------------------------------------

@dataclass
class Predicao:
    """Resultado da classificacao de um frame."""

    classe_idx: int
    classe_key: str
    nome: str
    confianca: float
    probabilidades: list[float] = field(default_factory=list)
    top: list[dict] = field(default_factory=list)
    e_falha: bool = False
    gravidade: str = "ok"
    ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "classe_idx": int(self.classe_idx),
            "classe_key": self.classe_key,
            "nome": self.nome,
            "confianca": float(self.confianca),
            "probabilidades": [float(p) for p in self.probabilidades],
            "top": [dict(item) for item in self.top],
            "e_falha": bool(self.e_falha),
            "gravidade": self.gravidade,
            "ms": float(self.ms),
        }


def _nome_classe(indice: int) -> str:
    if 0 <= indice < len(CLASS_NAMES_PT):
        return CLASS_NAMES_PT[indice]
    return f"classe {indice}"


def _key_classe(indice: int) -> str:
    if 0 <= indice < len(CLASS_KEYS):
        return CLASS_KEYS[indice]
    return f"classe_{indice}"


def _gravidade_classe(indice: int) -> str:
    try:
        return class_by_index(indice).gravidade
    except Exception:
        return "media"


def montar_predicao(probabilidades, ms: float = 0.0, top_k: int = 3) -> Predicao:
    """Monta a `Predicao` a partir do vetor de probabilidades."""
    probs = [float(p) for p in probabilidades]
    if not probs:
        raise ValueError("vetor de probabilidades vazio.")
    indice = int(max(range(len(probs)), key=lambda i: probs[i]))
    ordem = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
    k = max(1, min(int(top_k or 3), len(probs)))
    topo = [
        {
            "index": int(i),
            "key": _key_classe(i),
            "nome": _nome_classe(i),
            "prob": float(probs[i]),
        }
        for i in ordem[:k]
    ]
    return Predicao(
        classe_idx=indice,
        classe_key=_key_classe(indice),
        nome=_nome_classe(indice),
        confianca=float(probs[indice]),
        probabilidades=probs,
        top=topo,
        e_falha=bool(is_defect(indice)),
        gravidade=_gravidade_classe(indice),
        ms=float(ms),
    )


# ---------------------------------------------------------------------------
# Preditor
# ---------------------------------------------------------------------------

class Preditor:
    """Envolve o modelo treinado e serve predicoes para o resto do sistema."""

    def __init__(
        self,
        cfg,
        caminho_modelo: str | None = None,
        dispositivo: str | None = None,
    ) -> None:
        self._cfg = cfg
        self._lock = threading.RLock()

        self._caminho = str(caminho_modelo) if caminho_modelo else self._do_cfg(
            ("inferencia", "modelo"), "artifacts/modelo.pt"
        )
        pref = dispositivo if dispositivo else self._do_cfg(("inferencia", "dispositivo"), "auto")
        try:
            self._dispositivo = _resolver_dispositivo(pref)
        except Exception:
            self._dispositivo = torch.device("cpu")

        self._tamanho = int(self._do_cfg(("dados", "tamanho_imagem"), 224))
        self._top_k = int(self._do_cfg(("avaliacao", "top_k"), 3))
        self._gradcam_ligado = bool(self._do_cfg(("inferencia", "gradcam"), True))

        self._modelo: Optional[torch.nn.Module] = None
        self._meta: dict = {}
        self._erro: Optional[str] = None
        self._backbone: str = ""
        self._classes: list[str] = list(CLASS_KEYS)
        self._cam: Optional[GradCAM] = None
        self._erro_gradcam: Optional[str] = None

        self._carregar()

    # -- leitura tolerante do config ---------------------------------------

    def _do_cfg(self, caminho: tuple[str, ...], padrao):
        no = self._cfg
        try:
            for parte in caminho:
                no = no[parte]
            return no if no is not None else padrao
        except Exception:
            return padrao

    # -- carga -------------------------------------------------------------

    def _carregar(self) -> None:
        """Tenta carregar o checkpoint. Nunca levanta excecao."""
        with self._lock:
            self._descartar_gradcam()
            self._modelo = None
            self._meta = {}
            self._erro = None
            try:
                arquivo = Path(self._caminho)
                if not arquivo.exists():
                    raise FileNotFoundError(
                        f"modelo nao encontrado em {arquivo}. "
                        "Rode o treino (scripts/02_treinar.py) antes de inspecionar."
                    )
                modelo, meta = _carregar_checkpoint(str(arquivo), str(self._dispositivo))
                modelo.eval()
                modelo.to(self._dispositivo)
                for parametro in modelo.parameters():
                    parametro.requires_grad_(False)

                self._modelo = modelo
                self._meta = dict(meta or {})
                self._backbone = str(self._meta.get("backbone", "") or "")
                classes = self._meta.get("classes")
                if isinstance(classes, (list, tuple)) and classes:
                    self._classes = [str(c) for c in classes]
                tamanho = self._meta.get("tamanho_imagem")
                if tamanho:
                    self._tamanho = int(tamanho)
                self._preparar_gradcam()
            except Exception as exc:
                self._modelo = None
                self._erro = f"{type(exc).__name__}: {exc}"

    def _preparar_gradcam(self) -> None:
        self._erro_gradcam = None
        if not self._gradcam_ligado or self._modelo is None:
            return
        try:
            alvo = _camada_alvo(self._modelo, self._backbone)
            self._cam = GradCAM(self._modelo, alvo)
        except Exception as exc:
            self._cam = None
            self._erro_gradcam = f"{type(exc).__name__}: {exc}"

    def _descartar_gradcam(self) -> None:
        if self._cam is not None:
            try:
                self._cam.liberar()
            except Exception:
                pass
        self._cam = None

    def recarregar(self) -> bool:
        """Tenta carregar o modelo de novo. Devolve True se ficou disponivel."""
        self._carregar()
        return self.disponivel

    # -- propriedades ------------------------------------------------------

    @property
    def disponivel(self) -> bool:
        return self._modelo is not None

    @property
    def erro(self) -> Optional[str]:
        return self._erro

    @property
    def meta(self) -> dict:
        return dict(self._meta)

    @property
    def backbone(self) -> str:
        return self._backbone

    @property
    def tamanho(self) -> int:
        return int(self._tamanho)

    @property
    def classes(self) -> list[str]:
        return list(self._classes)

    @property
    def caminho_modelo(self) -> str:
        return str(self._caminho)

    @property
    def dispositivo(self) -> str:
        return str(self._dispositivo)

    @property
    def gradcam_disponivel(self) -> bool:
        return self._cam is not None

    @property
    def erro_gradcam(self) -> Optional[str]:
        return self._erro_gradcam

    # -- predicao ----------------------------------------------------------

    def _exigir_modelo(self) -> torch.nn.Module:
        if self._modelo is None:
            raise RuntimeError(
                "modelo indisponivel para inferencia. " + (self._erro or "treine o modelo primeiro.")
            )
        return self._modelo

    def _preparar_entrada(self, t: torch.Tensor) -> torch.Tensor:
        if not isinstance(t, torch.Tensor):
            raise TypeError("prever_tensor() espera um torch.Tensor.")
        entrada = t.detach()
        if entrada.dim() == 3:
            entrada = entrada.unsqueeze(0)
        if entrada.dim() != 4:
            raise ValueError(f"tensor deve ser (1,3,H,W); recebi {tuple(entrada.shape)}")
        # clone() fora de inference_mode garante um tensor comum, utilizavel
        # tanto no caminho rapido quanto no caminho com gradientes.
        return entrada.clone().to(self._dispositivo, dtype=torch.float32)

    def prever_tensor(
        self, t: torch.Tensor, com_gradcam: bool = False
    ) -> tuple[Predicao, Optional[np.ndarray]]:
        """Classifica um tensor (1, 3, T, T) ja normalizado."""
        modelo = self._exigir_modelo()
        entrada = self._preparar_entrada(t)

        inicio = time.perf_counter()
        mapa: Optional[np.ndarray] = None
        with self._lock:
            usar_cam = bool(com_gradcam) and self._cam is not None
            logits = None
            if usar_cam:
                try:
                    # Caminho com gradientes: JAMAIS dentro de inference_mode.
                    mapa = self._cam.gerar(entrada)
                    logits = self._cam.ultimos_logits
                except Exception as exc:
                    self._erro_gradcam = f"{type(exc).__name__}: {exc}"
                    mapa = None
                    logits = None
            if logits is None:
                # Caminho rapido: sem grafo, sem alocacao extra.
                with torch.inference_mode():
                    logits = modelo(entrada)
                    probs = torch.softmax(logits.reshape(logits.shape[0], -1)[0].float(), dim=0)
                    lista = probs.to("cpu").tolist()
            else:
                probs = torch.softmax(logits.reshape(logits.shape[0], -1)[0].float(), dim=0)
                lista = probs.detach().to("cpu").tolist()
        ms = (time.perf_counter() - inicio) * 1000.0
        return montar_predicao(lista, ms=ms, top_k=self._top_k), mapa

    def prever_bgr(
        self, frame_bgr: np.ndarray, com_gradcam: bool = False
    ) -> tuple[Predicao, Optional[np.ndarray]]:
        """Classifica um frame BGR da camera. O mapa volta no tamanho do frame."""
        if frame_bgr is None:
            raise ValueError("frame_bgr nao pode ser None.")
        quadro = np.ascontiguousarray(frame_bgr)
        tensor = preparar_frame(quadro, self._tamanho)
        predicao, mapa = self.prever_tensor(tensor, com_gradcam=com_gradcam)
        if mapa is not None:
            altura, largura = quadro.shape[:2]
            if mapa.shape[0] != altura or mapa.shape[1] != largura:
                if cv2 is not None:
                    mapa = cv2.resize(
                        mapa.astype(np.float32), (int(largura), int(altura)),
                        interpolation=cv2.INTER_LINEAR,
                    )
                else:  # pragma: no cover
                    ys = np.linspace(0, mapa.shape[0] - 1, altura).astype(np.int32)
                    xs = np.linspace(0, mapa.shape[1] - 1, largura).astype(np.int32)
                    mapa = mapa[ys][:, xs]
            mapa = np.clip(mapa.astype(np.float32), 0.0, 1.0)
        return predicao, mapa

    def prever_arquivo(
        self, caminho: str, com_gradcam: bool = False
    ) -> tuple[Predicao, Optional[np.ndarray]]:
        """Classifica uma imagem do disco (aceita caminhos do Windows com acento)."""
        arquivo = Path(caminho)
        if not arquivo.exists():
            raise FileNotFoundError(f"imagem nao encontrada: {arquivo}")
        dados = arquivo.read_bytes()
        return self.prever_bytes(dados, com_gradcam=com_gradcam)

    def prever_bytes(
        self, dados: bytes, com_gradcam: bool = False
    ) -> tuple[Predicao, Optional[np.ndarray]]:
        """Classifica uma imagem recebida como bytes (upload da interface)."""
        frame = self._decodificar(dados)
        return self.prever_bgr(frame, com_gradcam=com_gradcam)

    @staticmethod
    def _decodificar(dados: bytes) -> np.ndarray:
        if not dados:
            raise ValueError("arquivo de imagem vazio.")
        quadro = None
        if cv2 is not None:
            buffer = np.frombuffer(dados, dtype=np.uint8)
            quadro = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if quadro is None:
            try:
                import io

                from PIL import Image

                with Image.open(io.BytesIO(dados)) as imagem:
                    rgb = np.asarray(imagem.convert("RGB"), dtype=np.uint8)
                quadro = rgb[:, :, ::-1].copy()
            except Exception as exc:
                raise ValueError(f"nao consegui decodificar a imagem enviada: {exc}") from exc
        return np.ascontiguousarray(quadro)

    # -- diagnostico -------------------------------------------------------

    def resumo(self) -> dict:
        """Resumo usado pela rota /api/saude."""
        return {
            "carregado": self.disponivel,
            "erro": self._erro,
            "backbone": self._backbone,
            "metricas": dict(self._meta.get("metricas") or {}),
            "caminho": str(self._caminho),
            "dispositivo": str(self._dispositivo),
            "tamanho_imagem": int(self._tamanho),
            "gradcam": self.gradcam_disponivel,
        }

    def fechar(self) -> None:
        with self._lock:
            self._descartar_gradcam()
            self._modelo = None

    def __del__(self) -> None:  # pragma: no cover - best effort
        try:
            self._descartar_gradcam()
        except Exception:
            pass
