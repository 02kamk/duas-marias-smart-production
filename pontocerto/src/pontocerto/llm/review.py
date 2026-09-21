"""Segunda opiniao do LLM multimodal sobre uma predicao da CNN.

FILOSOFIA DESTA CAMADA
----------------------
A rede neural convolucional e quem decide em tempo real. Ela e rapida, roda
offline e foi treinada nas 14.565 imagens do proprio dataset. O LLM multimodal
NAO substitui a CNN e nao a "treina" por magica. Ele entra em tres papeis
concretos e verificaveis:

  (1) AUDITOR DE ROTULOS, antes do treino: revisa amostras do conjunto de treino
      e aponta imagens provavelmente mal rotuladas, melhorando o dado que
      alimenta a CNN.
  (2) SEGUNDA OPINIAO, em tempo de uso: quando a confianca da CNN cai na faixa
      de incerteza, o frame vai para o modelo de visao, que concorda ou discorda
      e justifica.  <-- este modulo
  (3) EXPLICADOR TECNICO: converte a classe prevista em causa provavel e acao
      corretiva na maquina de costura, e escreve o relatorio de turno.

`revisar_predicao` NUNCA levanta excecao. O loop de inferencia roda a 20 ou 30
quadros por segundo: se a internet cair, a chave vencer ou o modelo devolver
lixo, a funcao apenas preenche "erro" e devolve "concorda": None, e a interface
mostra um aviso amigavel em vez de um erro 500.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from pontocerto.labels import CLASS_KEYS, class_by_key
from pontocerto.llm.openrouter import (
    ClienteOpenRouter,
    ErroOpenRouter,
    extrair_primeiro_json,
)
from pontocerto.llm.prompts import (
    ESQUEMA_REVISAO,
    SISTEMA_INSPETOR,
    montar_prompt_revisao,
)

__all__ = ["revisar_predicao"]


def _base(erro: str | None = None) -> dict:
    return {
        "concorda": None,
        "classe_sugerida": "",
        "nome_sugerido": "",
        "confianca": 0.0,
        "justificativa": "",
        "sinais": [],
        "modelo": "",
        "ms": 0.0,
        "erro": erro,
    }


def _normalizar_chave(valor: Any) -> str:
    """Converte o que o modelo escreveu em uma das 11 chaves canonicas."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    if not texto:
        return ""
    if texto in CLASS_KEYS:
        return texto
    achatado = texto.lower().replace("-", "_").replace(" ", "_")
    if achatado in CLASS_KEYS:
        return achatado
    # O modelo pode ter respondido com o indice, o nome da pasta ou o nome em pt.
    if achatado.isdigit():
        idx = int(achatado)
        if 0 <= idx < len(CLASS_KEYS):
            return CLASS_KEYS[idx]
    for chave in CLASS_KEYS:
        if chave in achatado:
            return chave
    for c in (class_by_key(k) for k in CLASS_KEYS):
        if c.pt.lower() in texto.lower() or c.folder.lower() == texto.lower():
            return c.key
    return ""


def _normalizar_confianca(valor: Any) -> float:
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if f > 1.0:  # o modelo as vezes responde em porcentagem
        f = f / 100.0
    return max(0.0, min(1.0, f))


def _normalizar_sinais(valor: Any) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, str):
        return [valor.strip()] if valor.strip() else []
    if isinstance(valor, (list, tuple)):
        return [str(x).strip() for x in valor if str(x).strip()]
    return [str(valor)]


def revisar_predicao(
    cliente: ClienteOpenRouter,
    imagem_jpeg: bytes,
    predicao_dict: Mapping[str, Any],
    tecido: str | None = None,
) -> dict:
    """Pede ao modelo de visao que confirme ou corrija a predicao da CNN.

    Retorno (sempre com estas chaves):
        {"concorda": bool|None, "classe_sugerida": str, "nome_sugerido": str,
         "confianca": float, "justificativa": str, "sinais": [str],
         "modelo": str, "ms": float, "erro": str|None}

    Em qualquer falha devolve o mesmo dict com "erro" preenchido e
    "concorda": None. Nunca levanta excecao.
    """
    inicio = time.perf_counter()

    if cliente is None:
        return _base("cliente de LLM nao construido.")
    try:
        if not cliente.configurado:
            checagem = cliente.checar()
            return _base(str(checagem.get("mensagem") or "LLM nao configurado."))
    except Exception as exc:  # cliente estranho ou cfg incompleta
        return _base(f"nao foi possivel avaliar o cliente de LLM: {exc}")

    if not imagem_jpeg:
        return _base("nenhum quadro JPEG foi entregue para a segunda opiniao.")

    try:
        prompt = montar_prompt_revisao(predicao_dict or {}, tecido=tecido)
        resposta = cliente.chat_visao(
            prompt,
            imagem_jpeg,
            json_schema=ESQUEMA_REVISAO,
            prompt_sistema=SISTEMA_INSPETOR,
        )
    except ErroOpenRouter as exc:
        saida = _base(str(exc))
        saida["ms"] = (time.perf_counter() - inicio) * 1000.0
        return saida
    except Exception as exc:  # falha nao prevista: a inspecao nao pode parar
        saida = _base(f"falha inesperada na revisao pelo LLM: {exc}")
        saida["ms"] = (time.perf_counter() - inicio) * 1000.0
        return saida

    dados = extrair_primeiro_json(resposta.texto)
    if dados is None:
        saida = _base("o modelo respondeu sem JSON valido; revisao descartada.")
        saida["modelo"] = resposta.modelo
        saida["ms"] = resposta.ms
        return saida

    chave = _normalizar_chave(dados.get("classe_sugerida"))
    if not chave:
        # sem chave utilizavel, cai para a propria classe da rede
        chave = _normalizar_chave((predicao_dict or {}).get("classe_key"))

    nome = ""
    if chave:
        try:
            nome = class_by_key(chave).pt
        except KeyError:
            nome = chave

    concorda = dados.get("concorda")
    if not isinstance(concorda, bool):
        prevista = _normalizar_chave((predicao_dict or {}).get("classe_key"))
        concorda = (bool(chave) and bool(prevista) and chave == prevista) or None

    justificativa = str(dados.get("justificativa") or "").strip()

    return {
        "concorda": concorda,
        "classe_sugerida": chave,
        "nome_sugerido": nome,
        "confianca": _normalizar_confianca(dados.get("confianca")),
        "justificativa": justificativa,
        "sinais": _normalizar_sinais(dados.get("sinais")),
        "modelo": resposta.modelo or cliente.modelo_visao,
        "ms": float(resposta.ms),
        "erro": None,
    }
