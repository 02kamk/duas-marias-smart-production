"""Lotes simples: código, cliente e quantidade, guardados no Supabase.

O lote só agrupa as peças inspecionadas para dar a qualidade de cada pedido
(quantas foram vistas, quantas com defeito e quais defeitos). Não há prazo,
apontamento de produção nem previsão de entrega.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Body, FastAPI, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError, field_validator

from pontocerto.labels import CLASS_KEYS, class_by_key

SEM_BANCO = ("Os lotes ficam no Supabase. Preencha SUPABASE_DB_URL no .env "
             "(veja o README) e reinicie o sistema.")


class NovoLote(BaseModel):
    codigo: str = Field(min_length=1, max_length=40)
    cliente: str = Field(min_length=1, max_length=120)
    quantidade: int = Field(gt=0, le=1_000_000)
    modelo_peca: str | None = Field(default=None, max_length=120)

    @field_validator('codigo', 'cliente', 'modelo_peca')
    @classmethod
    def _limpar(cls, valor):
        if valor is None:
            return None
        valor = ' '.join(str(valor).split())
        return valor or None


def _erro(status: int, mensagem: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"erro": mensagem})


def _nome_classe(chave: str) -> str:
    return class_by_key(chave).pt if chave in CLASS_KEYS else chave


def _lote_publico(linha: dict) -> dict:
    inspecionadas = int(linha.get("inspecionadas") or 0)
    reprovadas = int(linha.get("reprovadas") or 0)
    return {
        "id": int(linha["id"]),
        "codigo": linha.get("codigo"),
        "cliente": linha.get("cliente"),
        "modelo_peca": linha.get("modelo_peca"),
        "quantidade": int(linha.get("quantidade") or 0),
        "concluido": linha.get("status") == "concluido",
        "inspecionadas": inspecionadas,
        "aprovadas": int(linha.get("aprovadas") or 0),
        "reprovadas": reprovadas,
        "taxa_defeito": round(reprovadas / inspecionadas, 4) if inspecionadas else 0.0,
        "ultima_inspecao": str(linha["ultima_inspecao"]) if linha.get("ultima_inspecao") else None,
        "criado_em": str(linha["criado_em"]) if linha.get("criado_em") else None,
    }


def registrar(app: FastAPI, definir_lote_ativo: Callable[[dict | None], dict | None]) -> None:
    """Rotas /api/lotes. `definir_lote_ativo` troca o lote que recebe as próximas peças."""

    def banco_ou_erro():
        banco = getattr(app.state, "banco", None)
        if banco is None or not banco.configurado:
            return None, _erro(503, SEM_BANCO)
        return banco, None

    def falha(banco, exc: Exception) -> JSONResponse:
        mensagem = banco.mascarar(str(exc)) if hasattr(banco, "mascarar") else "falha no banco"
        return _erro(502, f"Não foi possível falar com o Supabase: {mensagem}")

    def ativo_id():
        lote = app.state.estado.lote_ativo
        return lote.get("id") if lote else None

    @app.get("/api/lotes")
    def listar(todos: bool = Query(False, description="inclui os lotes concluídos")):
        banco = getattr(app.state, "banco", None)
        if banco is None or not banco.configurado:
            return {"disponivel": False, "erro": SEM_BANCO, "lotes": [], "ativo": app.state.estado.lote_ativo}
        try:
            linhas = banco.listar_lotes()
        except Exception:
            return {"disponivel": False, "erro": "Sem conexão com o Supabase agora. Tente de novo em instantes.",
                    "lotes": [], "ativo": app.state.estado.lote_ativo}
        lotes = [_lote_publico(l) for l in linhas]
        if not todos:
            lotes = [l for l in lotes if not l["concluido"]]
        return {"disponivel": True, "lotes": lotes, "ativo": app.state.estado.lote_ativo}

    @app.post("/api/lotes", status_code=201)
    def criar(corpo: dict = Body(...)):
        try:
            dados = NovoLote(**(corpo or {}))
        except ValidationError:
            return _erro(422, "Preencha código, cliente e uma quantidade maior que zero.")
        banco, erro = banco_ou_erro()
        if erro:
            return erro
        try:
            if any(str(l.get("codigo")).casefold() == dados.codigo.casefold() for l in banco.listar_lotes()):
                return _erro(409, f"Já existe um lote com o código {dados.codigo}.")
            cliente = next((c for c in banco.listar_clientes()
                            if str(c.get("nome")).casefold() == dados.cliente.casefold()), None)
            if cliente is None:
                cliente = banco.criar_cliente(dados.cliente)
            novo = banco.criar_lote({"cliente_id": cliente["id"], "codigo": dados.codigo,
                                     "quantidade": dados.quantidade, "modelo_peca": dados.modelo_peca})
            return {"lote": _lote_publico(banco.obter_lote(int(novo["id"])))}
        except Exception as exc:
            return falha(banco, exc)

    @app.get("/api/lotes/ativo")
    def ler_ativo():
        return {"lote": app.state.estado.lote_ativo}

    @app.get("/api/lotes/clientes")
    def clientes():
        banco, erro = banco_ou_erro()
        if erro:
            return {"clientes": []}
        try:
            return {"clientes": [c["nome"] for c in banco.listar_clientes()]}
        except Exception:
            return {"clientes": []}

    @app.get("/api/lotes/{lote_id}")
    def detalhe(lote_id: int):
        banco, erro = banco_ou_erro()
        if erro:
            return erro
        try:
            linha = banco.obter_lote(lote_id)
            if not linha:
                return _erro(404, "Lote não encontrado.")
            defeitos = [{"classe": d["classe_final"], "nome": _nome_classe(d["classe_final"]),
                         "quantidade": int(d["quantidade"])}
                        for d in banco.defeitos_por_classe(lote_id) if d["classe_final"] != "normal"]
            recentes = [{"evento_id": i.get("evento_id"), "classe": i["classe_final"],
                         "nome": _nome_classe(i["classe_final"]), "aprovada": bool(i["aprovada"]),
                         "corrigida": i.get("classe_confirmada") is not None,
                         "criado_em": str(i["criado_em"])}
                        for i in banco.ultimas_inspecoes(lote_id, 20)]
        except Exception as exc:
            return falha(banco, exc)
        lote = _lote_publico(linha)
        lote["ativo"] = ativo_id() == lote["id"]
        return {"lote": lote, "defeitos": defeitos, "recentes": recentes}

    @app.post("/api/lotes/{lote_id}/inspecionar")
    def inspecionar(lote_id: int):
        banco, erro = banco_ou_erro()
        if erro:
            return erro
        try:
            linha = banco.obter_lote(lote_id)
            if not linha:
                return _erro(404, "Lote não encontrado.")
            if linha.get("status") == "concluido":
                return _erro(409, "Este lote está concluído. Reabra para inspecionar mais peças.")
            if linha.get("status") == "aberto":
                banco.atualizar_status_lote(lote_id, "em_inspecao")
        except Exception as exc:
            return falha(banco, exc)
        return {"lote": definir_lote_ativo({
            "id": int(linha["id"]), "codigo": linha.get("codigo"), "cliente": linha.get("cliente"),
            "modelo_peca": linha.get("modelo_peca"), "quantidade": linha.get("quantidade")})}

    @app.post("/api/lotes/ativo")
    def parar():
        """As próximas peças ficam sem lote."""
        return {"lote": definir_lote_ativo(None)}

    def _mudar_status(lote_id: int, status: str):
        banco, erro = banco_ou_erro()
        if erro:
            return erro
        try:
            if not banco.atualizar_status_lote(lote_id, status):
                return _erro(404, "Lote não encontrado.")
            linha = banco.obter_lote(lote_id)
        except Exception as exc:
            return falha(banco, exc)
        if status == "concluido" and ativo_id() == lote_id:
            definir_lote_ativo(None)
        return {"lote": _lote_publico(linha)}

    @app.post("/api/lotes/{lote_id}/concluir")
    def concluir(lote_id: int):
        return _mudar_status(lote_id, "concluido")

    @app.post("/api/lotes/{lote_id}/reabrir")
    def reabrir(lote_id: int):
        return _mudar_status(lote_id, "em_inspecao")

    @app.get("/api/lotes/{lote_id}/pdf")
    def pdf(lote_id: int):
        banco, erro = banco_ou_erro()
        if erro:
            return erro
        try:
            linha = banco.obter_lote(lote_id)
            if not linha:
                return _erro(404, "Lote não encontrado.")
            contagem = banco.defeitos_por_classe(lote_id)
            ultimas = banco.ultimas_inspecoes(lote_id, 300)
        except Exception as exc:
            return falha(banco, exc)
        from datetime import datetime

        from pontocerto.app.pdf import numero, pct, pecas, relatorio
        lote = _lote_publico(linha)
        base = max(1, lote["inspecionadas"])
        defeitos = [(d["classe_final"], int(d["quantidade"])) for d in contagem if d["classe_final"] != "normal"]
        total_def = sum(q for _, q in defeitos) or 1

        def quando(v):
            try:
                return datetime.fromisoformat(str(v)).astimezone().strftime("%d/%m/%Y %H:%M")
            except ValueError:
                return str(v)[:16]

        com_defeito = [i for i in ultimas if not i.get("aprovada")]
        secoes = [{
            "titulo": "Defeitos por tipo",
            "texto": "Peças de cada tipo e a porcentagem sobre as peças inspecionadas no lote.",
            "barras": [(_nome_classe(c), q / total_def, f"{pecas(q)} · {pct(q / base)}")
                       for c, q in defeitos],
            "vazio": "Nenhum defeito encontrado." if lote["inspecionadas"] else "Nenhuma peça inspecionada neste lote ainda.",
        }]
        if com_defeito:
            secoes.append({"titulo": "Peças com defeito", "tabela": {
                "colunas": ["Data e hora", "Defeito", "Conferência"],
                "linhas": [[quando(i["criado_em"]), _nome_classe(i["classe_final"]),
                            "Corrigida" if i.get("classe_confirmada") and i["classe_confirmada"] != i.get("classe_predita")
                            else ("Confirmada" if i.get("classe_confirmada") else "Pela IA")] for i in com_defeito],
                "larguras": [0.3, 0.42, 0.28]}})
        andamento = f'{numero(lote["inspecionadas"])} de {numero(lote["quantidade"])} peças ({pct(min(1, lote["inspecionadas"] / max(1, lote["quantidade"])))})'
        dados = relatorio(
            rotulo=f'Qualidade do lote {lote["codigo"]}',
            sobretitulo="Relatório de qualidade do lote",
            titulo=f'Lote {lote["codigo"]}',
            subtitulo=lote["cliente"] + (f' · {lote["modelo_peca"]}' if lote["modelo_peca"] else ""),
            ficha=[("Cliente", lote["cliente"]), ("Peça", lote["modelo_peca"] or "—"),
                   ("Quantidade do lote", numero(lote["quantidade"]) + " peças"), ("Inspecionadas", andamento),
                   ("Situação", "Concluído" if lote["concluido"] else "Em aberto")],
            indicadores=[("Inspecionadas", numero(lote["inspecionadas"]), f'de {numero(lote["quantidade"])}'),
                         ("Aprovadas", numero(lote["aprovadas"]), pct(lote["aprovadas"] / base) if lote["inspecionadas"] else None),
                         ("Com defeito", numero(lote["reprovadas"]), pct(lote["taxa_defeito"]) if lote["inspecionadas"] else None)],
            secoes=secoes,
            nota='Cada peça foi fotografada e lida por um modelo de inteligência artificial de visão, que indica se há defeito de costura ou de tecido e qual é. Peças com defeito ou com leitura incerta passam por conferência humana; quando a pessoa corrigiu a leitura, vale a classe corrigida. Os percentuais são calculados sobre as peças inspecionadas no período e não substituem a inspeção final do cliente.',
        )
        nome = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in str(lote["codigo"]))
        return Response(dados, media_type='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename="qualidade-{nome}.pdf"'})
