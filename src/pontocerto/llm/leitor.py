"""Leitura da peça por IA de visão (OpenRouter).

O modelo treinado no StitchingNet não reconhece fotos reais da fábrica (tecido
liso, dobras, elástico franzido): ele vira "conhecimento de apoio". A IA recebe
a foto da peça, a lista dos 12 tipos com a explicação de cada um e um quadro
com uma foto de exemplo de cada tipo tirada do conjunto de treino.
"""
from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from pontocerto.labels import CLASSES, CLASS_KEYS, class_by_key
from pontocerto.llm.openrouter import ErroOpenRouter, extrair_primeiro_json

RAIZ = Path(__file__).resolve().parents[3]
QUADRO = RAIZ / "artifacts" / "referencia_defeitos.jpg"
LADO_FOTO = 1024

ESQUEMA = {
    "name": "leitura_peca",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["veredito", "classe", "confianca", "onde", "explicacao"],
        "properties": {
            "veredito": {"type": "string", "enum": ["aprovada", "defeito", "incerta"]},
            "classe": {"type": "string", "enum": list(CLASS_KEYS)},
            "confianca": {"type": "number"},
            "onde": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "required": ["x", "y", "largura", "altura"],
                "properties": {k: {"type": "number"} for k in ("x", "y", "largura", "altura")},
            },
            "explicacao": {"type": "string"},
        },
    },
}


def _instrucoes() -> str:
    tipos = "\n".join(f"{i}. {c.key} = {c.pt}: {c.descricao}" for i, c in enumerate(CLASSES))
    return f"""Você é inspetora de qualidade numa facção de costura. Olhe a FOTO DA PEÇA (a segunda imagem) e diga se há defeito de costura ou de tecido.

Tipos possíveis (use exatamente a chave antes do "="):
{tipos}

A primeira imagem é um QUADRO DE REFERÊNCIA com um exemplo ampliado de cada tipo, numerado como na lista. Ele serve só para mostrar como cada defeito costuma parecer; a foto da peça é tirada de mais longe, com outra luz e outro tecido.

Regras:
- Franzido de elástico no cós, pregas de modelagem, dobras do tecido, sombras, reflexos e amassados de manuseio são NORMAIS.
- Só aponte defeito se ele estiver visível na foto. Na dúvida entre normal e defeito, use veredito "incerta".
- Fio solto, linha sobrando ou sujeira sobre o tecido: use stain_damage e diga isso na explicação.
- Se aprovada, classe = "normal" e onde = null.
- "onde" é a caixa do defeito na FOTO DA PEÇA, em frações de 0 a 1: x e y do canto superior esquerdo, largura e altura.
- "confianca" de 0 a 1.
- "explicacao": uma frase curta em português, para quem está na linha de produção (sem termos técnicos em inglês).
Responda só com o JSON."""


def quadro_referencia() -> bytes | None:
    """Quadro 4x3 com um exemplo de cada tipo (do conjunto de teste), feito uma vez e guardado.

    Sem o arquivo pronto e sem o dataset no computador, a leitura segue só com a lista de tipos.
    """
    if QUADRO.exists():
        return QUADRO.read_bytes()
    try:
        return _montar_quadro()
    except Exception:
        return None


def _montar_quadro() -> bytes:
    import pandas as pd  # só para montar o quadro uma vez; o servidor online não precisa

    df = pd.read_csv(RAIZ / "artifacts" / "splits.csv")
    teste = df[df.split == "teste"]
    blocos = []
    for c in CLASSES:
        linha = teste[teste.classe_idx == c.index].sort_values("caminho").iloc[0]
        img = cv2.imread(str(RAIZ / "dados" / "treino" / linha.caminho))
        img = cv2.resize(img, (224, 224))
        cv2.rectangle(img, (0, 0), (44, 30), (255, 255, 255), -1)
        cv2.putText(img, str(c.index), (6, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        blocos.append(img)
    while len(blocos) % 4:
        blocos.append(np.full((224, 224, 3), 255, np.uint8))
    grade = np.vstack([np.hstack(blocos[i:i + 4]) for i in range(0, len(blocos), 4)])
    ok, buf = cv2.imencode(".jpg", grade, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    QUADRO.parent.mkdir(parents=True, exist_ok=True)
    QUADRO.write_bytes(buf.tobytes())
    return buf.tobytes()


def preparar_foto(frame_bgr: np.ndarray) -> bytes:
    """Reduz a foto para no máximo 1024 px no lado maior: lê bem e gasta pouco."""
    h, w = frame_bgr.shape[:2]
    escala = min(1.0, LADO_FOTO / max(h, w))
    if escala < 1:
        frame_bgr = cv2.resize(frame_bgr, (int(w * escala), int(h * escala)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise ValueError("não consegui preparar a foto.")
    return buf.tobytes()


def _url(jpeg: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}}


def _normalizar(dados: dict) -> dict:
    classe = str(dados.get("classe") or "normal")
    if classe not in CLASS_KEYS:
        classe = "normal"
    veredito = str(dados.get("veredito") or "incerta")
    if veredito not in ("aprovada", "defeito", "incerta"):
        veredito = "incerta"
    if veredito == "aprovada":
        classe = "normal"
    elif veredito == "defeito" and classe == "normal":
        veredito = "incerta"
    try:
        confianca = max(0.0, min(1.0, float(dados.get("confianca"))))
    except (TypeError, ValueError):
        confianca = 0.5
    onde = dados.get("onde")
    caixa = None
    if isinstance(onde, dict) and classe != "normal":
        try:
            x, y = (max(0.0, min(1.0, float(onde[k]))) for k in ("x", "y"))
            lw, lh = (max(0.0, min(1.0, float(onde[k]))) for k in ("largura", "altura"))
            if lw > 0 and lh > 0:
                caixa = {"x": x, "y": y, "largura": min(lw, 1 - x), "altura": min(lh, 1 - y)}
        except (KeyError, TypeError, ValueError):
            caixa = None
    return {"veredito": veredito, "classe": classe, "nome": class_by_key(classe).pt,
            "confianca": confianca, "onde": caixa, "explicacao": str(dados.get("explicacao") or "").strip()[:300]}


def ler_peca(cliente: Any, frame_bgr: np.ndarray, modelo: str | None = None) -> dict:
    """Manda a foto para a IA e devolve a leitura normalizada, com tempo e custo."""
    quadro = quadro_referencia()
    texto = _instrucoes()
    if quadro is None:
        texto = texto.replace("A primeira imagem é um QUADRO", "(Sem quadro de referência nesta leitura.) Um QUADRO").replace(
            "a segunda imagem", "a imagem enviada")
    conteudo = [{"type": "text", "text": texto}] + ([_url(quadro)] if quadro else []) + [_url(preparar_foto(frame_bgr))]
    mensagens = [{"role": "user", "content": conteudo}]
    inicio = time.perf_counter()
    try:
        resposta = cliente.chat(mensagens, modelo=modelo or cliente.modelo_visao, json_schema=ESQUEMA,
                                max_tokens=400, temperatura=0.1)
    except ErroOpenRouter as exc:
        if exc.status not in (400, 404, 422):
            raise
        # Alguns modelos não aceitam json_schema: pede o JSON no texto.
        resposta = cliente.chat(mensagens, modelo=modelo or cliente.modelo_visao, max_tokens=400, temperatura=0.1)
    dados = extrair_primeiro_json(resposta.texto)
    if dados is None:
        raise ErroOpenRouter("a IA não devolveu uma leitura válida. Tente de novo.")
    uso = (resposta.bruto or {}).get("usage") or {}
    leitura = _normalizar(dados)
    leitura.update({"modelo": resposta.modelo or modelo, "ms": round((time.perf_counter() - inicio) * 1000),
                    "tokens_entrada": resposta.tokens_entrada, "tokens_saida": resposta.tokens_saida,
                    "custo_usd": float(uso.get("cost") or 0.0)})
    return leitura
