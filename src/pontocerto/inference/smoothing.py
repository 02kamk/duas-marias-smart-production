"""Suavizacao temporal do veredito do Ponto Certo.

Um classificador de frame isolado pisca: em 30 fps ele troca de opiniao varias
vezes por segundo e a tela vira um pisca-pisca inutil para o operador. Aqui a
gente estabiliza isso com tres mecanismos:

1. EMA das probabilidades (`cfg.inferencia.ema_alpha`) - filtra o ruido frame
   a frame sem introduzir atraso grande.
2. Confirmacao por contagem - a mesma classe precisa dominar
   `cfg.inferencia.frames_para_confirmar` frames CONSECUTIVOS acima de
   `cfg.inferencia.limiar_alerta`. Se a classe dominante muda, o contador
   reinicia: e isso que evita o veredito "grudar" em uma falha antiga.
3. Cooldown POR CLASSE (`cfg.inferencia.cooldown_evento_s`) - um evento so e
   emitido uma vez por deteccao, e a mesma classe so pode gerar outro evento
   depois do cooldown. Sem isso, uma peca parada na frente da camera geraria
   30 eventos por segundo.

Abaixo de `cfg.inferencia.limiar_incerteza` o veredito marca `pede_llm=True`:
e o gatilho para pedir a segunda opiniao do modelo de visao.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from pontocerto.labels import CLASS_KEYS, CLASS_NAMES_PT, NUM_CLASSES, OK_INDEX

ESTADO_AQUECENDO = "aquecendo"
ESTADO_OK = "ok"
ESTADO_FALHA = "falha"
ESTADO_INCERTO = "incerto"


@dataclass
class Veredito:
    """O que a interface mostra depois da suavizacao."""

    estado: str
    classe_idx: int
    classe_key: str
    nome: str
    confianca: float
    estavel: bool
    novo_evento: bool
    pede_llm: bool

    def to_dict(self) -> dict:
        return {
            "estado": self.estado,
            "classe_idx": int(self.classe_idx),
            "classe_key": self.classe_key,
            "nome": self.nome,
            "confianca": float(self.confianca),
            "estavel": bool(self.estavel),
            "novo_evento": bool(self.novo_evento),
            "pede_llm": bool(self.pede_llm),
        }


def _nome_classe(indice: int) -> str:
    if 0 <= indice < len(CLASS_NAMES_PT):
        return CLASS_NAMES_PT[indice]
    return f"classe {indice}"


def _key_classe(indice: int) -> str:
    if 0 <= indice < len(CLASS_KEYS):
        return CLASS_KEYS[indice]
    return f"classe_{indice}"


class SuavizadorTemporal:
    """Mantem o estado temporal da inspecao (uma instancia por sessao)."""

    def __init__(self, cfg) -> None:
        self._cfg = cfg
        self._lock = threading.RLock()

        self.ema_alpha = float(self._do_cfg("ema_alpha", 0.45))
        self.frames_para_confirmar = max(1, int(self._do_cfg("frames_para_confirmar", 4)))
        self.limiar_alerta = float(self._do_cfg("limiar_alerta", 0.55))
        self.limiar_incerteza = float(self._do_cfg("limiar_incerteza", 0.70))
        self.cooldown_evento_s = float(self._do_cfg("cooldown_evento_s", 3.0))

        self._probs: Optional[np.ndarray] = None
        self._classe_atual: int = -1
        self._contador: int = 0
        self._frames: int = 0
        self._evento_emitido: bool = False
        self._ultimo_evento: dict[int, float] = {}
        self._ultimo_veredito: Optional[Veredito] = None

    # -- config ------------------------------------------------------------

    def _do_cfg(self, chave: str, padrao):
        try:
            valor = self._cfg["inferencia"][chave]
            return padrao if valor is None else valor
        except Exception:
            return padrao

    def ajustar(
        self,
        limiar_alerta: float | None = None,
        limiar_incerteza: float | None = None,
        frames_para_confirmar: int | None = None,
        ema_alpha: float | None = None,
        cooldown_evento_s: float | None = None,
    ) -> dict:
        """Aplica novos limiares em memoria (rota POST /api/ajustes)."""
        with self._lock:
            if limiar_alerta is not None:
                self.limiar_alerta = float(limiar_alerta)
            if limiar_incerteza is not None:
                self.limiar_incerteza = float(limiar_incerteza)
            if frames_para_confirmar is not None:
                self.frames_para_confirmar = max(1, int(frames_para_confirmar))
            if ema_alpha is not None:
                self.ema_alpha = float(np.clip(float(ema_alpha), 0.01, 1.0))
            if cooldown_evento_s is not None:
                self.cooldown_evento_s = max(0.0, float(cooldown_evento_s))
            return self.ajustes()

    def ajustes(self) -> dict:
        return {
            "ema_alpha": float(self.ema_alpha),
            "frames_para_confirmar": int(self.frames_para_confirmar),
            "limiar_alerta": float(self.limiar_alerta),
            "limiar_incerteza": float(self.limiar_incerteza),
            "cooldown_evento_s": float(self.cooldown_evento_s),
        }

    # -- nucleo ------------------------------------------------------------

    @staticmethod
    def _sanear(probs: Sequence[float] | np.ndarray) -> np.ndarray:
        vetor = np.asarray(probs, dtype=np.float32).reshape(-1)
        if vetor.size == 0:
            raise ValueError("vetor de probabilidades vazio.")
        vetor = np.nan_to_num(vetor, nan=0.0, posinf=0.0, neginf=0.0)
        vetor = np.clip(vetor, 0.0, None)
        soma = float(vetor.sum())
        if soma > 0:
            vetor = vetor / soma
        else:
            vetor = np.full_like(vetor, 1.0 / vetor.size)
        return vetor

    def atualizar(self, probs: np.ndarray, agora: float | None = None) -> Veredito:
        """Alimenta o suavizador com as probabilidades de mais um frame."""
        instante = float(agora) if agora is not None else time.monotonic()
        vetor = self._sanear(probs)

        with self._lock:
            if self._probs is None or self._probs.shape != vetor.shape:
                suave = vetor.copy()
            else:
                a = float(np.clip(self.ema_alpha, 0.01, 1.0))
                suave = a * vetor + (1.0 - a) * self._probs
            self._probs = suave
            self._frames += 1

            indice = int(np.argmax(suave))
            confianca = float(suave[indice])
            acima = confianca >= self.limiar_alerta

            if indice == self._classe_atual:
                if acima:
                    self._contador += 1
                else:
                    # A classe continua a mesma mas perdeu forca: a sequencia
                    # de confirmacao recomeca do zero.
                    self._contador = 0
                    self._evento_emitido = False
            else:
                self._classe_atual = indice
                self._contador = 1 if acima else 0
                self._evento_emitido = False

            estavel = self._contador >= self.frames_para_confirmar
            aquecendo = self._frames < self.frames_para_confirmar

            if aquecendo:
                estado = ESTADO_AQUECENDO
            elif not estavel:
                estado = ESTADO_INCERTO
            elif indice == OK_INDEX:
                estado = ESTADO_OK
            else:
                estado = ESTADO_FALHA

            novo_evento = False
            if estavel and not self._evento_emitido:
                ultimo = self._ultimo_evento.get(indice)
                if ultimo is None or (instante - ultimo) >= self.cooldown_evento_s:
                    novo_evento = True
                    self._ultimo_evento[indice] = instante
                # Marca a deteccao como ja tratada mesmo quando o cooldown
                # bloqueou: so volta a valer quando a classe dominante mudar.
                self._evento_emitido = True

            pede_llm = bool(confianca < self.limiar_incerteza) and estado != ESTADO_AQUECENDO

            veredito = Veredito(
                estado=estado,
                classe_idx=indice,
                classe_key=_key_classe(indice),
                nome=_nome_classe(indice),
                confianca=confianca,
                estavel=bool(estavel),
                novo_evento=bool(novo_evento),
                pede_llm=pede_llm,
            )
            self._ultimo_veredito = veredito
            return veredito

    def reiniciar(self) -> None:
        """Zera o estado temporal (troca de peca, troca de camera, limpar sessao)."""
        with self._lock:
            self._probs = None
            self._classe_atual = -1
            self._contador = 0
            self._frames = 0
            self._evento_emitido = False
            self._ultimo_evento.clear()
            self._ultimo_veredito = None

    # -- leitura -----------------------------------------------------------

    @property
    def probs_suavizadas(self) -> np.ndarray:
        with self._lock:
            if self._probs is None:
                return np.zeros(NUM_CLASSES, dtype=np.float32)
            return self._probs.copy()

    @property
    def ultimo_veredito(self) -> Optional[Veredito]:
        return self._ultimo_veredito

    @property
    def frames(self) -> int:
        return int(self._frames)

    def veredito_neutro(self) -> Veredito:
        """Veredito usado antes do primeiro frame (camera parada, por exemplo)."""
        return Veredito(
            estado=ESTADO_AQUECENDO,
            classe_idx=OK_INDEX,
            classe_key=_key_classe(OK_INDEX),
            nome=_nome_classe(OK_INDEX),
            confianca=0.0,
            estavel=False,
            novo_evento=False,
            pede_llm=False,
        )
