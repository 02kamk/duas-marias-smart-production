"""Captura de video para o Ponto Certo.

A camera roda em uma thread daemon propria que apenas le quadros e guarda o
mais recente. Quem consome (o motor de inferencia) sempre pega o ultimo quadro
disponivel; quadros antigos sao descartados. Assim a inferencia nunca fica
"atrasada" em relacao a realidade, que e o defeito classico de ler a camera
dentro do laco de processamento.

No Windows o backend preferido e o DirectShow (cv2.CAP_DSHOW), que abre a
webcam bem mais rapido do que o MSMF e aceita mudar resolucao sem travar.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from typing import Any

import cv2
import numpy as np

__all__ = ["Camera", "listar_dispositivos"]

_E_WINDOWS = os.name == "nt"

# Quanto esperar a webcam abrir antes de desistir (segundos).
TEMPO_ABERTURA_S = 15.0

# Quantos quadros conferir na abertura para saber se a imagem chega mesmo.
QUADROS_CONFERENCIA = 8

# Depois de quantos segundos so de imagem preta avisar o operador.
SEGUNDOS_PRETO_AVISO = 3.0

AVISO_IMAGEM_PRETA = (
    "A webcam responde mas nao esta filmando (imagem preta). Quase sempre e o "
    "obturador de privacidade fechado ou a tecla de camera do teclado (nos Acer "
    "costuma ser F6). Confira tambem se outro programa (Teams, Discord, Chrome) "
    "esta com a camera aberta. Depois clique em 'Ligar camera' de novo."
)


def _quadro_preto(quadro: np.ndarray | None) -> bool:
    """True quando o quadro e literalmente todo zero (nao apenas escuro).

    Uma cena escura de verdade ainda tem ruido do sensor; so da zero absoluto
    quando o sensor nem chegou a ligar.
    """
    if quadro is None or quadro.size == 0:
        return True
    try:
        return bool(quadro.max() == 0)
    except Exception:
        return False


def _codigo_backend(nome: str) -> int:
    """Traduz o nome vindo do config.yaml para a constante do OpenCV."""
    nome = (nome or "auto").strip().lower()
    if nome == "dshow":
        return int(getattr(cv2, "CAP_DSHOW", 0))
    if nome == "msmf":
        return int(getattr(cv2, "CAP_MSMF", 0))
    if nome == "any":
        return int(getattr(cv2, "CAP_ANY", 0))
    # "auto": no Windows o DirectShow e o mais confiavel.
    if _E_WINDOWS:
        return int(getattr(cv2, "CAP_DSHOW", 0))
    return int(getattr(cv2, "CAP_ANY", 0))


def _ordem_backends(preferido: str) -> list[int]:
    """Backend preferido primeiro, depois os alternativos, sem repetir."""
    ordem = [_codigo_backend(preferido)]
    if _E_WINDOWS:
        candidatos = [
            int(getattr(cv2, "CAP_DSHOW", 0)),
            int(getattr(cv2, "CAP_MSMF", 0)),
            int(getattr(cv2, "CAP_ANY", 0)),
        ]
    else:
        candidatos = [int(getattr(cv2, "CAP_ANY", 0))]
    for c in candidatos:
        if c not in ordem:
            ordem.append(c)
    return ordem


def _sondar_dispositivos(maximo: int = 5) -> list[int]:
    """Testa os indices 0..maximo-1 e devolve os que abrem de verdade.

    Abrir camera e lento; por isso a funcao tenta ler apenas um quadro e
    libera o dispositivo em seguida.
    """
    encontrados: list[int] = []
    backend = _codigo_backend("auto")
    for indice in range(max(0, int(maximo))):
        cap = None
        try:
            cap = cv2.VideoCapture(indice, backend)
            if not cap.isOpened():
                continue
            ok, quadro = cap.read()
            if ok and quadro is not None:
                encontrados.append(indice)
        except Exception:
            continue
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
    return encontrados


_CACHE_LOCK = threading.Lock()
_CACHE_DISPOSITIVOS: tuple[float, int, list[int]] | None = None
_CACHE_SEGUNDOS = 20.0


def listar_dispositivos(maximo: int = 5) -> list[int]:
    """Lista os indices de camera disponiveis, sem arriscar derrubar o servidor.

    A varredura roda em um PROCESSO separado. No Windows o DirectShow as vezes
    quebra dentro do proprio OpenCV quando nao ha webcam (mensagens
    "backend is generally available but can't be used to capture by index");
    quando isso acontece o processo inteiro morre sem traceback. Isolando a
    varredura, o pior caso vira uma lista vazia em vez do servidor fechando
    sozinho. O resultado fica em cache por alguns segundos porque abrir camera
    e lento.
    """
    maximo = max(0, int(maximo))
    agora = time.monotonic()
    global _CACHE_DISPOSITIVOS
    with _CACHE_LOCK:
        cache = _CACHE_DISPOSITIVOS
        if cache is not None and cache[1] == maximo and (agora - cache[0]) < _CACHE_SEGUNDOS:
            return list(cache[2])

    try:
        proc = subprocess.run(
            [sys.executable, str(__file__), "--listar", str(maximo)],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if _E_WINDOWS else 0,
        )
        saida = (proc.stdout or "").strip().splitlines()
        encontrados = json.loads(saida[-1]) if saida else []
        encontrados = [int(v) for v in encontrados]
    except Exception:
        # Subprocesso indisponivel (ex.: executavel congelado): tenta local.
        try:
            encontrados = _sondar_dispositivos(maximo)
        except Exception:
            encontrados = []

    with _CACHE_LOCK:
        _CACHE_DISPOSITIVOS = (time.monotonic(), maximo, list(encontrados))
    return encontrados


class Camera:
    """Webcam com leitura em thread e descarte de quadros velhos."""

    def __init__(self, cfg: Any) -> None:
        cam = cfg.camera
        self._cfg = cfg
        self._indice = int(cam.indice)
        self._largura = int(cam.largura)
        self._altura = int(cam.altura)
        self._fps_alvo = int(cam.fps)
        self._espelhar = bool(cam.espelhar)
        self._backend_nome = str(cam.get("backend", "auto"))
        roi = list(cam.get("roi", [0.25, 0.25, 0.50, 0.50]))
        self._roi = tuple(float(v) for v in (roi + [0.5, 0.5, 0.5, 0.5])[:4])

        self._cap: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._evt_parar = threading.Event()
        self._evt_aberta = threading.Event()
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._ativa = False
        self._erro: str | None = None
        self._fps_real = 0.0
        self._largura_real = 0
        self._altura_real = 0

    # ------------------------------------------------------------------ ciclo

    def iniciar(self, indice: int | None = None) -> bool:
        """Abre a camera e sobe a thread de captura. Devolve True se conseguiu.

        O dispositivo e aberto DENTRO da thread de captura, nao aqui. No Windows
        o DirectShow e COM: criar o capture em uma thread (a do request HTTP) e
        usar em outra costuma travar ou derrubar o processo sem traceback.
        """
        if indice is not None:
            indice = int(indice)
            if self._ativa and indice == self._indice:
                return True
            self._indice = indice
        if self._ativa:
            return True

        self.parar()
        self._erro = None
        self._evt_parar.clear()
        self._evt_aberta.clear()
        self._thread = threading.Thread(
            target=self._laco, name="pontocerto-camera", daemon=True
        )
        self._thread.start()
        # Espera a abertura terminar (ou falhar) antes de responder ao usuario.
        self._evt_aberta.wait(TEMPO_ABERTURA_S)
        if not self._ativa and not self._erro:
            self._erro = (
                f"A camera {self._indice} demorou demais para abrir "
                f"({TEMPO_ABERTURA_S:.0f}s). Feche outros programas que usam a webcam."
            )
        return bool(self._ativa)

    def parar(self) -> None:
        """Encerra a thread e libera o dispositivo (pode ser chamado varias vezes)."""
        self._evt_parar.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=TEMPO_ABERTURA_S + 2.0)
        self._ativa = False
        self._fps_real = 0.0
        with self._lock:
            self._frame = None

    # ----------------------------------------------------------------- estado

    @property
    def ativa(self) -> bool:
        return bool(self._ativa)

    @property
    def erro(self) -> str | None:
        return self._erro

    @property
    def indice(self) -> int:
        return self._indice

    def info(self) -> dict:
        return {
            "ativa": bool(self._ativa),
            "indice": int(self._indice),
            "largura": int(self._largura_real or self._largura),
            "altura": int(self._altura_real or self._altura),
            "fps_real": round(float(self._fps_real), 1),
            "erro": self._erro,
        }

    # ---------------------------------------------------------------- leitura

    def ler(self) -> np.ndarray | None:
        """Ultimo quadro BGR capturado (ja espelhado), ou None."""
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def recortar_roi(self, frame: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """Recorta a regiao de interesse e devolve (recorte, (x, y, w, h))."""
        if frame is None:
            raise ValueError("frame vazio em recortar_roi")
        altura, largura = frame.shape[:2]
        fx, fy, fw, fh = self._roi
        x = int(round(max(0.0, min(1.0, fx)) * largura))
        y = int(round(max(0.0, min(1.0, fy)) * altura))
        w = int(round(max(0.01, min(1.0, fw)) * largura))
        h = int(round(max(0.01, min(1.0, fh)) * altura))
        x = min(x, max(0, largura - 8))
        y = min(y, max(0, altura - 8))
        w = max(8, min(w, largura - x))
        h = max(8, min(h, altura - y))
        return frame[y:y + h, x:x + w].copy(), (x, y, w, h)

    # ---------------------------------------------------------------- interno

    def _preparar(self, quadro: np.ndarray) -> np.ndarray:
        if self._espelhar:
            quadro = cv2.flip(quadro, 1)
        return quadro

    def _abrir(self) -> "cv2.VideoCapture | None":
        """Abre o dispositivo tentando os backends em ordem. Roda NA thread."""
        ultimo_erro = ""
        for backend in _ordem_backends(self._backend_nome):
            cap = None
            try:
                cap = cv2.VideoCapture(self._indice, backend)
                if not cap.isOpened():
                    cap.release()
                    ultimo_erro = "dispositivo nao abriu"
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._largura)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._altura)
                cap.set(cv2.CAP_PROP_FPS, self._fps_alvo)
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
                ok, quadro = cap.read()
                if not ok or quadro is None:
                    cap.release()
                    ultimo_erro = "a camera abriu mas nao entregou quadros"
                    continue
                # Alguns drivers montam o grafo de captura sem ligar o sensor:
                # os quadros chegam, mas todos pretos. Confere antes de aceitar.
                vivo = not _quadro_preto(quadro)
                for _ in range(QUADROS_CONFERENCIA):
                    if vivo:
                        break
                    ok_extra, extra = cap.read()
                    if ok_extra and not _quadro_preto(extra):
                        vivo = True
                        quadro = extra
                if not vivo:
                    cap.release()
                    ultimo_erro = "imagem preta"
                    continue
                self._largura_real = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or self._largura)
                self._altura_real = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or self._altura)
                with self._lock:
                    self._frame = self._preparar(quadro)
                return cap
            except Exception as exc:  # pragma: no cover - depende de hardware
                ultimo_erro = str(exc)
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
        if ultimo_erro in ("imagem preta", "a camera abriu mas nao entregou quadros"):
            # O dispositivo existe e o driver responde, mas o sensor nao liga.
            self._erro = AVISO_IMAGEM_PRETA
        else:
            self._erro = (
                f"Nao foi possivel abrir a camera {self._indice} ({ultimo_erro}). "
                "Verifique se ela esta conectada e se nenhum outro programa esta usando."
            )
        return None

    def _laco(self) -> None:
        cap = self._abrir()
        self._cap = cap
        self._ativa = cap is not None
        self._evt_aberta.set()
        if cap is None:
            return
        try:
            self._capturar(cap)
        finally:
            self._cap = None
            self._ativa = False
            try:
                cap.release()
            except Exception:
                pass

    def _capturar(self, cap: "cv2.VideoCapture") -> None:
        falhas = 0
        desde_preto: float | None = None
        marca = time.perf_counter()
        while not self._evt_parar.is_set():
            try:
                ok, quadro = cap.read()
            except Exception as exc:  # pragma: no cover - depende de hardware
                ok, quadro = False, None
                self._erro = f"falha ao ler a camera: {exc}"
            if not ok or quadro is None:
                falhas += 1
                if falhas >= 30:
                    self._erro = self._erro or "a camera parou de enviar quadros"
                    break
                time.sleep(0.02)
                continue
            falhas = 0
            if _quadro_preto(quadro):
                if desde_preto is None:
                    desde_preto = time.monotonic()
                elif (time.monotonic() - desde_preto) >= SEGUNDOS_PRETO_AVISO:
                    self._erro = AVISO_IMAGEM_PRETA
            else:
                desde_preto = None
                if self._erro == AVISO_IMAGEM_PRETA:
                    self._erro = None
            pronto = self._preparar(quadro)
            with self._lock:
                self._frame = pronto  # descarta o anterior: sempre o mais novo
            agora = time.perf_counter()
            dt = agora - marca
            marca = agora
            if dt > 0:
                inst = 1.0 / dt
                self._fps_real = inst if self._fps_real <= 0 else (
                    0.85 * self._fps_real + 0.15 * inst
                )


if __name__ == "__main__":  # usado por listar_dispositivos() como subprocesso
    _maximo = 5
    if "--listar" in sys.argv:
        _pos = sys.argv.index("--listar")
        if _pos + 1 < len(sys.argv):
            try:
                _maximo = int(sys.argv[_pos + 1])
            except ValueError:
                _maximo = 5
    try:
        _achados = _sondar_dispositivos(_maximo)
    except Exception:
        _achados = []
    print(json.dumps(_achados))
