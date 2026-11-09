"""Estado da sessao de inspecao (eventos, estatisticas e correcoes).

Tudo que a interface mostra no painel sai daqui. A classe e usada por duas
threads ao mesmo tempo (a thread do motor de inferencia escreve, as rotas HTTP
leem), entao todo acesso passa por um unico Lock.
"""

from __future__ import annotations

import csv
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from pontocerto.config import garantir_pasta
from pontocerto.labels import CLASS_KEYS, OK_INDEX, class_by_index, class_by_key

__all__ = ["Evento", "EstadoSessao"]

META_PECAS_PADRAO = 50


@dataclass
class Evento:
    """Uma deteccao confirmada pelo suavizador temporal."""

    id: str
    timestamp: float
    hora: str
    classe_idx: int
    classe_key: str
    nome: str
    confianca: float
    gravidade: str
    tecido: str | None = None
    imagem: str | None = None
    diagnostico: dict | None = None
    revisao_llm: dict | None = None
    rotulo_operador: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "hora": self.hora,
            "classe_idx": int(self.classe_idx),
            "classe_key": self.classe_key,
            "nome": self.nome,
            "confianca": float(self.confianca),
            "gravidade": self.gravidade,
            "tecido": self.tecido,
            "imagem": self.imagem,
            "diagnostico": self.diagnostico,
            "revisao_llm": self.revisao_llm,
            "rotulo_operador": self.rotulo_operador,
            "e_falha": int(self.classe_idx) != OK_INDEX,
        }


class EstadoSessao:
    """Historico da sessao atual, em memoria, com capturas salvas em disco."""

    def __init__(self, cfg: Any) -> None:
        self._cfg = cfg
        app = cfg.app
        self._max_eventos = int(app.get("max_eventos_memoria", 300))
        self._pasta_capturas = Path(app.pasta_capturas)
        self._arquivo_correcoes = Path(app.correcoes)
        self._lock = threading.RLock()
        self._eventos: deque[Evento] = deque(maxlen=self._max_eventos)
        self._indice: dict[str, Evento] = {}
        self._inicio = time.time()
        self._total = 0
        self._aprovadas = 0
        self._reprovadas = 0
        self._sequencia_ok = 0
        self._melhor_sequencia = 0
        self._por_classe: dict[str, int] = {k: 0 for k in CLASS_KEYS}
        self.meta_pecas = int(app.get("meta_pecas", META_PECAS_PADRAO))
        try:
            garantir_pasta(self._pasta_capturas)
        except Exception:
            pass

    # ------------------------------------------------------------- registrar

    def registrar_evento(
        self,
        predicao_dict: dict,
        frame_bgr: np.ndarray | None = None,
        tecido: str | None = None,
    ) -> Evento:
        """Cria o evento, salva o JPG da captura e atualiza as estatisticas."""
        agora = time.time()
        idx = int(predicao_dict.get("classe_idx", OK_INDEX))
        try:
            info = class_by_index(idx)
            key = info.key
            nome = predicao_dict.get("nome") or info.pt
            gravidade = predicao_dict.get("gravidade") or info.gravidade
        except Exception:
            key = str(predicao_dict.get("classe_key", "normal"))
            nome = str(predicao_dict.get("nome", key))
            gravidade = str(predicao_dict.get("gravidade", "media"))

        evento_id = uuid.uuid4().hex[:12]
        imagem_url = self._salvar_captura(evento_id, frame_bgr)

        evento = Evento(
            id=evento_id,
            timestamp=agora,
            hora=datetime.fromtimestamp(agora).strftime("%H:%M:%S"),
            classe_idx=idx,
            classe_key=key,
            nome=nome,
            confianca=float(predicao_dict.get("confianca", 0.0) or 0.0),
            gravidade=gravidade,
            tecido=tecido,
            imagem=imagem_url,
        )

        with self._lock:
            if len(self._eventos) == self._eventos.maxlen and self._eventos:
                antigo = self._eventos[0]
                self._indice.pop(antigo.id, None)
            self._eventos.append(evento)
            self._indice[evento.id] = evento
            self._total += 1
            self._por_classe[key] = self._por_classe.get(key, 0) + 1
            if idx == OK_INDEX:
                self._aprovadas += 1
                self._sequencia_ok += 1
                self._melhor_sequencia = max(self._melhor_sequencia, self._sequencia_ok)
            else:
                self._reprovadas += 1
                self._sequencia_ok = 0
        return evento

    def _salvar_captura(self, evento_id: str, frame_bgr: np.ndarray | None) -> str | None:
        if frame_bgr is None:
            return None
        try:
            import cv2  # import local: state.py tambem serve para testes sem camera

            garantir_pasta(self._pasta_capturas)
            destino = self._pasta_capturas / f"{evento_id}.jpg"
            ok = cv2.imwrite(str(destino), frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            if not ok:
                return None
            return f"/capturas/{destino.name}"
        except Exception:
            return None

    def caminho_captura(self, evento: "Evento | str") -> Path | None:
        """Caminho em disco da captura de um evento (util para mandar ao LLM)."""
        ev = self.evento(evento) if isinstance(evento, str) else evento
        if ev is None or not ev.imagem:
            return None
        destino = self._pasta_capturas / Path(ev.imagem).name
        return destino if destino.exists() else None

    # ----------------------------------------------------------------- leitura

    def eventos(self, limite: int = 60, classe: str | None = None) -> list[dict]:
        """Eventos mais recentes primeiro, opcionalmente filtrados por classe."""
        limite = max(1, int(limite))
        with self._lock:
            itens = list(self._eventos)
        itens.reverse()
        if classe:
            classe = str(classe).strip()
            itens = [e for e in itens if e.classe_key == classe]
        return [e.to_dict() for e in itens[:limite]]

    def evento(self, evento_id: str) -> Evento | None:
        with self._lock:
            return self._indice.get(str(evento_id))

    # ------------------------------------------------------------- anexos LLM

    def anexar_diagnostico(self, evento_id: str, diagnostico: dict) -> bool:
        with self._lock:
            ev = self._indice.get(str(evento_id))
            if ev is None:
                return False
            ev.diagnostico = diagnostico
            return True

    def anexar_revisao(self, evento_id: str, revisao: dict) -> bool:
        with self._lock:
            ev = self._indice.get(str(evento_id))
            if ev is None:
                return False
            ev.revisao_llm = revisao
            return True

    # --------------------------------------------------------- correcao humana

    def corrigir_rotulo(self, evento_id: str, classe_key: str) -> bool:
        """Registra a correcao do operador e grava uma linha no CSV de correcoes."""
        classe_key = str(classe_key).strip()
        try:
            info = class_by_key(classe_key)
        except KeyError:
            return False
        with self._lock:
            ev = self._indice.get(str(evento_id))
            if ev is None:
                return False
            ev.rotulo_operador = info.key
            linha = {
                "timestamp": f"{ev.timestamp:.3f}",
                "hora": datetime.fromtimestamp(ev.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                "evento_id": ev.id,
                "imagem": Path(ev.imagem).name if ev.imagem else "",
                "classe_predita": ev.classe_key,
                "classe_corrigida": info.key,
                "confianca": f"{ev.confianca:.4f}",
                "tecido": ev.tecido or "",
            }
        self._gravar_correcao(linha)
        return True

    def _gravar_correcao(self, linha: dict) -> None:
        try:
            destino = self._arquivo_correcoes
            garantir_pasta(destino.parent)
            novo = not destino.exists()
            with open(destino, "a", newline="", encoding="utf-8") as fh:
                escritor = csv.DictWriter(fh, fieldnames=list(linha.keys()))
                if novo:
                    escritor.writeheader()
                escritor.writerow(linha)
        except Exception:
            # Nunca derruba a aplicacao por causa do arquivo de correcoes.
            pass

    # ------------------------------------------------------------ estatisticas

    def estatisticas(self) -> dict:
        with self._lock:
            total = self._total
            aprovadas = self._aprovadas
            reprovadas = self._reprovadas
            meta = max(1, int(self.meta_pecas))
            return {
                "total": total,
                "aprovadas": aprovadas,
                "reprovadas": reprovadas,
                "sequencia_ok": self._sequencia_ok,
                "melhor_sequencia": self._melhor_sequencia,
                "taxa_aprovacao": round(aprovadas / total, 4) if total else 0.0,
                "por_classe": dict(self._por_classe),
                "inicio": self._inicio,
                "duracao_s": round(time.time() - self._inicio, 1),
                "meta_pecas": int(self.meta_pecas),
                "progresso_meta": round(min(1.0, total / meta), 4),
            }

    def definir_meta(self, pecas: int) -> int:
        with self._lock:
            self.meta_pecas = max(1, int(pecas))
            return self.meta_pecas

    def limpar(self) -> None:
        with self._lock:
            self._eventos.clear()
            self._indice.clear()
            self._inicio = time.time()
            self._total = 0
            self._aprovadas = 0
            self._reprovadas = 0
            self._sequencia_ok = 0
            self._melhor_sequencia = 0
            self._por_classe = {k: 0 for k in CLASS_KEYS}
