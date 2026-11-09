"""Fila de gravacao no Supabase (thread propria, fora da inferencia).

Fluxo:

    motor / rotas  --enfileirar_evento()-->  fila em memoria  -->  thread "banco-sync"
                                                                     |
                                     falhou (sem internet etc.) -----+--> artifacts/pendentes.jsonl
                                                                     |
                               a cada `intervalo_reenvio_s` <--------+    (reenviados depois)

Regras:

  - So eventos com `lote_id` vao para o banco. Sem lote ativo a peca fica so no
    historico local, como antes.
  - Cada item e uma FOTOGRAFIA COMPLETA do evento (classe, correcao, diagnostico,
    revisao). Gravar e idempotente: insere se nao existe, senao atualiza. Assim a
    ordem de chegada nao importa e reenviar nunca duplica.
  - Foto so sobe quando a classe final e um defeito. Se o operador corrigir para
    "normal", a foto que ja estava na nuvem e apagada.
  - Sem internet o sincronizador entra em "modo offline" por `intervalo_reenvio_s`:
    os itens vao direto para o arquivo, sem esperar o timeout de cada um.
  - `enfileirar_evento` nunca bloqueia: e chamado pela thread de inferencia.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pontocerto.labels import CLASS_KEYS, OK_INDEX

__all__ = ["Sincronizador"]

log = logging.getLogger("pontocerto.sincronizador")

CLASSE_OK = CLASS_KEYS[OK_INDEX]
_FIM = object()  # sentinela para encerrar a thread


def _cfg_banco(cfg: Any) -> dict:
    try:
        return dict(cfg["banco"] or {})
    except Exception:
        return {}


class Sincronizador:
    """Envia inspecoes (e fotos de defeitos) para o Supabase em segundo plano."""

    def __init__(self, cfg: Any, banco: Any, pasta_capturas: str | Path) -> None:
        bcfg = _cfg_banco(cfg)
        self._banco = banco
        self._pasta = Path(pasta_capturas)
        self._fila: queue.Queue = queue.Queue(maxsize=max(1, int(bcfg.get("tamanho_fila", 500))))
        self._intervalo = max(1.0, float(bcfg.get("intervalo_reenvio_s", 30)))
        self._max_tentativas = max(1, int(bcfg.get("max_tentativas", 20)))
        pend = bcfg.get("pendentes")
        self._arquivo = Path(pend) if pend else None
        self._descartados = (self._arquivo.with_name(self._arquivo.stem + "_descartados.jsonl")
                             if self._arquivo else None)

        self._trava_arquivo = threading.Lock()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._offline_ate = 0.0
        self._fotos_enviadas: set[str] = set()

        self.enviados = 0
        self.ultimo_erro: str | None = None
        self.ultimo_envio: str | None = None

    # ------------------------------------------------------------ ciclo
    def iniciar(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._laco, name="banco-sync", daemon=True)
        self._thread.start()

    def parar(self, timeout: float = 5.0) -> None:
        """Encerra a thread. O que sobrar na fila vai para o arquivo de pendentes."""
        self._parar.set()
        try:
            self._fila.put_nowait(_FIM)
        except queue.Full:
            pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        sobras = []
        while True:
            try:
                item = self._fila.get_nowait()
            except queue.Empty:
                break
            if item is not _FIM:
                sobras.append(item)
        self._guardar(sobras)

    # -------------------------------------------------------- entrada
    def enfileirar_evento(self, evento: Any) -> bool:
        """Agenda a gravacao do estado atual do evento. Nunca bloqueia.

        Devolve False quando o evento nao pertence a um lote (fica so local).
        """
        if getattr(evento, "lote_id", None) is None:
            return False
        item = self.instantaneo(evento)
        try:
            self._fila.put_nowait(item)
        except queue.Full:
            self._guardar([item])
        return True

    @staticmethod
    def instantaneo(evento: Any) -> dict:
        """Estado completo do evento, serializavel em JSON (vai para o arquivo)."""
        final = evento.rotulo_operador or evento.classe_key
        return {
            "evento_id": str(evento.id),
            "lote_id": int(evento.lote_id),
            "origem": "ao_vivo",
            "classe_predita": evento.classe_key,
            "confianca": float(evento.confianca),
            "classe_confirmada": evento.rotulo_operador,
            "diagnostico": evento.diagnostico,
            "revisao_llm": evento.revisao_llm,
            "criado_em": datetime.fromtimestamp(evento.timestamp).astimezone().isoformat(),
            "foto": Path(evento.imagem).name if evento.imagem else None,
            "quer_foto": final != CLASSE_OK,
            "tentativas": 0,
        }

    # ---------------------------------------------------------- estado
    def contar_pendentes(self) -> int:
        """Itens ainda nao gravados: os da fila + os do arquivo."""
        return self._fila.qsize() + self._linhas_no_arquivo()

    def estado(self) -> dict:
        offline = time.time() < self._offline_ate
        return {
            "na_fila": self._fila.qsize(),
            "no_arquivo": self._linhas_no_arquivo(),
            "enviados": self.enviados,
            "ultimo_envio": self.ultimo_envio,
            "ultimo_erro": self.ultimo_erro,
            "offline": offline,
            "proxima_tentativa_s": round(max(0.0, self._offline_ate - time.time())) if offline else 0,
        }

    def _linhas_no_arquivo(self) -> int:
        if not self._arquivo or not self._arquivo.exists():
            return 0
        with self._trava_arquivo:
            try:
                with open(self._arquivo, "r", encoding="utf-8") as fh:
                    return sum(1 for linha in fh if linha.strip())
            except Exception:
                return 0

    # ------------------------------------------------------------ laco
    def _laco(self) -> None:
        proximo_reenvio = time.time() + 2.0  # logo depois da subida: pendentes antigos
        while not self._parar.is_set():
            try:
                item = self._fila.get(timeout=1.0)
            except queue.Empty:
                item = None
            if item is _FIM:
                break
            if item is not None:
                self._processar(item)
            if time.time() >= proximo_reenvio:
                self.reenviar_pendentes()
                proximo_reenvio = time.time() + self._intervalo

    def _processar(self, item: dict) -> bool:
        """Tenta gravar; se nao der, guarda no arquivo. True se gravou."""
        if time.time() < self._offline_ate:
            self._guardar([item])
            return False
        try:
            self._enviar(item)
        except Exception as exc:
            self.ultimo_erro = self._mascarar(exc)
            item = dict(item)
            item["tentativas"] = int(item.get("tentativas", 0)) + 1
            item["ultimo_erro"] = self.ultimo_erro
            if not getattr(self._banco, "disponivel", False):
                self._offline_ate = time.time() + self._intervalo
            self._guardar([item])
            return False
        self.enviados += 1
        self.ultimo_erro = None
        self.ultimo_envio = datetime.now().isoformat(timespec="seconds")
        return True

    def _enviar(self, item: dict) -> None:
        banco = self._banco
        evento_id = str(item["evento_id"])
        lote_id = int(item["lote_id"])

        caminho = None
        if item.get("quer_foto") and item.get("foto") and banco.storage_configurado:
            arquivo = self._pasta / Path(str(item["foto"])).name
            if arquivo.is_file() and evento_id not in self._fotos_enviadas:
                caminho = banco.upload_foto(lote_id, evento_id, arquivo.read_bytes())

        criado = banco.inserir_inspecao({
            "lote_id": lote_id,
            "evento_id": evento_id,
            "origem": item.get("origem") or "ao_vivo",
            "classe_predita": item["classe_predita"],
            "confianca": item.get("confianca"),
            "classe_confirmada": item.get("classe_confirmada"),
            "imagem_path": caminho,
            "diagnostico": item.get("diagnostico"),
            "revisao_llm": item.get("revisao_llm"),
            "criado_em": item.get("criado_em"),
        })
        if criado is None:
            # Ja estava no banco: atualiza com o estado mais recente.
            campos = {
                "classe_confirmada": item.get("classe_confirmada"),
                "diagnostico": item.get("diagnostico"),
                "revisao_llm": item.get("revisao_llm"),
            }
            if caminho:
                campos["imagem_path"] = caminho
            banco.atualizar_inspecao(evento_id, **campos)
            if not item.get("quer_foto"):
                # Operador corrigiu para "normal": peca aprovada nao guarda foto.
                banco.remover_foto_inspecao(evento_id)
                self._fotos_enviadas.discard(evento_id)
        if caminho:
            self._fotos_enviadas.add(evento_id)

    # -------------------------------------------------------- pendentes
    def reenviar_pendentes(self) -> int:
        """Tenta gravar o que esta no arquivo. Devolve quantos foram gravados."""
        if not self._arquivo or not getattr(self._banco, "configurado", False):
            return 0
        with self._trava_arquivo:
            if not self._arquivo.exists():
                return 0
            try:
                linhas = self._arquivo.read_text(encoding="utf-8").splitlines()
                self._arquivo.unlink()
            except Exception as exc:
                self.ultimo_erro = f"nao consegui ler {self._arquivo.name}: {type(exc).__name__}"
                return 0

        # Varios estados do mesmo evento: vale o ultimo (as linhas estao em ordem).
        por_evento: dict[str, dict] = {}
        for linha in linhas:
            try:
                item = json.loads(linha)
                chave = str(item["evento_id"])
            except Exception:
                continue
            anterior = por_evento.pop(chave, None)
            if anterior is not None:
                item["tentativas"] = max(int(item.get("tentativas", 0)),
                                         int(anterior.get("tentativas", 0)))
            por_evento[chave] = item

        self._offline_ate = 0.0  # hora de tentar de novo
        gravados = 0
        descartar = []
        for item in por_evento.values():
            if int(item.get("tentativas", 0)) >= self._max_tentativas:
                descartar.append(item)
                continue
            # Se a conexao cair no meio, _processar devolve o resto ao arquivo
            # sem tentar (modo offline), entao nao se espera um timeout por item.
            if self._processar(item):
                gravados += 1
        self._guardar(descartar, self._descartados)
        if descartar:
            log.warning("%d gravacoes descartadas apos %d tentativas (ver %s)",
                        len(descartar), self._max_tentativas, self._descartados)
        return gravados

    def _guardar(self, itens: list[dict], destino: Path | None = None) -> None:
        destino = destino or self._arquivo
        if not itens or destino is None:
            return
        with self._trava_arquivo:
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
                with open(destino, "a", encoding="utf-8") as fh:
                    for item in itens:
                        fh.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            except Exception as exc:
                self.ultimo_erro = f"nao consegui gravar {destino.name}: {type(exc).__name__}"

    def _mascarar(self, exc: BaseException) -> str:
        texto = str(exc) or type(exc).__name__
        mascarar = getattr(self._banco, "mascarar", None)
        return mascarar(texto) if callable(mascarar) else texto
