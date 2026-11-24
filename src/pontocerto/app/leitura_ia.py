"""Leitura das peças pela IA de visão, com limite diário de chamadas e registro do gasto."""
from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from pontocerto.labels import class_by_key

# Leitura "incerta" fica abaixo do limiar de conferência e vai para Conferir.
CONFIANCA_INCERTA = 0.5


class LeituraIA:
    def __init__(self, cfg: Any, cliente: Callable[[], Any], arquivo_uso: Path, nuvem: bool = False) -> None:
        llm = cfg.llm
        self.ativa = bool(llm.get("leitura_ia", True))
        self._limite = int(llm.get("leitura_limite_diario", 400))
        self._nuvem = nuvem
        self._cliente = cliente
        self._arquivo = Path(arquivo_uso)
        self._lock = threading.Lock()

    # Online o limite e o gasto valem para todas as máquinas (pc_config no Supabase).
    @property
    def limite_diario(self) -> int:
        if self._nuvem:
            from pontocerto import nuvem
            ajustes = nuvem.ler("ajustes", {}) or {}
            return int(ajustes.get("leitura_limite_diario", self._limite))
        return self._limite

    @limite_diario.setter
    def limite_diario(self, valor: int) -> None:
        self._limite = int(valor)

    # ------------------------------------------------------------ uso do dia
    def _ler_uso(self) -> dict:
        hoje = date.today().isoformat()
        if self._nuvem:
            from pontocerto import nuvem
            u = nuvem.ler("uso_ia", None, cache_s=0) or {}
            if u.get("data") == hoje:
                return {"data": hoje, "chamadas": int(u.get("chamadas", 0)), "custo_usd": float(u.get("custo_usd", 0))}
            return {"data": hoje, "chamadas": 0, "custo_usd": 0.0}
        try:
            dados = json.loads(self._arquivo.read_text(encoding="utf-8"))
            if dados.get("data") == hoje:
                return dados
        except Exception:
            pass
        return {"data": hoje, "chamadas": 0, "custo_usd": 0.0}

    def uso(self) -> dict:
        with self._lock:
            u = self._ler_uso()
        return {**u, "limite": self.limite_diario, "restantes": max(0, self.limite_diario - u["chamadas"])}

    def _somar(self, custo: float) -> None:
        if self._nuvem:
            from pontocerto import nuvem
            nuvem.somar_uso_ia(date.today().isoformat(), float(custo or 0))
            return
        with self._lock:
            u = self._ler_uso()
            u["chamadas"] += 1
            u["custo_usd"] = round(u["custo_usd"] + float(custo or 0), 6)
            self._arquivo.parent.mkdir(parents=True, exist_ok=True)
            self._arquivo.write_text(json.dumps(u), encoding="utf-8")

    # ---------------------------------------------------------------- estado
    def motivo_indisponivel(self) -> str | None:
        if not self.ativa:
            return "Leitura por IA desligada no config.yaml (llm.leitura_ia)."
        cliente = self._cliente()
        if cliente is None or not getattr(cliente, "configurado", False):
            return "Sem OPENROUTER_API_KEY no .env."
        if self.uso()["restantes"] <= 0:
            return f"Limite de {self.limite_diario} leituras por IA hoje atingido."
        return None

    @property
    def disponivel(self) -> bool:
        return self.motivo_indisponivel() is None

    # ----------------------------------------------------------------- leitura
    def ler(self, frame_bgr: np.ndarray) -> tuple[dict, np.ndarray, dict]:
        """Devolve (predição no formato do sistema, foto com o defeito marcado, leitura da IA)."""
        from pontocerto.llm.leitor import ler_peca

        leitura = ler_peca(self._cliente(), frame_bgr)
        self._somar(leitura.get("custo_usd", 0.0))
        info = class_by_key(leitura["classe"])
        confianca = leitura["confianca"]
        if leitura["veredito"] == "incerta":
            confianca = min(confianca, CONFIANCA_INCERTA)
        predicao = {
            "classe_idx": info.index, "classe_key": info.key, "nome": info.pt,
            "confianca": float(confianca), "gravidade": info.gravidade,
            "e_falha": info.key != "normal", "ms": float(leitura.get("ms", 0)),
            "top": [{"index": info.index, "key": info.key, "nome": info.pt, "prob": float(confianca)}],
            "fonte": "ia", "leitura": {k: leitura.get(k) for k in (
                "veredito", "classe", "nome", "confianca", "onde", "explicacao", "modelo", "ms", "custo_usd")},
        }
        return predicao, marcar(frame_bgr, leitura.get("onde")), leitura


def marcar(frame_bgr: np.ndarray, onde: dict | None) -> np.ndarray:
    """Desenha a caixa do defeito (com folga) sobre a foto, em vermelho com borda branca."""
    if not onde:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    folga = 0.02
    x0 = int(max(0, onde["x"] - folga) * w)
    y0 = int(max(0, onde["y"] - folga) * h)
    x1 = int(min(1, onde["x"] + onde["largura"] + folga) * w)
    y1 = int(min(1, onde["y"] + onde["altura"] + folga) * h)
    espessura = max(3, int(min(h, w) / 160))
    vis = frame_bgr.copy()
    cv2.rectangle(vis, (x0, y0), (x1, y1), (255, 255, 255), espessura + 4)
    cv2.rectangle(vis, (x0, y0), (x1, y1), (47, 24, 163), espessura)
    return vis
