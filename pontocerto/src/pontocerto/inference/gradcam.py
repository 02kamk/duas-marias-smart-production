"""Grad-CAM para o Ponto Certo.

Gera o mapa de calor que mostra ONDE a rede olhou para decidir a classe do
ponto de costura. Funciona com mobilenet_v3_small, mobilenet_v3_large e
resnet18 - a camada alvo vem de `pontocerto.training.model.camada_alvo_gradcam`.

Dois cuidados importantes nesta implementacao:

1. Grad-CAM PRECISA de gradientes. Por isso `gerar()` roda dentro de
   `torch.enable_grad()` e jamais pode ser chamado de dentro de um bloco
   `torch.inference_mode()` (tensores criados la nao podem entrar no autograd).
   O `Preditor` separa os dois caminhos justamente por causa disso.

2. Os hooks sao registrados UMA unica vez, no `__init__`, e removidos em
   `liberar()`. Nada de registrar hook a cada frame - em 30 fps isso viraria
   um vazamento de memoria em poucos segundos.

O colormap do overlay e proprio (branco -> areia -> laranja -> terracota ->
marrom), feito na mao com numpy. Nada de COLORMAP_JET.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import torch

try:  # opencv e usado so para redimensionar; ha um fallback puro numpy
    import cv2
except Exception:  # pragma: no cover - ambiente sem opencv
    cv2 = None


# ---------------------------------------------------------------------------
# Colormap quente do projeto (interpolacao linear entre 5 paradas RGB)
# ---------------------------------------------------------------------------

_PARADAS_RGB = np.array(
    [
        [255.0, 255.0, 255.0],   # frio  - branco
        [247.0, 233.0, 226.0],   # areia
        [224.0, 130.0, 88.0],    # laranja
        [193.0, 80.0, 46.0],     # terracota
        [124.0, 58.0, 31.0],     # quente - marrom queimado
    ],
    dtype=np.float32,
)
_POSICOES = np.linspace(0.0, 1.0, len(_PARADAS_RGB), dtype=np.float32)


def _construir_lut(n: int = 256) -> np.ndarray:
    """Tabela (n, 3) em BGR uint8 do colormap do projeto."""
    x = np.linspace(0.0, 1.0, n, dtype=np.float32)
    canais = [np.interp(x, _POSICOES, _PARADAS_RGB[:, c]) for c in range(3)]
    rgb = np.stack(canais, axis=1)          # (n, 3) em RGB
    bgr = rgb[:, ::-1]                      # OpenCV trabalha em BGR
    return np.clip(np.rint(bgr), 0, 255).astype(np.uint8)


LUT_QUENTE: np.ndarray = _construir_lut()


def _redimensionar(mapa: np.ndarray, largura: int, altura: int) -> np.ndarray:
    """Redimensiona o mapa (H, W) float para (altura, largura)."""
    if mapa.shape[0] == altura and mapa.shape[1] == largura:
        return mapa
    if cv2 is not None:
        return cv2.resize(
            mapa.astype(np.float32), (int(largura), int(altura)),
            interpolation=cv2.INTER_LINEAR,
        )
    # Fallback sem opencv: vizinho mais proximo com indexacao numpy.
    ys = (np.linspace(0, mapa.shape[0] - 1, int(altura))).astype(np.int32)
    xs = (np.linspace(0, mapa.shape[1] - 1, int(largura))).astype(np.int32)
    return mapa[ys][:, xs].astype(np.float32)


def _normalizar_01(mapa: np.ndarray) -> np.ndarray:
    """Leva o mapa para a faixa 0..1 de forma segura (mapa chapado -> zeros).

    O teste de "chapado" precisa ser RELATIVO. A escala absoluta do Grad-CAM
    depende inteiramente da magnitude dos logits: a mobilenet_v3_small produz
    mapas na casa de 1e-11 e um limiar absoluto (1e-8) zeraria um mapa
    perfeitamente valido, deixando a tela sem mapa de calor nenhum.
    """
    mapa = np.nan_to_num(mapa.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    menor = float(mapa.min())
    maior = float(mapa.max())
    faixa = maior - menor
    escala = max(abs(maior), abs(menor))
    if escala <= 1e-30 or faixa <= escala * 1e-9:
        return np.zeros_like(mapa, dtype=np.float32)
    return (mapa - menor) / faixa


# ---------------------------------------------------------------------------
# Grad-CAM
# ---------------------------------------------------------------------------

class GradCAM:
    """Grad-CAM classico: media espacial dos gradientes pondera as ativacoes.

    Uso tipico::

        cam = GradCAM(modelo, camada_alvo_gradcam(modelo, "mobilenet_v3_small"))
        mapa = cam.gerar(tensor)          # (H, W) float 0..1
        ...
        cam.liberar()                     # remove os hooks
    """

    def __init__(self, modelo: torch.nn.Module, camada_alvo: torch.nn.Module) -> None:
        if modelo is None or camada_alvo is None:
            raise ValueError("GradCAM exige um modelo e uma camada alvo validos.")
        self.modelo = modelo
        self.camada_alvo = camada_alvo

        self._ativacoes: Optional[torch.Tensor] = None
        self._grad_modulo: Optional[torch.Tensor] = None
        self._grad_tensor: Optional[torch.Tensor] = None
        self._handles: list[Any] = []
        self._usar_hook_modulo = True
        self._liberado = False

        # Ultimo forward feito por gerar(): evita que o Preditor precise de
        # um segundo forward so para descobrir as probabilidades.
        self.ultimos_logits: Optional[torch.Tensor] = None
        self.ultima_classe: Optional[int] = None

        self._registrar_hooks()

    # -- hooks -------------------------------------------------------------

    def _registrar_hooks(self) -> None:
        def hook_forward(_modulo, _entrada, saida):
            # Guarda a ativacao e tambem pendura um hook no proprio tensor.
            # O hook de tensor morre junto com o grafo (nao vaza) e serve de
            # rede de seguranca caso o full_backward_hook do modulo falhe.
            self._ativacoes = saida
            self._grad_modulo = None
            self._grad_tensor = None
            if isinstance(saida, torch.Tensor) and saida.requires_grad:
                saida.register_hook(self._guardar_grad_tensor)
            return None

        def hook_backward(_modulo, _grad_entrada, grad_saida):
            if grad_saida and isinstance(grad_saida[0], torch.Tensor):
                self._grad_modulo = grad_saida[0].detach()
            return None

        self._handles.append(self.camada_alvo.register_forward_hook(hook_forward))
        self._handles.append(self.camada_alvo.register_full_backward_hook(hook_backward))

    def _guardar_grad_tensor(self, grad: torch.Tensor) -> None:
        self._grad_tensor = grad.detach()

    def _remover_hook_modulo(self) -> None:
        """Descarta o full_backward_hook e segue apenas com o hook de tensor."""
        if len(self._handles) >= 2:
            try:
                self._handles[1].remove()
            except Exception:
                pass
            self._handles = self._handles[:1]
        self._usar_hook_modulo = False

    # -- geracao -----------------------------------------------------------

    def gerar(self, tensor_entrada: torch.Tensor, classe_idx: int | None = None) -> np.ndarray:
        """Devolve o mapa (H, W) float 0..1 da ativacao da classe escolhida.

        `tensor_entrada` e um tensor (1, 3, T, T) ja normalizado. Quando
        `classe_idx` e None usa a classe de maior logit.
        """
        if self._liberado:
            raise RuntimeError("Este GradCAM ja foi liberado; crie outro.")
        if not isinstance(tensor_entrada, torch.Tensor):
            raise TypeError("gerar() espera um torch.Tensor.")

        dispositivo = self._dispositivo()
        entrada = tensor_entrada.detach()
        if entrada.dim() == 3:
            entrada = entrada.unsqueeze(0)
        if entrada.dim() != 4:
            raise ValueError(f"tensor de entrada deve ser (1,3,H,W); recebi {tuple(entrada.shape)}")
        if entrada.shape[0] != 1:
            entrada = entrada[:1]
        # clone() fora de inference_mode devolve um tensor comum, pronto para autograd.
        entrada = entrada.clone().to(dispositivo, dtype=torch.float32)
        entrada.requires_grad_(True)

        treinando = self.modelo.training
        self.modelo.eval()
        estados = self._congelar_parametros()
        try:
            mapa = self._passada(entrada, classe_idx)
        except RuntimeError:
            # Alguns blocos com operacoes in-place brigam com full_backward_hook.
            # Tenta de novo usando somente o hook de tensor.
            if not self._usar_hook_modulo:
                raise
            self._remover_hook_modulo()
            mapa = self._passada(entrada, classe_idx)
        finally:
            self._restaurar_parametros(estados)
            if treinando:
                self.modelo.train()
            self._ativacoes = None
            self._grad_modulo = None
            self._grad_tensor = None
        return mapa

    def _passada(self, entrada: torch.Tensor, classe_idx: int | None) -> np.ndarray:
        with torch.enable_grad():
            logits = self.modelo(entrada)
            if logits.dim() == 1:
                logits = logits.unsqueeze(0)
            if classe_idx is None:
                indice = int(torch.argmax(logits[0]).item())
            else:
                indice = int(classe_idx)
            self.ultimos_logits = logits.detach()
            self.ultima_classe = indice

            self.modelo.zero_grad(set_to_none=True)
            if entrada.grad is not None:
                entrada.grad = None
            logits[0, indice].backward()

        ativacoes = self._ativacoes
        gradientes = self._grad_modulo if self._grad_modulo is not None else self._grad_tensor
        if ativacoes is None or gradientes is None:
            raise RuntimeError(
                "Grad-CAM nao capturou ativacoes/gradientes. "
                "Verifique se a camada alvo participa do forward do modelo."
            )

        ativacoes = ativacoes.detach()
        if ativacoes.dim() != 4 or gradientes.dim() != 4:
            raise RuntimeError(
                "Grad-CAM espera uma camada convolucional (N,C,H,W); "
                f"recebi ativacoes {tuple(ativacoes.shape)}."
            )

        pesos = gradientes.mean(dim=(2, 3), keepdim=True)          # (N, C, 1, 1)
        soma = (pesos * ativacoes).sum(dim=1)                      # (N, H, W)
        bruto = soma[0].to("cpu", dtype=torch.float32).numpy()
        mapa = _normalizar_01(np.maximum(bruto, 0.0))
        if float(mapa.max()) <= 0.0:
            # Nenhuma evidencia positiva (acontece com modelo mal treinado ou
            # classe muito improvavel). Em vez de devolver uma tela em branco,
            # mostra a evidencia relativa do mapa antes da ReLU.
            mapa = _normalizar_01(bruto)
        return mapa

    # -- utilidades --------------------------------------------------------

    def _dispositivo(self) -> torch.device:
        try:
            return next(self.modelo.parameters()).device
        except StopIteration:  # pragma: no cover - modelo sem parametros
            return torch.device("cpu")

    def _congelar_parametros(self) -> list[tuple[torch.nn.Parameter, bool]]:
        """Desliga requires_grad dos pesos: o backward fica bem mais barato.

        A entrada e que carrega requires_grad=True, entao o grafo continua
        sendo construido e os gradientes ainda passam pela camada alvo.
        """
        estados: list[tuple[torch.nn.Parameter, bool]] = []
        for p in self.modelo.parameters():
            estados.append((p, p.requires_grad))
            p.requires_grad_(False)
        return estados

    @staticmethod
    def _restaurar_parametros(estados: list[tuple[torch.nn.Parameter, bool]]) -> None:
        for p, valor in estados:
            p.requires_grad_(valor)

    def liberar(self) -> None:
        """Remove todos os hooks. Pode ser chamado mais de uma vez."""
        for handle in self._handles:
            try:
                handle.remove()
            except Exception:
                pass
        self._handles = []
        self._ativacoes = None
        self._grad_modulo = None
        self._grad_tensor = None
        self._liberado = True

    def __enter__(self) -> "GradCAM":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.liberar()

    def __del__(self) -> None:  # pragma: no cover - best effort
        try:
            self.liberar()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------------

def aplicar_mapa(frame_bgr: np.ndarray, mapa: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    """Pinta o mapa de calor sobre o frame BGR e devolve um novo frame BGR uint8.

    O alpha e proporcional a intensidade: regiao fria fica praticamente
    transparente, regiao quente recebe ate `alpha` de cor.
    """
    if frame_bgr is None:
        raise ValueError("frame_bgr nao pode ser None.")
    quadro = np.ascontiguousarray(frame_bgr)
    if quadro.ndim == 2:
        quadro = np.stack([quadro] * 3, axis=2)
    if quadro.dtype != np.uint8:
        quadro = np.clip(quadro, 0, 255).astype(np.uint8)
    if mapa is None:
        return quadro

    altura, largura = quadro.shape[:2]
    calor = np.asarray(mapa, dtype=np.float32)
    if calor.ndim == 3:
        calor = calor[..., 0]
    calor = _redimensionar(calor, largura, altura)
    calor = np.clip(np.nan_to_num(calor, nan=0.0), 0.0, 1.0)

    indices = np.clip(calor * 255.0, 0, 255).astype(np.uint8)
    cor = LUT_QUENTE[indices]                                   # (H, W, 3) BGR uint8
    alpha = float(np.clip(alpha, 0.0, 1.0))

    # Peso por pixel (frio ~ transparente, quente ate `alpha`). A conta toda e
    # feita em 8 bits: em 720x1280 a versao float32 custava ~200 ms por frame,
    # o que inviabilizaria o MJPEG. Assim fica na casa de poucos milissegundos.
    peso = np.clip(calor * (alpha * 255.0), 0, 255).astype(np.uint8)
    if cv2 is not None:
        peso3 = cv2.cvtColor(peso, cv2.COLOR_GRAY2BGR)
        inverso = cv2.bitwise_not(peso3)                        # 255 - peso
        fundo = cv2.multiply(quadro, inverso, scale=1.0 / 255.0)
        frente = cv2.multiply(cor, peso3, scale=1.0 / 255.0)
        return cv2.add(fundo, frente)

    peso3 = peso[..., None].astype(np.uint16)                   # pragma: no cover
    fundo = quadro.astype(np.uint16) * (255 - peso3)
    frente = cor.astype(np.uint16) * peso3
    return ((fundo + frente) // 255).astype(np.uint8)
