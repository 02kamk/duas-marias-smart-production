"""Conteúdo dos relatórios de qualidade em PDF (período e lote).

Uma página de visão geral (números, o que merece atenção, produção por dia,
defeitos por tipo, máquinas, pessoas e lotes) e, depois, a lista das peças com
defeito com quem inspecionou e em qual máquina. A lista mostra no máximo as
`MAX_PECAS` mais recentes, para o relatório não virar um catálogo.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

from pontocerto.app.pdf import numero, pct, pecas
from pontocerto.labels import CLASS_KEYS, class_by_key

MAX_PECAS = 40
MIN_PECAS_COMPARAR = 10   # abaixo disso, uma taxa alta é sorte/azar, não sinal
TAXA_ALERTA = 0.10
TOP_TIPOS = 6

NOTA = ("Cada peça foi fotografada e lida por um modelo de inteligência artificial de visão, que indica se há "
        "defeito de costura ou de tecido e qual é. Peças com defeito ou leitura incerta passam por conferência "
        "humana; quando a pessoa corrigiu a leitura, vale a classe corrigida. As comparações entre máquinas e "
        f"pessoas só consideram quem tem {MIN_PECAS_COMPARAR} peças ou mais. Os percentuais não substituem a "
        "inspeção final do cliente.")


def _nome_classe(chave: str) -> str:
    return class_by_key(chave).pt if chave in CLASS_KEYS else chave


def _taxa(defeitos: int, total: int) -> float:
    return defeitos / total if total else 0.0


def _situacao(e) -> str:
    if e.revisao_humana:
        return "Corrigida" if e.revisao_humana.get("decisao") == "corrigida" else "Confirmada"
    return "A conferir" if e.precisa_revisao else "Automática"


def _grupos(eventos, chave):
    g = defaultdict(list)
    for e in eventos:
        g[chave(e)].append(e)
    linhas = []
    for k, lista in g.items():
        d = sum(e.classe_final != "normal" for e in lista)
        linhas.append({"chave": k, "total": len(lista), "defeitos": d, "taxa": _taxa(d, len(lista)), "eventos": lista})
    return sorted(linhas, key=lambda x: (-x["total"]))


def _pior(grupos, rotulo):
    """O grupo com maior taxa de defeito entre os que têm peças suficientes."""
    validos = [g for g in grupos if g["chave"] and g["total"] >= MIN_PECAS_COMPARAR and g["defeitos"]]
    if len(validos) < 2:
        return None
    pior = max(validos, key=lambda g: g["taxa"])
    media = _taxa(sum(g["defeitos"] for g in validos), sum(g["total"] for g in validos))
    if pior["taxa"] < media * 1.25:
        return None  # ninguém se destaca de verdade
    return (f"{rotulo} <b>{escape(str(pior['nome']))}</b> teve a maior taxa de defeito: "
            f"<b>{pct(pior['taxa'])}</b> em {pecas(pior['total'])} (média de {pct(media)}).")


def conteudo(eventos, nome_de, *, de: date | None = None, ate: date | None = None,
             mostrar_lotes: bool = True) -> dict:
    """indicadores, secoes e totais para `pdf.relatorio`. `nome_de(email)` dá o nome da pessoa."""
    eventos = sorted(eventos, key=lambda e: e.timestamp, reverse=True)
    total = len(eventos)
    com_defeito = [e for e in eventos if e.classe_final != "normal"]
    n_def = len(com_defeito)
    conferidas = [e for e in eventos if e.revisao_humana]
    corrigidas = [e for e in conferidas if e.revisao_humana.get("decisao") == "corrigida"]
    pendentes = sum(e.precisa_revisao for e in eventos)

    por_maquina = _grupos(eventos, lambda e: e.maquina_nome)
    for g in por_maquina:
        g["nome"] = g["chave"] or "Sem máquina"
    por_pessoa = _grupos(eventos, lambda e: e.autor)
    for g in por_pessoa:
        g["nome"] = nome_de(g["chave"])
        maq = Counter(e.maquina_nome for e in g["eventos"] if e.maquina_nome).most_common(1)
        g["maquina"] = maq[0][0] if maq else "—"
    por_lote = _grupos(eventos, lambda e: e.lote_codigo)
    tipos = Counter(e.classe_final for e in com_defeito).most_common()

    # --- o que merece atenção (no máximo 4 frases)
    frases = []
    if total and tipos:
        c, q = tipos[0]
        frases.append(f"<b>{escape(_nome_classe(c))}</b> foi o defeito mais comum: {pecas(q)}, "
                      f"{pct(q / n_def)} dos defeitos.")
    for frase in (_pior(por_maquina, "A máquina"), _pior(por_pessoa, "")):
        if frase:
            frases.append(frase.strip())
    if pendentes:
        frases.append(f"<b>{pecas(pendentes)}</b> ainda {'aguarda' if pendentes == 1 else 'aguardam'} conferência.")
    if conferidas and len(frases) < 4:
        frases.append(f"Na conferência, a leitura da IA foi corrigida em {numero(len(corrigidas))} de "
                      f"{pecas(len(conferidas))} ({pct(_taxa(len(corrigidas), len(conferidas)))}).")
    if total and not n_def:
        frases.append("Nenhuma peça com defeito no período.")

    secoes = []
    if frases:
        secoes.append({"destaques": frases[:4]})

    # --- produção por dia (só quando há mais de um dia e não é longo demais); entra depois dos tipos
    grafico = None
    if de and ate and 1 <= (ate - de).days <= 62:
        dias = Counter(date.fromtimestamp(e.timestamp) for e in eventos)
        dias_def = Counter(date.fromtimestamp(e.timestamp) for e in com_defeito)
        itens, d = [], de
        while d <= ate:
            itens.append((d.strftime("%d/%m"), dias[d] - dias_def[d], dias_def[d]))
            d += timedelta(days=1)
        if any(a + b for _, a, b in itens):
            grafico = {"titulo": "Produção por dia", "grafico_dias": itens}

    # --- defeitos por tipo | máquinas
    barras = [(_nome_classe(c), q / n_def, f"{numero(q)} · {pct(q / n_def)}") for c, q in tipos[:TOP_TIPOS]]
    resto = sum(q for _, q in tipos[TOP_TIPOS:])
    if resto:
        barras.append(("Outros tipos", resto / n_def, f"{numero(resto)} · {pct(resto / n_def)}"))
    sec_tipos = {"titulo": "Defeitos por tipo", "barras": barras,
                 "vazio": "Nenhum defeito no período." if total else "Nenhuma peça no período."}
    linhas_m = [[g["nome"], numero(g["total"]), pct(g["taxa"])] for g in por_maquina]
    alerta_m = [(i, 2) for i, g in enumerate(por_maquina) if g["total"] >= MIN_PECAS_COMPARAR and g["taxa"] >= TAXA_ALERTA]
    sec_maq = {"titulo": "Por máquina", "tabela": {"colunas": ["Máquina", "Peças", "Defeito"], "linhas": linhas_m,
                                                  "larguras": [0.56, 0.22, 0.22], "direita": (1, 2), "alerta": alerta_m},
               "vazio": "Nenhuma peça no período."}
    secoes.append({"colunas": [sec_tipos, sec_maq]})
    if grafico:
        secoes.append(grafico)

    # --- pessoas
    if len(por_pessoa) > 1 or (por_pessoa and por_pessoa[0]["chave"]):
        secoes.append({"titulo": "Por pessoa", "tabela": {
            "colunas": ["Pessoa", "Peças", "Com defeito", "Taxa", "Máquina mais usada"],
            "linhas": [[g["nome"], numero(g["total"]), numero(g["defeitos"]), pct(g["taxa"]), g["maquina"]] for g in por_pessoa],
            "larguras": [0.32, 0.12, 0.15, 0.12, 0.29], "direita": (1, 2, 3),
            "alerta": [(i, 3) for i, g in enumerate(por_pessoa) if g["total"] >= MIN_PECAS_COMPARAR and g["taxa"] >= TAXA_ALERTA]}})

    # --- lotes (no relatório do período)
    if mostrar_lotes and any(g["chave"] for g in por_lote):
        top = por_lote[:10]
        secoes.append({"titulo": "Por lote",
                       "texto": None if len(por_lote) <= 10 else f"Os 10 lotes com mais peças, de {numero(len(por_lote))}.",
                       "tabela": {
            "colunas": ["Lote", "Peças", "Com defeito", "Taxa"],
            "linhas": [[g["chave"] or "Sem lote", numero(g["total"]), numero(g["defeitos"]), pct(g["taxa"])] for g in top],
            "larguras": [0.46, 0.18, 0.18, 0.18], "direita": (1, 2, 3)}})

    # --- peças com defeito: quem, onde e quando
    if com_defeito:
        mostradas = com_defeito[:MAX_PECAS]
        texto = (f"As {numero(MAX_PECAS)} mais recentes de {pecas(n_def)}." if n_def > MAX_PECAS
                 else f"{pecas(n_def)}, da mais recente para a mais antiga.")
        # Só entram as colunas que dizem algo (ex.: sem lote nenhum, a coluna Lote sai).
        campos = [("Quando", 0.13, lambda e: datetime.fromtimestamp(e.timestamp).strftime("%d/%m %H:%M")),
                  ("Defeito", 0.25, lambda e: _nome_classe(e.classe_final))]
        if len({e.autor for e in com_defeito}) > 1 or any(e.autor for e in com_defeito):
            campos.append(("Pessoa", 0.19, lambda e: nome_de(e.autor)))
        if any(e.maquina_nome for e in com_defeito):
            campos.append(("Máquina", 0.17, lambda e: e.maquina_nome or "—"))
        if mostrar_lotes and any(e.lote_codigo for e in com_defeito):
            campos.append(("Lote", 0.12, lambda e: e.lote_codigo or "—"))
        campos.append(("Conferência", 0.14, _situacao))
        soma = sum(f for _, f, _ in campos)
        secoes.append({"titulo": "Peças com defeito", "texto": texto, "tabela": {
            "colunas": [n for n, _, _ in campos], "larguras": [f / soma for _, f, _ in campos], "compacta": True,
            "linhas": [[fn(e) for _, _, fn in campos] for e in mostradas]}})

    indicadores = [("Inspecionadas", numero(total), None),
                   ("Aprovadas", numero(total - n_def), pct(1 - _taxa(n_def, total)) if total else None),
                   ("Com defeito", numero(n_def), pct(_taxa(n_def, total)) if total else None),
                   ("Aguardando conferência", numero(pendentes), None)]
    return {"indicadores": indicadores, "secoes": secoes, "pessoas": len(por_pessoa),
            "maquinas": len([g for g in por_maquina if g["chave"]]), "lotes": len([g for g in por_lote if g["chave"]])}
