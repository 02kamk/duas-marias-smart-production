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


def numero_txt(n: int) -> str:
    return "—" if not n else f"{n:,}".replace(",", ".")


def registrar(app: FastAPI) -> None:
    from pontocerto.app.maquinas import quem

    def eventos(de: date, ate: date, request: Request, equipe: bool = False):
        """Peças da conta que pede; com `equipe`, o administrador recebe as de todas as contas."""
        email, admin = quem(app, request)
        return app.state.estado.eventos_periodo(de.isoformat(), ate.isoformat(), email, admin,
                                                todos=bool(equipe and admin))

    def nomes(request: Request):
        """email -> nome da pessoa (o começo do e-mail quando ela não pôs nome)."""
        contas = getattr(app.state, "accounts", None)
        try:
            perfis = contas.perfis() if contas is not None else {}
        except Exception:
            perfis = {}

        def nome_de(email):
            if not email:
                return "Sem conta"
            return (perfis.get(email) or {}).get("nome") or email.split("@")[0]
        return nome_de

    @app.get("/api/relatorios/resumo")
    def resumo(request: Request, de: date | None = None, ate: date | None = None, dia: date | None = None):
        de, ate = _periodo(de, ate, dia)
        _, admin = quem(app, request)
        return {"de": de.isoformat(), "ate": ate.isoformat(),
                "escopo": "equipe" if admin and getattr(app.state, "accounts", None) else "conta",
                **resumir(eventos(de, ate, request, equipe=True))}

    @app.get("/api/relatorios/pdf")
    def pdf(request: Request, de: date | None = None, ate: date | None = None, dia: date | None = None):
        from pontocerto.app.pdf import relatorio
        from pontocerto.app.relatorio_pdf import NOTA, conteudo
        de, ate = _periodo(de, ate, dia)
        email, admin = quem(app, request)
        nome_de = nomes(request)
        equipe = bool(admin and getattr(app.state, "accounts", None))
        c = conteudo(eventos(de, ate, request, equipe=True), nome_de, de=de, ate=ate)
        periodo = _br(de) if de == ate else f"{_br(de)} a {_br(ate)}"
        dados = relatorio(
            rotulo="Relatório de inspeções · " + periodo,
            sobretitulo="Relatório de qualidade",
            titulo="Inspeções de costura",
            subtitulo=(f"Período de {periodo}" if de != ate else f"Dia {periodo}")
                      + (" · toda a equipe" if equipe else (f" · {nome_de(email)}" if email else "")),
            ficha=[("Pessoas", numero_txt(c["pessoas"])),
                   ("Máquinas", numero_txt(c["maquinas"])), ("Lotes", numero_txt(c["lotes"]))],
            indicadores=c["indicadores"],
            secoes=c["secoes"],
            nota=NOTA,
        )
        nome = f"inspecoes-{de.isoformat()}" + ("" if de == ate else f"-a-{ate.isoformat()}")
        return Response(dados, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.pdf"'})

    app.state.nomes_pessoas = nomes

    @app.get("/api/perfil/atividade")
    def minha_atividade(request: Request):
        """Conferências feitas pela pessoa logada."""
        email, admin = quem(app, request)
        todos = app.state.estado.eventos_periodo("0000-01-01", "9999-12-31", email, admin)
        return atividade(todos, str(request.state.user or "").casefold())

    @app.get("/api/inicio")
    def inicio(request: Request):
        """Hoje (pela classe que vale) e os lotes em aberto, para a tela Início."""
        hoje = date.today()
        r = resumir(eventos(hoje, hoje, request))
        lotes, erro = [], None
        banco = getattr(app.state, "banco", None)
        if banco is not None and banco.configurado:
            try:
                from pontocerto.app.lotes import _lote_publico
                lotes = [l for l in (_lote_publico(x) for x in banco.listar_lotes()) if not l["concluido"]]
            except Exception:
                erro = "Sem conexão com o Supabase agora."
        return {"hoje": {"data": hoje.isoformat(), **r}, "lotes": lotes[:6], "total_lotes": len(lotes),
                "lote_ativo": app.state.estado.lote_de(quem(app, request)[0]), "erro_lotes": erro}


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
