"""Lotes simples: código, cliente e quantidade, guardados no Supabase.

O lote só agrupa as peças inspecionadas para dar a qualidade de cada pedido
(quantas foram vistas, quantas com defeito e quais defeitos). Não há prazo,
apontamento de produção nem previsão de entrega.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Body, FastAPI, Query, Request
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


def registrar(app: FastAPI, definir_lote_ativo: Callable[..., dict | None],
              soltar_lote: Callable[[int], None] | None = None) -> None:
    """Rotas /api/lotes. Cada conta escolhe o lote que recebe as próximas peças dela.

    `definir_lote_ativo(lote, email)` troca o lote de uma conta; `soltar_lote(id)` tira
    um lote concluído de todas as contas.
    """
    from pontocerto.app.maquinas import quem

    def email_de(request: Request):
        return quem(app, request)[0]

    def ativo_de(request: Request):
        return app.state.estado.lote_de(email_de(request))

    def banco_ou_erro():
        banco = getattr(app.state, "banco", None)
        if banco is None or not banco.configurado:
            return None, _erro(503, SEM_BANCO)
        return banco, None

    def falha(banco, exc: Exception) -> JSONResponse:
        mensagem = banco.mascarar(str(exc)) if hasattr(banco, "mascarar") else "falha no banco"
        return _erro(502, f"Não foi possível falar com o Supabase: {mensagem}")

    def ativo_id(request: Request):
        lote = ativo_de(request)
        return lote.get("id") if lote else None

    @app.get("/api/lotes")
    def listar(request: Request, todos: bool = Query(False, description="inclui os lotes concluídos")):
        banco = getattr(app.state, "banco", None)
        if banco is None or not banco.configurado:
            return {"disponivel": False, "erro": SEM_BANCO, "lotes": [], "ativo": ativo_de(request)}
        try:
            linhas = banco.listar_lotes()
        except Exception:
            return {"disponivel": False, "erro": "Sem conexão com o Supabase agora. Tente de novo em instantes.",
                    "lotes": [], "ativo": ativo_de(request)}
        lotes = [_lote_publico(l) for l in linhas]
        if not todos:
            lotes = [l for l in lotes if not l["concluido"]]
        return {"disponivel": True, "lotes": lotes, "ativo": ativo_de(request)}

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
    def ler_ativo(request: Request):
        return {"lote": ativo_de(request)}

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
    def detalhe(lote_id: int, request: Request):
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
        lote["ativo"] = ativo_id(request) == lote["id"]
        return {"lote": lote, "defeitos": defeitos, "recentes": recentes}

    @app.post("/api/lotes/{lote_id}/inspecionar")
    def inspecionar(lote_id: int, request: Request):
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
            "modelo_peca": linha.get("modelo_peca"), "quantidade": linha.get("quantidade")}, email_de(request))}

    @app.post("/api/lotes/ativo")
    def parar(request: Request):
        """As próximas peças desta conta ficam sem lote."""
        return {"lote": definir_lote_ativo(None, email_de(request))}

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
        if status == "concluido":
            if soltar_lote is not None:
                soltar_lote(lote_id)
            else:
                app.state.estado.soltar_lote(lote_id)
        return {"lote": _lote_publico(linha)}

    @app.post("/api/lotes/{lote_id}/concluir")
    def concluir(lote_id: int):
        return _mudar_status(lote_id, "concluido")

    @app.post("/api/lotes/{lote_id}/reabrir")
    def reabrir(lote_id: int):
        return _mudar_status(lote_id, "em_inspecao")

    @app.get("/api/lotes/{lote_id}/pdf")
    def pdf(lote_id: int, request: Request):
        banco, erro = banco_ou_erro()
        if erro:
            return erro
        try:
            linha = banco.obter_lote(lote_id)
            if not linha:
                return _erro(404, "Lote não encontrado.")
            ultimas = banco.ultimas_inspecoes(lote_id, 500)
        except Exception as exc:
            return falha(banco, exc)
        from datetime import date, datetime
        from types import SimpleNamespace

        from pontocerto.app.pdf import numero, pct, relatorio
        from pontocerto.app.relatorio_pdf import NOTA, conteudo
        lote = _lote_publico(linha)

        # As peças do lote com quem inspecionou e em qual máquina (histórico do app).
        eventos = [e for e in app.state.estado.eventos_periodo("0000-01-01", "9999-12-31", todos=True)
                   if e.lote_id == lote_id]
        if not eventos:
            # Peças gravadas por outro computador: o banco tem a peça, sem pessoa e máquina.
            def peca(i):
                try:
                    ts = datetime.fromisoformat(str(i["criado_em"])).timestamp()
                except ValueError:
                    ts = 0.0
                return SimpleNamespace(timestamp=ts, classe_final=i["classe_final"], autor=None, maquina_nome=None,
                                       lote_codigo=lote["codigo"], precisa_revisao=False,
                                       revisao_humana=({"decisao": "corrigida" if i["classe_confirmada"] != i["classe_predita"]
                                                        else "confirmada"} if i.get("classe_confirmada") else None))
            eventos = [peca(i) for i in ultimas]
        nomes = getattr(app.state, "nomes_pessoas", None)
        nome_de = nomes(request) if nomes else (lambda e: (e or "Sem conta").split("@")[0])
        datas = [date.fromtimestamp(e.timestamp) for e in eventos if e.timestamp]
        c = conteudo(eventos, nome_de, de=min(datas) if datas else None, ate=max(datas) if datas else None,
                     mostrar_lotes=False)
        andamento = f'{numero(lote["inspecionadas"])} de {numero(lote["quantidade"])} ({pct(min(1, lote["inspecionadas"] / max(1, lote["quantidade"])))})'
        indicadores = c["indicadores"]
        indicadores[0] = ("Inspecionadas", numero(lote["inspecionadas"]), f'de {numero(lote["quantidade"])} do lote')
        dados = relatorio(
            rotulo=f'Qualidade do lote {lote["codigo"]}',
            sobretitulo="Relatório de qualidade do lote",
            titulo=f'Lote {lote["codigo"]}',
            subtitulo=lote["cliente"] + (f' · {lote["modelo_peca"]}' if lote["modelo_peca"] else ""),
            ficha=[("Cliente", lote["cliente"]), ("Andamento", andamento),
                   ("Situação", "Concluído" if lote["concluido"] else "Em aberto"),
                   ("Pessoas · máquinas", f'{c["pessoas"]} · {c["maquinas"]}')],
            indicadores=indicadores,
            secoes=c["secoes"],
            nota=NOTA,
        )
        nome = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in str(lote["codigo"]))
        return Response(dados, media_type='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename="qualidade-{nome}.pdf"'})
