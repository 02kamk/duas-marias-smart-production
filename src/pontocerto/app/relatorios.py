"""Números para a tela Início e para os Relatórios (período, defeitos, lotes e PDF)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import Response

from pontocerto.labels import CLASS_KEYS, class_by_key

MAX_DIAS = 366


def _nome(chave: str) -> str:
    return class_by_key(chave).pt if chave in CLASS_KEYS else chave


def _pct(parte: int, total: int) -> float:
    return round(parte / total, 4) if total else 0.0


def resumir(eventos) -> dict:
    """Resumo de uma lista de `Evento`, sempre pela classe que vale (a corrigida, se houver)."""
    total = len(eventos)
    defeitos = [e for e in eventos if e.classe_final != "normal"]
    por_tipo = Counter(e.classe_final for e in defeitos)
    lotes: dict[str, list[int]] = {}
    for e in eventos:
        item = lotes.setdefault(e.lote_codigo or "", [0, 0])
        item[0] += 1
        item[1] += e.classe_final != "normal"
    dias = Counter()
    dias_def = Counter()
    for e in eventos:
        dia = date.fromtimestamp(e.timestamp).isoformat()
        dias[dia] += 1
        dias_def[dia] += e.classe_final != "normal"
    return {
        "total": total,
        "aprovadas": total - len(defeitos),
        "defeitos": len(defeitos),
        "taxa_defeito": _pct(len(defeitos), total),
        "conferidas": sum(bool(e.revisao_humana) for e in eventos),
        "corrigidas": sum(bool(e.rotulo_operador and e.rotulo_operador != e.classe_key) for e in eventos),
        "pendentes": sum(e.precisa_revisao for e in eventos),
        "defeitos_por_tipo": [{"classe": c, "nome": _nome(c), "quantidade": q,
                               "parcela": _pct(q, len(defeitos))} for c, q in por_tipo.most_common()],
        "por_lote": sorted(({"codigo": cod or None, "inspecionadas": n, "defeitos": d, "taxa_defeito": _pct(d, n)}
                            for cod, (n, d) in lotes.items()), key=lambda x: (x["codigo"] is None, -x["inspecionadas"])),
        "por_dia": [{"data": d, "total": dias[d], "defeitos": dias_def[d]} for d in sorted(dias)],
    }


def _periodo(de: date | None, ate: date | None, dia: date | None):
    hoje = date.today()
    if dia:
        de = ate = dia
    ate = ate or hoje
    de = de or ate
    if de > ate:
        de, ate = ate, de
    if (ate - de).days >= MAX_DIAS:
        de = ate - timedelta(days=MAX_DIAS - 1)
    return de, ate


def _br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def registrar(app: FastAPI) -> None:
    def eventos(de: date, ate: date):
        return app.state.estado.eventos_periodo(de.isoformat(), ate.isoformat())

    @app.get("/api/relatorios/resumo")
    def resumo(de: date | None = None, ate: date | None = None, dia: date | None = None):
        de, ate = _periodo(de, ate, dia)
        return {"de": de.isoformat(), "ate": ate.isoformat(), **resumir(eventos(de, ate))}

    @app.get("/api/relatorios/pdf")
    def pdf(de: date | None = None, ate: date | None = None, dia: date | None = None):
        from pontocerto.app.pdf import numero, pct, pecas, relatorio
        de, ate = _periodo(de, ate, dia)
        lista = eventos(de, ate)
        r = resumir(lista)
        periodo = _br(de) if de == ate else f"{_br(de)} a {_br(ate)}"
        lotes = [l["codigo"] for l in r["por_lote"] if l["codigo"]]
        secoes = [{
            "titulo": "Defeitos por tipo",
            "texto": "Participação de cada tipo no total de peças com defeito.",
            "barras": [(d["nome"], d["parcela"], f'{pecas(d["quantidade"])} · {pct(d["parcela"])}')
                       for d in r["defeitos_por_tipo"]],
            "vazio": "Nenhum defeito no período." if r["total"] else "Nenhuma peça inspecionada no período.",
        }]
        if r["por_lote"]:
            secoes.append({"titulo": "Por lote", "tabela": {
                "colunas": ["Lote", "Inspecionadas", "Com defeito", "% com defeito"],
                "linhas": [[l["codigo"] or "Sem lote", numero(l["inspecionadas"]), numero(l["defeitos"]), pct(l["taxa_defeito"])]
                           for l in r["por_lote"]],
                "larguras": [0.4, 0.2, 0.2, 0.2], "direita": (1, 2, 3)}})
        if len(r["por_dia"]) > 1:
            secoes.append({"titulo": "Por dia", "tabela": {
                "colunas": ["Dia", "Inspecionadas", "Com defeito", "% com defeito"],
                "linhas": [[_br(date.fromisoformat(d["data"])), numero(d["total"]), numero(d["defeitos"]),
                            pct(d["defeitos"] / d["total"] if d["total"] else 0)] for d in r["por_dia"]],
                "larguras": [0.4, 0.2, 0.2, 0.2], "direita": (1, 2, 3)}})
        com_defeito = [e for e in lista if e.classe_final != "normal"]
        if com_defeito:
            def situacao(e):
                if e.revisao_humana:
                    return "Corrigida" if (e.revisao_humana.get("decisao") == "corrigida") else "Confirmada"
                return "Aguardando conferência" if e.precisa_revisao else "Automática"
            secoes.append({"titulo": "Peças com defeito",
                           "texto": pecas(len(com_defeito)) + (", mostrando as 300 mais recentes." if len(com_defeito) > 300 else "."),
                           "tabela": {
                "colunas": ["Data e hora", "Lote", "Defeito", "Conferência"],
                "linhas": [[datetime.fromtimestamp(e.timestamp).strftime("%d/%m/%Y %H:%M"), e.lote_codigo or "Sem lote",
                            _nome(e.classe_final), situacao(e)] for e in com_defeito[:300]],
                "larguras": [0.22, 0.2, 0.33, 0.25]}})
        dados = relatorio(
            rotulo="Relatório de inspeções",
            sobretitulo="Relatório de qualidade",
            titulo="Inspeções de costura",
            subtitulo=f"Período de {periodo}",
            ficha=[("Período", periodo), ("Lotes no período", ", ".join(lotes[:6]) + ("..." if len(lotes) > 6 else "") or "Sem lote"),
                   ("Peças conferidas por uma pessoa", f'{numero(r["conferidas"])} (corrigidas: {numero(r["corrigidas"])})'),
                   ("Aguardando conferência", numero(r["pendentes"]))],
            indicadores=[("Inspecionadas", numero(r["total"]), None),
                         ("Aprovadas", numero(r["aprovadas"]), pct(1 - r["taxa_defeito"]) if r["total"] else None),
                         ("Com defeito", numero(r["defeitos"]), pct(r["taxa_defeito"]) if r["total"] else None),
                         ("Conferidas", numero(r["conferidas"]), None)],
            secoes=secoes,
            nota='Cada peça foi fotografada e lida por um modelo de inteligência artificial de visão, que indica se há defeito de costura ou de tecido e qual é. Peças com defeito ou com leitura incerta passam por conferência humana; quando a pessoa corrigiu a leitura, vale a classe corrigida. Os percentuais são calculados sobre as peças inspecionadas no período e não substituem a inspeção final do cliente.',
        )
        nome = f"inspecoes-{de.isoformat()}" + ("" if de == ate else f"-a-{ate.isoformat()}")
        return Response(dados, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.pdf"'})

    @app.get("/api/perfil/atividade")
    def minha_atividade(request: Request):
        """Conferências feitas pela pessoa logada."""
        todos = app.state.estado.eventos_periodo("0000-01-01", "9999-12-31")
        return atividade(todos, str(request.state.user or "").casefold())

    @app.get("/api/inicio")
    def inicio():
        """Hoje (pela classe que vale) e os lotes em aberto, para a tela Início."""
        hoje = date.today()
        r = resumir(eventos(hoje, hoje))
        lotes, erro = [], None
        banco = getattr(app.state, "banco", None)
        if banco is not None and banco.configurado:
            try:
                from pontocerto.app.lotes import _lote_publico
                lotes = [l for l in (_lote_publico(x) for x in banco.listar_lotes()) if not l["concluido"]]
            except Exception:
                erro = "Sem conexão com o Supabase agora."
        return {"hoje": {"data": hoje.isoformat(), **r}, "lotes": lotes[:6], "total_lotes": len(lotes),
                "lote_ativo": app.state.estado.lote_ativo, "erro_lotes": erro}


def atividade(eventos, email: str, agora: float | None = None) -> dict:
    """O que a pessoa conferiu: hoje, últimos 7 dias, total, quantas corrigiu e as últimas."""
    import time as _time
    agora = agora or _time.time()
    hoje = date.fromtimestamp(agora)
    semana = hoje - timedelta(days=6)
    minhas = [e for e in eventos if e.revisao_humana and str(e.revisao_humana.get("autor") or "").casefold() == email]
    minhas.sort(key=lambda e: e.revisao_humana.get("timestamp") or e.timestamp, reverse=True)

    def dia(e):
        return date.fromtimestamp(e.revisao_humana.get("timestamp") or e.timestamp)

    return {
        "hoje": sum(dia(e) == hoje for e in minhas),
        "semana": sum(dia(e) >= semana for e in minhas),
        "total": len(minhas),
        "corrigidas": sum(e.revisao_humana.get("decisao") == "corrigida" for e in minhas),
        "ultimas": [{
            "id": e.id, "nome": _nome(e.classe_final), "imagem": e.imagem, "lote": e.lote_codigo,
            "corrigida": e.revisao_humana.get("decisao") == "corrigida",
            "quando": e.revisao_humana.get("timestamp") or e.timestamp,
        } for e in minhas[:6]],
    }
