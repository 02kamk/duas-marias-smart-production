"""API HTTP e streaming de video do Ponto Certo (FastAPI).

Arquitetura (importante):

    camera (thread A)  ->  motor (thread B)  ->  estado compartilhado  ->  rotas HTTP
                                                        |
                                                        +--> gerador MJPEG (so desenha)

Existe UMA unica thread de inferencia (o "motor"). Ela le o ultimo quadro da
camera, recorta a ROI, chama o Preditor, alimenta o SuavizadorTemporal, registra
eventos e guarda em memoria o quadro ja com overlay (codificado em JPEG) junto
com o ultimo veredito e o fps medido.

O gerador de /api/video nao infere nada: ele apenas repete o ultimo JPEG pronto.
E /api/status apenas le o estado compartilhado. Com isso nenhuma rota fica presa
esperando a inferencia, que e o bug classico quando a inferencia roda dentro do
gerador MJPEG (o /api/status trava enquanto o video roda).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import threading
import time
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

if __package__ in (None, ""):  # permite "python src/pontocerto/app/server.py"
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import Body, FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

from pontocerto.config import carregar_config, garantir_pasta
from pontocerto.labels import (
    CLASS_KEYS,
    CLASS_NAMES_PT,
    OK_INDEX,
    fabrics_payload,
    taxonomy_payload,
)
from pontocerto.app.camera import AVISO_IMAGEM_PRETA, Camera, listar_dispositivos
from pontocerto.app.state import EstadoSessao

VERSAO = "1.0.0"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
FPS_STREAM = 20.0

# ---------------------------------------------------------------------------
# Modulos escritos por outras partes do projeto. Se algum ainda nao existir (ou
# quebrar ao importar), o servidor sobe assim mesmo e informa o problema em
# /api/saude, em vez de devolver 500 em tudo.
# ---------------------------------------------------------------------------
IMPORTS_FALHOS: dict[str, str] = {}

try:
    from pontocerto.inference.predictor import Preditor  # type: ignore
except Exception as _exc:  # pragma: no cover
    Preditor = None  # type: ignore[assignment]
    IMPORTS_FALHOS["predictor"] = f"{type(_exc).__name__}: {_exc}"

try:
    from pontocerto.inference.smoothing import SuavizadorTemporal  # type: ignore
except Exception as _exc:  # pragma: no cover
    SuavizadorTemporal = None  # type: ignore[assignment]
    IMPORTS_FALHOS["smoothing"] = f"{type(_exc).__name__}: {_exc}"

try:
    from pontocerto.inference.gradcam import aplicar_mapa as _aplicar_mapa_ext  # type: ignore
except Exception as _exc:  # pragma: no cover
    _aplicar_mapa_ext = None  # type: ignore[assignment]
    IMPORTS_FALHOS["gradcam"] = f"{type(_exc).__name__}: {_exc}"

try:
    from pontocerto.llm.openrouter import ClienteOpenRouter  # type: ignore
except Exception as _exc:  # pragma: no cover
    ClienteOpenRouter = None  # type: ignore[assignment]
    IMPORTS_FALHOS["openrouter"] = f"{type(_exc).__name__}: {_exc}"

try:
    from pontocerto.llm.diagnosis import diagnosticar, gerar_relatorio  # type: ignore
except Exception as _exc:  # pragma: no cover
    diagnosticar = None  # type: ignore[assignment]
    gerar_relatorio = None  # type: ignore[assignment]
    IMPORTS_FALHOS["diagnosis"] = f"{type(_exc).__name__}: {_exc}"

try:
    from pontocerto.llm.review import revisar_predicao  # type: ignore
except Exception as _exc:  # pragma: no cover
    revisar_predicao = None  # type: ignore[assignment]
    IMPORTS_FALHOS["review"] = f"{type(_exc).__name__}: {_exc}"


# ---------------------------------------------------------------------------
# Paleta e desenho
# ---------------------------------------------------------------------------
TERRACOTA = (46, 80, 193)        # BGR do #C1502E
TERRACOTA_ESCURA = (31, 58, 124)  # BGR do #7C3A1F
OSSO = (233, 239, 244)            # BGR de um bege claro
VERDE_OK = (110, 160, 90)
CINZA = (120, 120, 120)
BRANCO = (255, 255, 255)

# cv2.putText nao desenha acento: usamos os nomes sem acento no overlay.
_PARADAS_MAPA = (
    (255, 255, 255),
    (247, 233, 226),
    (224, 130, 88),
    (193, 80, 46),
    (124, 58, 31),
)


def _ascii(texto: Any) -> str:
    return (
        unicodedata.normalize("NFKD", str(texto))
        .encode("ascii", "ignore")
        .decode("ascii")
    )


NOMES_ASCII: tuple[str, ...] = tuple(_ascii(n) for n in CLASS_NAMES_PT)


def _mapa_colorido_bgr(mapa: np.ndarray) -> np.ndarray:
    """Colormap quente proprio (branco -> terracota -> marrom), em BGR."""
    m = np.clip(np.asarray(mapa, dtype=np.float32), 0.0, 1.0)
    paradas = np.asarray(_PARADAS_MAPA, dtype=np.float32)
    n = len(paradas) - 1
    pos = m * n
    baixo = np.clip(np.floor(pos).astype(np.int32), 0, n - 1)
    t = (pos - baixo)[..., None]
    c0 = paradas[baixo]
    c1 = paradas[baixo + 1]
    rgb = c0 + (c1 - c0) * t
    return np.ascontiguousarray(rgb[..., ::-1].astype(np.uint8))


def aplicar_mapa_local(frame_bgr: np.ndarray, mapa: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    """Fallback local caso inference.gradcam nao esteja disponivel."""
    if mapa is None:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    m = np.asarray(mapa, dtype=np.float32)
    if m.shape[:2] != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    m = np.clip(m, 0.0, 1.0)
    cor = _mapa_colorido_bgr(m).astype(np.float32)
    peso = (m * float(alpha))[..., None]
    saida = frame_bgr.astype(np.float32) * (1.0 - peso) + cor * peso
    return np.clip(saida, 0, 255).astype(np.uint8)


def _misturar_gradcam(frame_bgr: np.ndarray, mapa: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    if _aplicar_mapa_ext is not None:
        try:
            return _aplicar_mapa_ext(frame_bgr, mapa, alpha)
        except Exception:
            pass
    return aplicar_mapa_local(frame_bgr, mapa, alpha)


def _cantos(img: np.ndarray, x: int, y: int, w: int, h: int, cor, tamanho: int = 28) -> None:
    e = max(3, tamanho)
    g = 3
    for (cx, cy, dx, dy) in (
        (x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)
    ):
        cv2.line(img, (cx, cy), (cx + dx * e, cy), cor, g, cv2.LINE_AA)
        cv2.line(img, (cx, cy), (cx, cy + dy * e), cor, g, cv2.LINE_AA)


def desenhar_overlay(
    frame_bgr: np.ndarray,
    caixa: tuple[int, int, int, int] | None,
    veredito: dict | None = None,
    mapa: np.ndarray | None = None,
    fps: float = 0.0,
    aviso: str | None = None,
) -> np.ndarray:
    """Devolve uma copia do quadro com ROI, Grad-CAM e faixa de status."""
    img = frame_bgr.copy()
    altura, largura = img.shape[:2]

    if caixa is not None:
        x, y, w, h = caixa
        x = max(0, min(x, largura - 2))
        y = max(0, min(y, altura - 2))
        w = max(2, min(w, largura - x))
        h = max(2, min(h, altura - y))
        if mapa is not None:
            try:
                recorte = img[y:y + h, x:x + w]
                img[y:y + h, x:x + w] = _misturar_gradcam(recorte, mapa, 0.45)
            except Exception:
                pass
        cv2.rectangle(img, (x, y), (x + w, y + h), TERRACOTA, 2, cv2.LINE_AA)
        _cantos(img, x, y, w, h, TERRACOTA, tamanho=max(18, min(w, h) // 8))

    faixa = max(54, int(altura * 0.085))
    cv2.rectangle(img, (0, altura - faixa), (largura, altura), TERRACOTA_ESCURA, -1)

    estado = (veredito or {}).get("estado", "aquecendo")
    nome = _ascii((veredito or {}).get("nome", "Aguardando"))
    conf = float((veredito or {}).get("confianca", 0.0) or 0.0)
    idx = int((veredito or {}).get("classe_idx", OK_INDEX) or 0)

    if aviso:
        texto = _ascii(aviso)
        cor_ponto = CINZA
    elif estado == "aquecendo":
        texto = "Analisando..."
        cor_ponto = OSSO
    elif estado == "falha":
        texto = f"FALHA: {nome} {conf * 100:.0f}%"
        cor_ponto = (80, 80, 235)
    elif estado == "incerto":
        texto = f"Incerto: {nome} {conf * 100:.0f}%"
        cor_ponto = (90, 190, 235)
    else:
        texto = f"{nome} {conf * 100:.0f}%"
        cor_ponto = VERDE_OK if idx == OK_INDEX else (80, 80, 235)

    base_y = altura - faixa // 2 + 8
    cv2.circle(img, (26, altura - faixa // 2), 9, cor_ponto, -1, cv2.LINE_AA)
    cv2.putText(img, texto, (48, base_y), cv2.FONT_HERSHEY_SIMPLEX,
                0.72, BRANCO, 2, cv2.LINE_AA)

    canto = f"PONTO CERTO  |  {fps:.1f} fps"
    (tw, _), _ = cv2.getTextSize(canto, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.putText(img, canto, (largura - tw - 16, base_y - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, OSSO, 1, cv2.LINE_AA)
    return img


def quadro_placeholder(largura: int = 960, altura: int = 540, mensagem: str = "Camera desligada") -> np.ndarray:
    """Imagem em memoria mostrada quando nao ha camera aberta."""
    img = np.full((altura, largura, 3), OSSO, dtype=np.uint8)
    cv2.rectangle(img, (18, 18), (largura - 18, altura - 18), TERRACOTA, 3, cv2.LINE_AA)
    _cantos(img, 18, 18, largura - 36, altura - 36, TERRACOTA, tamanho=46)
    msg = _ascii(mensagem)
    (tw, th), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 1.1, 2)
    cv2.putText(img, msg, ((largura - tw) // 2, (altura + th) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, TERRACOTA_ESCURA, 2, cv2.LINE_AA)
    sub = "Use o botao Ligar camera para comecar a inspecao"
    (sw, _), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.putText(img, sub, ((largura - sw) // 2, (altura + th) // 2 + 42),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 110, 105), 1, cv2.LINE_AA)
    return img


def _para_jpeg(img: np.ndarray, qualidade: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(qualidade)])
    if not ok:
        return b""
    return buf.tobytes()


def _data_uri(img: np.ndarray, qualidade: int = 85) -> str:
    dados = _para_jpeg(img, qualidade)
    return "data:image/jpeg;base64," + base64.b64encode(dados).decode("ascii")


def _veredito_padrao(mensagem: str = "aquecendo") -> dict:
    return {
        "estado": mensagem,
        "classe_idx": OK_INDEX,
        "classe_key": CLASS_KEYS[OK_INDEX],
        "nome": CLASS_NAMES_PT[OK_INDEX],
        "confianca": 0.0,
        "estavel": False,
        "novo_evento": False,
        "pede_llm": False,
    }


def _como_dict(obj: Any) -> dict | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    try:
        return dict(obj.__dict__)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Motor de inferencia (thread unica)
# ---------------------------------------------------------------------------
class Motor:
    """Thread de fundo: camera -> ROI -> preditor -> suavizador -> overlay."""

    def __init__(self, cfg: Any, camera: Camera, preditor: Any, estado: EstadoSessao) -> None:
        self.cfg = cfg
        self.camera = camera
        self.preditor = preditor
        self.estado = estado
        self.tecido: str | None = None
        self.gradcam = bool(cfg.inferencia.get("gradcam", True))

        self._lock = threading.Lock()
        self._evt_parar = threading.Event()
        self._thread: threading.Thread | None = None

        self._suavizador = self._novo_suavizador()
        self._jpeg = _para_jpeg(quadro_placeholder())
        self._veredito = _veredito_padrao()
        self._predicao: dict | None = None
        self._ultimo_evento: dict | None = None
        self._fps = 0.0
        self._erro: str | None = None

    # ---------------------------------------------------------------- ciclo
    def _novo_suavizador(self):
        if SuavizadorTemporal is None:
            return None
        try:
            return SuavizadorTemporal(self.cfg)
        except Exception as exc:  # pragma: no cover
            self._erro = f"suavizador indisponivel: {exc}"
            return None

    def reconfigurar(self) -> None:
        """Recria o suavizador depois de um POST /api/ajustes."""
        novo = self._novo_suavizador()
        with self._lock:
            self._suavizador = novo
            self._veredito = _veredito_padrao()

    def iniciar(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._evt_parar.clear()
        self._thread = threading.Thread(target=self._laco, name="pontocerto-motor", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._evt_parar.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)

    # --------------------------------------------------------------- leitura
    @property
    def encerrando(self) -> bool:
        """True depois de parar(): faz o gerador MJPEG terminar no shutdown."""
        return self._evt_parar.is_set()

    def ultimo_jpeg(self) -> bytes:
        with self._lock:
            return self._jpeg

    def instantaneo(self) -> dict:
        with self._lock:
            return {
                "veredito": dict(self._veredito) if self._veredito else _veredito_padrao(),
                "predicao": dict(self._predicao) if self._predicao else None,
                "ultimo_evento": dict(self._ultimo_evento) if self._ultimo_evento else None,
                "fps": round(float(self._fps), 1),
                "erro": self._erro,
                "gradcam": bool(self.gradcam),
            }

    def _publicar(self, jpeg: bytes, veredito: dict | None, predicao: dict | None) -> None:
        with self._lock:
            if jpeg:
                self._jpeg = jpeg
            if veredito is not None:
                self._veredito = veredito
            self._predicao = predicao

    # ----------------------------------------------------------------- laco
    def _laco(self) -> None:
        marca = time.perf_counter()
        placeholder_cache: bytes | None = None
        while not self._evt_parar.is_set():
            inicio = time.perf_counter()
            frame = self.camera.ler() if self.camera.ativa else None

            if frame is None:
                msg = "Camera desligada" if not self.camera.ativa else "Aguardando quadros"
                if placeholder_cache is None:
                    placeholder_cache = _para_jpeg(quadro_placeholder(mensagem=msg))
                with self._lock:
                    self._jpeg = placeholder_cache
                    self._fps = 0.0
                    self._predicao = None
                    self._veredito = _veredito_padrao()
                self._evt_parar.wait(0.20)
                continue
            placeholder_cache = None

            try:
                recorte, caixa = self.camera.recortar_roi(frame)
            except Exception:
                recorte, caixa = frame, None

            predicao_dict: dict | None = None
            veredito_dict: dict | None = None
            mapa = None
            aviso = None

            disponivel = bool(getattr(self.preditor, "disponivel", False))
            if self.camera.erro == AVISO_IMAGEM_PRETA:
                # Inferir em cima de preto so produz palpite: melhor avisar.
                aviso = "Imagem preta - verifique o obturador da webcam"
            elif not disponivel:
                aviso = "Modelo nao carregado - treine em scripts/02_treinar.py"
            else:
                try:
                    predicao, mapa = self.preditor.prever_bgr(
                        recorte, com_gradcam=bool(self.gradcam)
                    )
                    predicao_dict = _como_dict(predicao)
                except Exception as exc:
                    self._erro = f"falha na inferencia: {exc}"
                    aviso = "Falha na inferencia"
                    predicao_dict = None

            if predicao_dict is not None and self._suavizador is not None:
                try:
                    probs = np.asarray(predicao_dict.get("probabilidades", []), dtype=np.float32)
                    veredito = self._suavizador.atualizar(probs)
                    veredito_dict = _como_dict(veredito)
                except Exception as exc:
                    self._erro = f"falha na suavizacao: {exc}"
                    veredito_dict = None
            elif predicao_dict is not None:
                # Sem suavizador: usa a predicao crua para nao deixar a tela muda.
                veredito_dict = {
                    "estado": "falha" if predicao_dict.get("e_falha") else "ok",
                    "classe_idx": predicao_dict.get("classe_idx", OK_INDEX),
                    "classe_key": predicao_dict.get("classe_key", CLASS_KEYS[OK_INDEX]),
                    "nome": predicao_dict.get("nome", CLASS_NAMES_PT[OK_INDEX]),
                    "confianca": predicao_dict.get("confianca", 0.0),
                    "estavel": False,
                    "novo_evento": False,
                    "pede_llm": False,
                }

            if veredito_dict and veredito_dict.get("novo_evento") and predicao_dict:
                try:
                    evento = self.estado.registrar_evento(
                        predicao_dict, frame_bgr=recorte, tecido=self.tecido
                    )
                    with self._lock:
                        self._ultimo_evento = evento.to_dict()
                except Exception as exc:
                    self._erro = f"falha ao registrar evento: {exc}"

            try:
                overlay = desenhar_overlay(
                    frame, caixa, veredito_dict, mapa if self.gradcam else None,
                    fps=self._fps, aviso=aviso,
                )
                jpeg = _para_jpeg(overlay)
            except Exception as exc:
                self._erro = f"falha no overlay: {exc}"
                jpeg = _para_jpeg(frame)

            self._publicar(jpeg, veredito_dict, predicao_dict)

            agora = time.perf_counter()
            dt = agora - marca
            marca = agora
            if dt > 0:
                inst = 1.0 / dt
                with self._lock:
                    self._fps = inst if self._fps <= 0 else (0.8 * self._fps + 0.2 * inst)

            gasto = time.perf_counter() - inicio
            self._evt_parar.wait(max(0.0, 0.033 - gasto))


# ---------------------------------------------------------------------------
# Aplicacao
# ---------------------------------------------------------------------------
PASTA_APP = Path(__file__).resolve().parent
PASTA_STATIC = PASTA_APP / "static"

HTML_AVISO = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Ponto Certo</title>
<style>
 body{margin:0;font-family:system-ui,Segoe UI,Arial,sans-serif;background:#F7F3EE;color:#3B2B23;
      display:flex;min-height:100vh;align-items:center;justify-content:center}
 .caixa{max-width:36rem;padding:2rem;border:2px solid #C1502E;border-radius:14px;background:#fff}
 h1{margin:0 0 .5rem;color:#C1502E} code{background:#F7E9E2;padding:.1rem .3rem;border-radius:4px}
</style></head><body><div class="caixa">
<h1>Ponto Certo</h1>
<p>A API esta no ar, mas a interface (<code>src/pontocerto/app/static/index.html</code>)
ainda nao foi encontrada.</p>
<p>Teste a API em <code>/api/saude</code>, <code>/api/status</code> ou <code>/docs</code>.</p>
</div></body></html>"""


def _ler_json(caminho: str | Path) -> Any:
    try:
        p = Path(caminho)
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def criar_app(cfg: Any = None) -> FastAPI:
    """Monta a aplicacao FastAPI completa."""
    cfg = cfg if cfg is not None else carregar_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- subida -------------------------------------------------------
        app.state.cfg = cfg
        app.state.erros_import = dict(IMPORTS_FALHOS)

        app.state.estado = EstadoSessao(cfg)
        app.state.camera = Camera(cfg)

        if Preditor is not None:
            try:
                app.state.preditor = Preditor(cfg)
            except Exception as exc:  # o contrato diz que nao deve estourar
                app.state.preditor = _PreditorAusente(f"{type(exc).__name__}: {exc}")
        else:
            app.state.preditor = _PreditorAusente(
                IMPORTS_FALHOS.get("predictor", "modulo predictor indisponivel")
            )

        if ClienteOpenRouter is not None:
            try:
                app.state.cliente = ClienteOpenRouter(cfg)
            except Exception as exc:
                app.state.cliente = None
                app.state.erros_import["openrouter"] = f"{type(exc).__name__}: {exc}"
        else:
            app.state.cliente = None

        app.state.motor = Motor(cfg, app.state.camera, app.state.preditor, app.state.estado)
        app.state.motor.iniciar()  # a camera NAO e aberta automaticamente
        try:
            yield
        finally:
            # --- descida --------------------------------------------------
            try:
                app.state.motor.parar()
            except Exception:
                pass
            try:
                app.state.camera.parar()
            except Exception:
                pass

    app = FastAPI(
        title=str(cfg.app.get("titulo", "Ponto Certo")),
        description="Inspecao de costura em tempo real - API do Ponto Certo",
        version=VERSAO,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    pasta_capturas = garantir_pasta(cfg.app.pasta_capturas)
    garantir_pasta(cfg.app.pasta_relatorios)
    garantir_pasta(PASTA_STATIC)
    app.mount("/capturas", StaticFiles(directory=str(pasta_capturas)), name="capturas")
    app.mount("/static", StaticFiles(directory=str(PASTA_STATIC)), name="static")

    # ------------------------------------------------------------- pagina
    @app.get("/", include_in_schema=False)
    def raiz():
        index = PASTA_STATIC / "index.html"
        if index.exists():
            return FileResponse(str(index), media_type="text/html")
        return HTMLResponse(HTML_AVISO)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        icone = PASTA_STATIC / "favicon.ico"
        if icone.exists():
            return FileResponse(str(icone))
        # 204 nao pode ter corpo: devolver JSON aqui quebra o ASGI
        # ("Response content longer than Content-Length").
        return Response(status_code=204)

    # -------------------------------------------------------------- saude
    @app.get("/api/saude")
    def saude():
        preditor = app.state.preditor
        meta = {}
        try:
            meta = dict(getattr(preditor, "meta", {}) or {})
        except Exception:
            meta = {}
        cliente = app.state.cliente
        return {
            "ok": True,
            "modelo": {
                "carregado": bool(getattr(preditor, "disponivel", False)),
                "erro": getattr(preditor, "erro", None),
                "backbone": meta.get("backbone"),
                "metricas": meta.get("metricas") or {},
            },
            "camera": app.state.camera.info(),
            "llm": {
                "configurado": bool(getattr(cliente, "configurado", False)),
                "modelo": str(cfg.llm.get("modelo_visao", "")) if cliente is not None else None,
            },
            "versao": VERSAO,
            "modulos_indisponiveis": app.state.erros_import,
        }

    @app.get("/api/taxonomia")
    def taxonomia():
        return {"classes": taxonomy_payload(), "tecidos": fabrics_payload()}

    # ------------------------------------------------------------ ajustes
    @app.get("/api/ajustes")
    def ler_ajustes():
        inf = cfg.inferencia
        return {
            "ema_alpha": float(inf.get("ema_alpha", 0.45)),
            "frames_para_confirmar": int(inf.get("frames_para_confirmar", 4)),
            "limiar_alerta": float(inf.get("limiar_alerta", 0.55)),
            "limiar_incerteza": float(inf.get("limiar_incerteza", 0.70)),
            "cooldown_evento_s": float(inf.get("cooldown_evento_s", 3.0)),
            "gradcam": bool(app.state.motor.gradcam),
            "meta_pecas": int(app.state.estado.meta_pecas),
            "tecido": app.state.motor.tecido,
        }

    @app.post("/api/ajustes")
    def aplicar_ajustes(corpo: dict = Body(default={})):
        corpo = corpo or {}
        inf = cfg.inferencia
        numericos = {
            "ema_alpha": (float, 0.01, 1.0),
            "limiar_alerta": (float, 0.05, 0.999),
            "limiar_incerteza": (float, 0.05, 0.999),
            "cooldown_evento_s": (float, 0.0, 120.0),
            "frames_para_confirmar": (int, 1, 60),
        }
        mudou_suavizador = False
        for chave, (tipo, minimo, maximo) in numericos.items():
            if chave in corpo and corpo[chave] is not None:
                try:
                    valor = tipo(corpo[chave])
                except (TypeError, ValueError):
                    continue
                inf[chave] = type(valor)(max(minimo, min(maximo, valor)))
                mudou_suavizador = True
        if "gradcam" in corpo:
            app.state.motor.gradcam = bool(corpo["gradcam"])
            inf["gradcam"] = bool(corpo["gradcam"])
        if "meta_pecas" in corpo and corpo["meta_pecas"] is not None:
            try:
                app.state.estado.definir_meta(int(corpo["meta_pecas"]))
            except (TypeError, ValueError):
                pass
        if "tecido" in corpo:
            tecido = corpo["tecido"]
            app.state.motor.tecido = str(tecido) if tecido else None
        if mudou_suavizador:
            app.state.motor.reconfigurar()
        return ler_ajustes()

    # ------------------------------------------------------------- camera
    @app.get("/api/camera/dispositivos")
    def dispositivos():
        try:
            return {"dispositivos": listar_dispositivos(5)}
        except Exception as exc:
            return {"dispositivos": [], "erro": str(exc)}

    @app.post("/api/camera/iniciar")
    def camera_iniciar(corpo: dict = Body(default={})):
        corpo = corpo or {}
        indice = corpo.get("indice")
        try:
            indice = int(indice) if indice is not None else None
        except (TypeError, ValueError):
            indice = None
        try:
            ok = app.state.camera.iniciar(indice)
        except Exception as exc:
            return {"ok": False, "camera": app.state.camera.info(), "erro": str(exc)}
        if ok:
            app.state.motor.reconfigurar()
        return {"ok": bool(ok), "camera": app.state.camera.info()}

    @app.post("/api/camera/parar")
    def camera_parar():
        try:
            app.state.camera.parar()
        except Exception as exc:
            return {"ok": False, "erro": str(exc)}
        return {"ok": True}

    # -------------------------------------------------------------- video
    @app.get("/api/video")
    def video():
        motor: Motor = app.state.motor

        def gerador():
            intervalo = 1.0 / FPS_STREAM
            while not motor.encerrando:
                inicio = time.perf_counter()
                quadro = motor.ultimo_jpeg()
                if quadro:
                    yield (
                        b"--quadro\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(quadro)).encode("ascii") + b"\r\n\r\n"
                        + quadro + b"\r\n"
                    )
                gasto = time.perf_counter() - inicio
                time.sleep(max(0.0, intervalo - gasto))

        return StreamingResponse(
            gerador(),
            media_type="multipart/x-mixed-replace; boundary=quadro",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
        )

    # ------------------------------------------------------------- status
    @app.get("/api/status")
    def status():
        instantaneo = app.state.motor.instantaneo()
        return {
            "veredito": instantaneo["veredito"],
            "predicao": instantaneo["predicao"],
            "estatisticas": app.state.estado.estatisticas(),
            "ultimo_evento": instantaneo["ultimo_evento"],
            "camera": app.state.camera.info(),
            "fps": instantaneo["fps"],
            "gradcam": instantaneo["gradcam"],
            "erro": instantaneo["erro"],
        }

    @app.post("/api/gradcam")
    def alternar_gradcam(corpo: dict = Body(default={})):
        corpo = corpo or {}
        ligado = corpo.get("ligado")
        if ligado is None:
            ligado = not app.state.motor.gradcam
        app.state.motor.gradcam = bool(ligado)
        cfg.inferencia["gradcam"] = bool(ligado)
        return {"ok": True, "ligado": bool(app.state.motor.gradcam)}

    # ----------------------------------------------------------- analisar
    @app.post("/api/analisar")
    async def analisar(arquivo: UploadFile = File(...)):
        dados = b""
        try:
            while True:
                pedaco = await arquivo.read(1 << 20)
                if not pedaco:
                    break
                dados += pedaco
                if len(dados) > MAX_UPLOAD_BYTES:
                    return {"erro": "Imagem muito grande (limite de 10 MB)."}
        except Exception as exc:
            return {"erro": f"Falha ao ler o arquivo enviado: {exc}"}
        finally:
            try:
                await arquivo.close()
            except Exception:
                pass

        if not dados:
            return {"erro": "Arquivo vazio."}

        try:
            frame = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            frame = None
        if frame is None or frame.size == 0:
            return {"erro": "Nao foi possivel decodificar a imagem (envie JPG ou PNG)."}

        preditor = app.state.preditor
        if not getattr(preditor, "disponivel", False):
            return {"erro": getattr(preditor, "erro", None) or "Modelo nao carregado."}

        try:
            predicao, mapa = preditor.prever_bgr(frame, com_gradcam=True)
        except Exception as exc:
            return {"erro": f"Falha na inferencia: {exc}"}

        predicao_dict = _como_dict(predicao) or {}
        if mapa is not None:
            try:
                heat = _misturar_gradcam(frame, mapa, 0.5)
            except Exception:
                heat = frame
        else:
            heat = frame

        return {
            "predicao": predicao_dict,
            "heatmap": _data_uri(heat),
            "imagem": _data_uri(frame),
        }

    # ------------------------------------------------------------ eventos
    @app.get("/api/eventos")
    def listar_eventos(limite: int = Query(60, ge=1, le=500), classe: str | None = None):
        return {
            "eventos": app.state.estado.eventos(limite=limite, classe=classe),
            "estatisticas": app.state.estado.estatisticas(),
        }

    @app.post("/api/eventos/{evento_id}/rotulo")
    def rotular(evento_id: str, corpo: dict = Body(default={})):
        corpo = corpo or {}
        classe_key = str(corpo.get("classe_key", "")).strip()
        if classe_key not in CLASS_KEYS:
            return {"ok": False, "erro": f"classe_key invalida: '{classe_key}'"}
        ok = app.state.estado.corrigir_rotulo(evento_id, classe_key)
        return {"ok": bool(ok)} if ok else {"ok": False, "erro": "evento nao encontrado"}

    @app.post("/api/eventos/{evento_id}/diagnostico")
    def diagnostico_evento(evento_id: str, corpo: dict = Body(default={})):
        corpo = corpo or {}
        evento = app.state.estado.evento(evento_id)
        if evento is None:
            return {"erro": "evento nao encontrado"}
        if diagnosticar is None:
            return {"erro": "modulo de diagnostico indisponivel: "
                            + IMPORTS_FALHOS.get("diagnosis", "")}
        usar_llm = bool(corpo.get("usar_llm", True)) and bool(cfg.llm.get("ativo", True))
        try:
            resultado = diagnosticar(
                app.state.cliente,
                evento.classe_key,
                tecido=evento.tecido or app.state.motor.tecido,
                confianca=evento.confianca,
                usar_llm=usar_llm,
            )
        except Exception as exc:
            return {"erro": f"falha ao diagnosticar: {exc}"}
        app.state.estado.anexar_diagnostico(evento_id, resultado)
        return {"diagnostico": resultado}

    @app.post("/api/diagnostico")
    def diagnostico_avulso(corpo: dict = Body(default={})):
        """Diagnostico por classe, sem evento associado.

        A aba "Testar" analisa uma imagem enviada pelo operador: nao existe
        evento na sessao para pendurar o diagnostico, entao o pedido vem so com
        a classe prevista. Mesma logica de /api/eventos/{id}/diagnostico, sem o
        passo de anexar ao historico.
        """
        corpo = corpo or {}
        classe_key = str(corpo.get("classe_key", "")).strip()
        if classe_key not in CLASS_KEYS:
            return {"erro": f"classe_key invalida: '{classe_key}'"}
        if diagnosticar is None:
            return {"erro": "modulo de diagnostico indisponivel: "
                            + IMPORTS_FALHOS.get("diagnosis", "")}
        confianca = corpo.get("confianca")
        try:
            confianca = float(confianca) if confianca is not None else None
        except (TypeError, ValueError):
            confianca = None
        tecido = corpo.get("tecido") or app.state.motor.tecido
        usar_llm = bool(corpo.get("usar_llm", True)) and bool(cfg.llm.get("ativo", True))
        try:
            resultado = diagnosticar(
                app.state.cliente, classe_key,
                tecido=tecido, confianca=confianca, usar_llm=usar_llm,
            )
        except Exception as exc:
            return {"erro": f"falha ao diagnosticar: {exc}"}
        return {"diagnostico": resultado}

    @app.post("/api/eventos/{evento_id}/revisao")
    def revisao_evento(evento_id: str):
        evento = app.state.estado.evento(evento_id)
        if evento is None:
            return {"erro": "evento nao encontrado"}
        if revisar_predicao is None:
            return {"erro": "modulo de revisao indisponivel: "
                            + IMPORTS_FALHOS.get("review", "")}
        if app.state.cliente is None or not getattr(app.state.cliente, "configurado", False):
            return {"erro": "LLM nao configurado: defina OPENROUTER_API_KEY no arquivo .env"}
        caminho = app.state.estado.caminho_captura(evento)
        if caminho is None:
            return {"erro": "captura do evento nao encontrada em disco"}
        try:
            imagem = Path(caminho).read_bytes()
        except Exception as exc:
            return {"erro": f"falha ao ler a captura: {exc}"}
        predicao_dict = {
            "classe_idx": evento.classe_idx,
            "classe_key": evento.classe_key,
            "nome": evento.nome,
            "confianca": evento.confianca,
            "gravidade": evento.gravidade,
            "e_falha": evento.classe_idx != OK_INDEX,
        }
        try:
            resultado = revisar_predicao(
                app.state.cliente, imagem, predicao_dict,
                tecido=evento.tecido or app.state.motor.tecido,
            )
        except Exception as exc:
            return {"erro": f"falha na revisao: {exc}"}
        app.state.estado.anexar_revisao(evento_id, resultado)
        return {"revisao": resultado}

    # ----------------------------------------------------------------- LLM
    @app.get("/api/llm/status")
    def llm_status():
        cliente = app.state.cliente
        if cliente is None:
            return {
                "ok": False,
                "mensagem": "cliente do OpenRouter indisponivel: "
                            + IMPORTS_FALHOS.get("openrouter", "modulo nao carregado"),
                "modelo_visao": str(cfg.llm.get("modelo_visao", "")),
                "creditos": None,
                "estatisticas": {},
                "ativo": bool(cfg.llm.get("ativo", True)),
            }
        try:
            resultado = dict(cliente.checar() or {})
        except Exception as exc:
            resultado = {
                "ok": False,
                "mensagem": f"falha ao consultar o OpenRouter: {exc}",
                "modelo_visao": str(cfg.llm.get("modelo_visao", "")),
                "creditos": None,
            }
        try:
            resultado["estatisticas"] = dict(cliente.estatisticas or {})
        except Exception:
            resultado["estatisticas"] = {}
        resultado["configurado"] = bool(getattr(cliente, "configurado", False))
        resultado["ativo"] = bool(cfg.llm.get("ativo", True))
        return resultado

    # ----------------------------------------------------------- relatorio
    @app.post("/api/relatorio")
    def relatorio(corpo: dict = Body(default={})):
        corpo = corpo or {}
        estatisticas = app.state.estado.estatisticas()
        eventos = app.state.estado.eventos(limite=int(corpo.get("limite", 200) or 200))
        usar_llm = bool(corpo.get("usar_llm", True)) and bool(cfg.llm.get("ativo", True))
        if gerar_relatorio is None:
            return {"erro": "modulo de relatorio indisponivel: "
                            + IMPORTS_FALHOS.get("diagnosis", "")}
        try:
            resultado = gerar_relatorio(
                app.state.cliente, estatisticas, eventos, usar_llm=usar_llm
            ) or {}
        except Exception as exc:
            return {"erro": f"falha ao gerar o relatorio: {exc}"}
        markdown = str(resultado.get("markdown", ""))
        arquivo = ""
        try:
            pasta = garantir_pasta(cfg.app.pasta_relatorios)
            destino = pasta / f"relatorio_{datetime.now():%Y%m%d_%H%M%S}.md"
            destino.write_text(markdown, encoding="utf-8")
            arquivo = str(destino)
        except Exception:
            arquivo = ""
        return {
            "markdown": markdown,
            "arquivo": arquivo,
            "fonte": resultado.get("fonte"),
            "modelo": resultado.get("modelo"),
        }

    # ------------------------------------------------------------- treino
    @app.get("/api/treino/historico")
    def treino_historico():
        historico = _ler_json(cfg.treino.historico)
        metricas = _ler_json(Path(cfg.avaliacao.saida_dir) / "metricas.json")
        if historico is None and metricas is None:
            return {}
        return {
            "historico": historico or [],
            "metricas": metricas or {},
        }

    return app


class _PreditorAusente:
    """Substituto usado quando inference.predictor nao pode ser importado."""

    def __init__(self, erro: str) -> None:
        self._erro = erro

    @property
    def disponivel(self) -> bool:
        return False

    @property
    def erro(self) -> str:
        return self._erro

    @property
    def meta(self) -> dict:
        return {}

    def prever_bgr(self, *args, **kwargs):
        raise RuntimeError(self._erro)

    def prever_tensor(self, *args, **kwargs):
        raise RuntimeError(self._erro)

    def prever_arquivo(self, *args, **kwargs):
        raise RuntimeError(self._erro)

    def prever_bytes(self, *args, **kwargs):
        raise RuntimeError(self._erro)

    def recarregar(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    cfg = carregar_config()
    parser = argparse.ArgumentParser(
        prog="pontocerto-servidor",
        description="Sobe a interface e a API do Ponto Certo.",
    )
    parser.add_argument("--host", default=str(cfg.app.get("host", "127.0.0.1")),
                        help="endereco de escuta (padrao: %(default)s)")
    parser.add_argument("--porta", type=int, default=int(cfg.app.get("porta", 8000)),
                        help="porta TCP (padrao: %(default)s)")
    parser.add_argument("--recarregar", action="store_true",
                        help="recarrega o servidor quando o codigo mudar (desenvolvimento)")
    args = parser.parse_args(argv)

    import uvicorn

    print(f"Ponto Certo em http://{args.host}:{args.porta}  (Ctrl+C para encerrar)")
    if args.recarregar:
        uvicorn.run(
            "pontocerto.app.server:criar_app",
            factory=True,
            host=args.host,
            port=args.porta,
            reload=True,
            reload_dirs=[str(Path(__file__).resolve().parents[2])],
        )
    else:
        uvicorn.run(criar_app(cfg), host=args.host, port=args.porta, log_level="info")


if __name__ == "__main__":
    main()
