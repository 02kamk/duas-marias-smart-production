"""Análise da equipe para o administrador: produtividade e qualidade por pessoa e por máquina.

Só administradores acessam. Os números saem das peças registradas (todas as
contas), sempre pela classe que vale (a corrigida na conferência, se houver).

Produtividade: o tempo ativo de cada pessoa é a soma dos intervalos entre peças
seguidas de até 15 minutos (pausas maiores contam como parada) mais 1 minuto por
sequência, para a primeira peça. Peças por hora = peças / horas ativas.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import median

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from pontocerto.labels import CLASS_KEYS, class_by_key

PAUSA_S = 15 * 60       # intervalo maior que isso é parada, não trabalho
PRIMEIRA_S = 60         # tempo atribuído à primeira peça de cada sequência
MIN_ATIVO_S = 10 * 60   # abaixo disso o ritmo (peças/hora) não é confiável
MAX_DIAS = 366
SEM = "sem"             # filtro: peças sem dono / sem máquina


def _nome_classe(chave: str) -> str:
    return class_by_key(chave).pt if chave in CLASS_KEYS else chave


def _pct(parte: int, total: int) -> float:
    return round(parte / total, 4) if total else 0.0


def _tempo_ativo(instantes: list[float]) -> tuple[float, list[float]]:
    """(segundos ativos, intervalos dentro das sequências) para uma lista de horários."""
    if not instantes:
        return 0.0, []
    ordenados = sorted(instantes)
    ativo, intervalos = PRIMEIRA_S, []
    for antes, depois in zip(ordenados, ordenados[1:]):
        gap = depois - antes
        if gap <= PAUSA_S:
            ativo += gap
            intervalos.append(gap)
        else:
            ativo += PRIMEIRA_S
    return float(ativo), intervalos


def _ritmo(eventos) -> dict:
    """Tempo ativo somado dia a dia (uma pausa da noite nunca vira trabalho)."""
    por_dia: dict[date, list[float]] = defaultdict(list)
    for e in eventos:
        por_dia[date.fromtimestamp(e.timestamp)].append(e.timestamp)
    ativo, intervalos = 0.0, []
    for instantes in por_dia.values():
        a, i = _tempo_ativo(instantes)
        ativo += a
        intervalos += i
    n = len(eventos)
    return {
        "horas_ativas": round(ativo / 3600, 2),
        "pecas_por_hora": round(n / (ativo / 3600), 1) if ativo >= MIN_ATIVO_S and n else None,
        "intervalo_medio_s": round(median(intervalos)) if intervalos else None,
        "dias_ativos": len(por_dia),
        "media_por_dia": round(n / len(por_dia), 1) if por_dia else 0,
    }


def _qualidade(eventos) -> dict:
    total = len(eventos)
    defeitos = [e for e in eventos if e.classe_final != "normal"]
    tipo = Counter(e.classe_final for e in defeitos).most_common(1)
    return {
        "inspecionadas": total,
        "aprovadas": total - len(defeitos),
        "defeitos": len(defeitos),
        "taxa_defeito": _pct(len(defeitos), total),
        "pendentes": sum(e.precisa_revisao for e in eventos),
        "defeito_principal": ({"classe": tipo[0][0], "nome": _nome_classe(tipo[0][0]), "quantidade": tipo[0][1]}
                              if tipo else None),
    }


def _horario(eventos) -> dict | None:
    """Horário típico: a hora da primeira e da última peça, pela mediana dos dias."""
    por_dia: dict[date, list[float]] = defaultdict(list)
    for e in eventos:
        por_dia[date.fromtimestamp(e.timestamp)].append(e.timestamp)
    if not por_dia:
        return None

    def hm(segundos: float) -> str:
        return f"{int(segundos // 3600):02d}:{int(segundos % 3600 // 60):02d}"

    def do_dia(t: float) -> float:
        d = datetime.fromtimestamp(t)
        return d.hour * 3600 + d.minute * 60 + d.second

    return {"inicio": hm(median(do_dia(min(v)) for v in por_dia.values())),
            "fim": hm(median(do_dia(max(v)) for v in por_dia.values()))}


def analisar(eventos, *, perfis: dict, contas: list[str], maquinas: list[dict],
             de: date, ate: date, usuario: str | None = None, maquina: str | None = None) -> dict:
    """Todos os números da aba Análise. `eventos`: todos do período (de todas as contas)."""
    # Opções dos filtros: contas cadastradas + quem aparece nas peças; máquinas idem.
    emails = sorted(set(contas) | {e.autor for e in eventos if e.autor})
    nomes_maquinas = {m["id"]: m["nome"] for m in maquinas}
    for e in eventos:
        if e.maquina_id and e.maquina_id not in nomes_maquinas:
            nomes_maquinas[e.maquina_id] = (e.maquina_nome or "Máquina removida") + " (removida)"

    def nome_de(email: str | None) -> str:
        if not email:
            return "Sem conta (peças antigas)"
        return (perfis.get(email) or {}).get("nome") or email.split("@")[0]

    filtrados = list(eventos)
    if usuario:
        filtrados = [e for e in filtrados if (e.autor or SEM) == usuario]
    if maquina:
        filtrados = [e for e in filtrados if (e.maquina_id or SEM) == maquina]

    conferidas = [e for e in filtrados if e.revisao_humana]
    corrigidas = [e for e in conferidas if (e.revisao_humana or {}).get("decisao") == "corrigida"]
    totais = {**_qualidade(filtrados), **_ritmo(filtrados),
              "conferidas": len(conferidas), "corrigidas": len(corrigidas),
              "acerto_ia": round(1 - len(corrigidas) / len(conferidas), 4) if conferidas else None,
              "pessoas": len({e.autor for e in filtrados}),
              "maquinas": len({e.maquina_id for e in filtrados if e.maquina_id})}

    # ---- por pessoa
    grupos: dict[str | None, list] = defaultdict(list)
    for e in filtrados:
        grupos[e.autor].append(e)
    conferencias_feitas = Counter(str((e.revisao_humana or {}).get("autor") or "").casefold()
                                  for e in filtrados if e.revisao_humana)
    por_usuario = []
    for email, lista in grupos.items():
        maquina_mais = Counter(e.maquina_nome for e in lista if e.maquina_nome).most_common(1)
        conf = [e for e in lista if e.revisao_humana]
        corr = [e for e in conf if (e.revisao_humana or {}).get("decisao") == "corrigida"]
        por_usuario.append({
            "email": email, "chave": email or SEM, "nome": nome_de(email),
            "avatar": (perfis.get(email) or {}).get("avatar") if email else None,
            **_qualidade(lista), **_ritmo(lista),
            "conferencias_feitas": conferencias_feitas.get(email or "", 0),
            "corrigidas": len(corr),
            "acerto_ia": round(1 - len(corr) / len(conf), 4) if conf else None,
            "maquina_principal": maquina_mais[0][0] if maquina_mais else None,
            "ultima": max(e.timestamp for e in lista),
            "horario": _horario(lista),
        })
    por_usuario.sort(key=lambda u: (-u["inspecionadas"], u["nome"].casefold()))

    # ---- por máquina
    grupos_m: dict[str | None, list] = defaultdict(list)
    for e in filtrados:
        grupos_m[e.maquina_id].append(e)
    por_maquina = []
    for mid, lista in grupos_m.items():
        operadores = Counter(e.autor for e in lista)
        principal = operadores.most_common(1)[0][0] if operadores else None
        por_maquina.append({
            "id": mid, "chave": mid or SEM,
            "nome": nomes_maquinas.get(mid) if mid else "Sem máquina",
            **_qualidade(lista), **_ritmo(lista),
            "operadores": len(operadores), "operador_principal": nome_de(principal) if operadores else None,
        })
    por_maquina.sort(key=lambda m: (m["id"] is None, -m["inspecionadas"]))

    # ---- no tempo: dias do período (com os dias vazios) e hora do dia
    dias = Counter()
    dias_def = Counter()
    horas = Counter()
    horas_def = Counter()
    for e in filtrados:
        quando = datetime.fromtimestamp(e.timestamp)
        dias[quando.date().isoformat()] += 1
        horas[quando.hour] += 1
        if e.classe_final != "normal":
            dias_def[quando.date().isoformat()] += 1
            horas_def[quando.hour] += 1
    por_dia = []
    d = de
    while d <= ate:
        chave = d.isoformat()
        por_dia.append({"data": chave, "total": dias[chave], "defeitos": dias_def[chave]})
        d += timedelta(days=1)
    melhor = max(por_dia, key=lambda x: x["total"]) if filtrados else None

    defeitos = [e for e in filtrados if e.classe_final != "normal"]
    por_tipo = Counter(e.classe_final for e in defeitos)

    return {
        "de": de.isoformat(), "ate": ate.isoformat(),
        "filtros": {"usuario": usuario, "maquina": maquina},
        "opcoes": {
            "usuarios": [{"chave": e, "nome": nome_de(e), "email": e} for e in emails]
                        + ([{"chave": SEM, "nome": nome_de(None), "email": None}] if any(not e.autor for e in eventos) else []),
            "maquinas": [{"chave": m["id"], "nome": m["nome"], "tipo": m.get("tipo")} for m in maquinas]
                        + [{"chave": k, "nome": v, "tipo": None} for k, v in nomes_maquinas.items()
                           if k not in {m["id"] for m in maquinas}]
                        + ([{"chave": SEM, "nome": "Sem máquina", "tipo": None}] if any(not e.maquina_id for e in eventos) else []),
        },
        "totais": totais,
        "melhor_dia": melhor if melhor and melhor["total"] else None,
        "por_usuario": por_usuario,
        "por_maquina": por_maquina,
        "por_dia": por_dia,
        "por_hora": [{"hora": h, "total": horas[h], "defeitos": horas_def[h]} for h in range(24)],
        "defeitos_por_tipo": [{"classe": c, "nome": _nome_classe(c), "quantidade": q, "parcela": _pct(q, len(defeitos))}
                              for c, q in por_tipo.most_common()],
    }


def _periodo(de: date | None, ate: date | None) -> tuple[date, date]:
    ate = ate or date.today()
    de = de or (ate - timedelta(days=6))
    if de > ate:
        de, ate = ate, de
    if (ate - de).days >= MAX_DIAS:
        de = ate - timedelta(days=MAX_DIAS - 1)
    return de, ate


def registrar(app: FastAPI) -> None:
    from pontocerto.app.maquinas import quem

    def calcular(request: Request, de, ate, usuario, maquina):
        email, admin = quem(app, request)
        if not admin:
            return None
        de, ate = _periodo(de, ate)
        contas = getattr(app.state, "accounts", None)
        perfis, lista_contas = {}, []
        if contas is not None:
            try:
                perfis = contas.perfis()
                lista_contas = [c["email"] for c in contas.listar_contas()]
            except Exception:
                perfis, lista_contas = {}, []  # sem internet: mostra os e-mails das peças
        eventos = app.state.estado.eventos_periodo(de.isoformat(), ate.isoformat(), todos=True)
        return analisar(eventos, perfis=perfis, contas=lista_contas, maquinas=app.state.maquinas.listar(),
                        de=de, ate=ate, usuario=usuario or None, maquina=maquina or None)

    negado = JSONResponse(status_code=403, content={"erro": "Só um administrador vê a análise da equipe."})

    @app.get("/api/analise")
    def rota(request: Request, de: date | None = None, ate: date | None = None,
             usuario: str | None = None, maquina: str | None = None):
        r = calcular(request, de, ate, usuario, maquina)
        return negado if r is None else r

    @app.get("/api/analise/pdf")
    def pdf(request: Request, de: date | None = None, ate: date | None = None,
            usuario: str | None = None, maquina: str | None = None):
        r = calcular(request, de, ate, usuario, maquina)
        if r is None:
            return negado
        from pontocerto.app.pdf import numero, pct, relatorio

        t = r["totais"]
        br = lambda iso: date.fromisoformat(iso).strftime("%d/%m/%Y")
        periodo = br(r["de"]) if r["de"] == r["ate"] else f'{br(r["de"])} a {br(r["ate"])}'
        nome_u = next((u["nome"] for u in r["opcoes"]["usuarios"] if u["chave"] == usuario), None)
        nome_m = next((m["nome"] for m in r["opcoes"]["maquinas"] if m["chave"] == maquina), None)
        dec = lambda v: f"{v:.1f}".replace(".", ",")
        ritmo = lambda v: f"{dec(v)}/h" if v is not None else "—"
        secoes = []
        if 2 <= len(r["por_dia"]) <= 63:
            secoes.append({"titulo": "Produção por dia", "grafico_dias": [
                (date.fromisoformat(d["data"]).strftime("%d/%m"), d["total"] - d["defeitos"], d["defeitos"])
                for d in r["por_dia"]]})
        secoes += [{
            "titulo": "Por pessoa",
            "texto": "Ritmo = peças por hora de trabalho (pausas de mais de 15 minutos não contam).",
            "tabela": {"colunas": ["Pessoa", "Peças", "Ritmo", "Com defeito", "Dias", "Máquina mais usada"],
                       "linhas": [[u["nome"], numero(u["inspecionadas"]), ritmo(u["pecas_por_hora"]),
                                   pct(u["taxa_defeito"]), numero(u["dias_ativos"]), u["maquina_principal"] or "—"]
                                  for u in r["por_usuario"]],
                       "larguras": [0.26, 0.11, 0.13, 0.15, 0.09, 0.26], "direita": (1, 2, 3, 4)},
            "vazio": "Nenhuma peça no período.",
        }, {
            "titulo": "Por máquina",
            "tabela": {"colunas": ["Máquina", "Peças", "Ritmo", "Com defeito", "Operadores"],
                       "linhas": [[m["nome"], numero(m["inspecionadas"]), ritmo(m["pecas_por_hora"]),
                                   pct(m["taxa_defeito"]), numero(m["operadores"])] for m in r["por_maquina"]],
                       "larguras": [0.36, 0.14, 0.16, 0.18, 0.16], "direita": (1, 2, 3, 4)},
            "vazio": "Nenhuma peça no período.",
        }, {
            "titulo": "Defeitos por tipo",
            "barras": [(d["nome"], d["parcela"], f'{numero(d["quantidade"])} · {pct(d["parcela"])}')
                       for d in r["defeitos_por_tipo"]],
            "vazio": "Nenhum defeito no período.",
        }]
        dados = relatorio(
            rotulo="Análise da equipe", sobretitulo="Produtividade e qualidade",
            titulo="Análise da equipe", subtitulo=f"Período de {periodo}",
            ficha=[("Pessoa", nome_u or "Todas"), ("Máquina", nome_m or "Todas"),
                   ("Horas de trabalho", f'{dec(t["horas_ativas"])} h')],
            indicadores=[("Peças", numero(t["inspecionadas"]), None),
                         ("Ritmo", ritmo(t["pecas_por_hora"]), "peças por hora"),
                         ("Com defeito", pct(t["taxa_defeito"]), numero(t["defeitos"]) + " peças"),
                         ("Acerto da IA", pct(t["acerto_ia"]) if t["acerto_ia"] is not None else "—",
                          f'em {numero(t["conferidas"])} conferidas')],
            secoes=secoes,
            nota="Números calculados a partir das peças registradas por cada conta. O ritmo considera só o tempo "
                 "entre peças seguidas (até 15 minutos de intervalo) e serve para comparar períodos e acompanhar "
                 "a evolução, não para medir a jornada. A taxa de defeito usa a classe corrigida na conferência, "
                 "quando houver.",
        )
        return Response(dados, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="analise-equipe-{r["de"]}-a-{r["ate"]}.pdf"'})
