"""Relatórios em PDF com a identidade do Ponto Certo.

Cabeçalho com a marca e rodapé com "página X de Y" em todas as páginas,
bloco de abertura com a ficha do relatório, faixa de indicadores, barras por
tipo de defeito, tabelas e uma nota de método no fim.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)

TERRACOTA = colors.HexColor("#C1502E")
TERRACOTA_TINTA = colors.HexColor("#F7E9E2")
TINTA = colors.HexColor("#1C1917")
GRAFITE = colors.HexColor("#6B625C")
LINHA = colors.HexColor("#E4DAD1")
OSSO = colors.HexColor("#FAF7F3")
AREIA = colors.HexColor("#F2EAE3")
DEFEITO = colors.HexColor("#A3182F")

MARGEM = 18 * mm
LARGURA = A4[0] - 2 * MARGEM
PASTA_FONTES = Path(__file__).resolve().parent / "fontes_pdf"


def _registrar_fontes() -> tuple[str, str, str]:
    """Plex para o texto e Bricolage para títulos; Helvetica se os arquivos faltarem."""
    try:
        for nome, arquivo in (("Plex", "IBMPlexSans-Regular.ttf"), ("Plex-Semi", "IBMPlexSans-SemiBold.ttf"),
                              ("Bricolage", "BricolageGrotesque-Bold.ttf")):
            if nome not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(nome, str(PASTA_FONTES / arquivo)))
        return "Plex", "Plex-Semi", "Bricolage"
    except Exception:
        return "Helvetica", "Helvetica-Bold", "Helvetica-Bold"


TEXTO, NEGRITO, TITULO = _registrar_fontes()


def _estilo(nome, **kw) -> ParagraphStyle:
    base = dict(fontName=TEXTO, fontSize=9.5, leading=13.5, textColor=TINTA)
    base.update(kw)
    return ParagraphStyle(nome, **base)


E_SOBRETITULO = _estilo("sobre", fontName=NEGRITO, fontSize=8.5, textColor=TERRACOTA, leading=11)
E_TITULO = _estilo("titulo", fontName=TITULO, fontSize=26, leading=30)
E_SUBTITULO = _estilo("subtitulo", fontSize=11, leading=15, textColor=GRAFITE)
E_SECAO = _estilo("secao", fontName=TITULO, fontSize=13.5, leading=17, spaceBefore=4, spaceAfter=8)
E_TEXTO = _estilo("texto")
E_PEQUENO = _estilo("pequeno", fontSize=8, leading=11, textColor=GRAFITE)
E_ROTULO = _estilo("rotulo", fontSize=8, leading=10, textColor=GRAFITE)
E_VALOR = _estilo("valor", fontName=NEGRITO, fontSize=9.5, leading=12)
E_CELULA = _estilo("celula", fontSize=8.8, leading=11.5)
E_CELULA_D = _estilo("celula_d", fontSize=8.8, leading=11.5, alignment=TA_RIGHT)
E_CABECA = _estilo("cabeca", fontName=NEGRITO, fontSize=8, leading=10, textColor=GRAFITE)
E_CABECA_D = _estilo("cabeca_d", fontName=NEGRITO, fontSize=8, leading=10, textColor=GRAFITE, alignment=TA_RIGHT)
E_NUMERO = _estilo("numero", fontName=TITULO, fontSize=22, leading=25)
E_NUMERO_DETALHE = _estilo("numero_det", fontSize=8, leading=10, textColor=GRAFITE)


def _p(texto, estilo=E_TEXTO) -> Paragraph:
    return Paragraph(escape(str(texto)), estilo)


def _logo(c, x, y, lado):
    """Quadrado terracota com o ✓ de costura tracejado."""
    c.saveState()
    c.setFillColor(TERRACOTA)
    c.roundRect(x, y, lado, lado, lado * 0.29, stroke=0, fill=1)
    c.setStrokeColor(colors.white)
    c.setLineWidth(lado * 0.095)
    c.setLineCap(1)
    c.setLineJoin(1)
    k = lado / 34.0
    p = c.beginPath()
    p.moveTo(x + 9 * k, y + (34 - 17.5) * k)
    p.lineTo(x + 14.5 * k, y + (34 - 23) * k)
    p.lineTo(x + 25.5 * k, y + (34 - 11) * k)
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


class _CanvasNumerado(rl_canvas.Canvas):
    """Guarda as páginas para escrever "página X de Y" no fim."""

    def __init__(self, *args, rotulo="", **kw):
        super().__init__(*args, **kw)
        self._paginas = []
        self._rotulo = rotulo

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._moldura(total)
            super().showPage()
        super().save()

    def _moldura(self, total):
        largura, altura = A4
        topo = altura - 12 * mm
        _logo(self, MARGEM, topo - 5.5 * mm, 7 * mm)
        self.setFont(TITULO, 12)
        self.setFillColor(TINTA)
        self.drawString(MARGEM + 9 * mm, topo - 3.6 * mm, "Ponto")
        largura_ponto = pdfmetrics.stringWidth("Ponto", TITULO, 12)
        self.setFillColor(TERRACOTA)
        self.drawString(MARGEM + 9 * mm + largura_ponto, topo - 3.6 * mm, "Certo")
        self.setFont(TEXTO, 8)
        self.setFillColor(GRAFITE)
        self.drawRightString(largura - MARGEM, topo - 3.4 * mm, self._rotulo)
        self.setStrokeColor(LINHA)
        self.setLineWidth(0.6)
        self.line(MARGEM, topo - 8 * mm, largura - MARGEM, topo - 8 * mm)
        self.line(MARGEM, 14 * mm, largura - MARGEM, 14 * mm)
        self.setFont(TEXTO, 7.5)
        self.drawString(MARGEM, 9.5 * mm, "Ponto Certo · Inspeção de costura com IA")
        self.drawRightString(largura - MARGEM, 9.5 * mm, f"Página {self._pageNumber} de {total}")


class _Barra(Flowable):
    def __init__(self, fracao: float, largura: float, cor=DEFEITO, altura: float = 5):
        super().__init__()
        self.fracao = max(0.0, min(1.0, float(fracao or 0)))
        self.width, self.height, self.cor = largura, altura, cor

    def draw(self):
        c = self.canv
        c.setFillColor(AREIA)
        c.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        if self.fracao > 0:
            c.setFillColor(self.cor)
            c.roundRect(0, 0, max(self.height, self.width * self.fracao), self.height, self.height / 2, stroke=0, fill=1)




APROVADA = colors.HexColor("#B9AA9C")


class _GraficoDias(Flowable):
    """Barras por dia: aprovadas embaixo, com defeito em cima, grade discreta e legenda."""

    def __init__(self, itens, largura: float = LARGURA, altura: float = 36 * mm):
        super().__init__()
        self.itens = list(itens)  # [(rótulo, aprovadas, defeitos)]
        self.width, self.height = largura, altura

    def draw(self):
        c = self.canv
        esq, base, topo_livre = 22, 14, 14
        w, h = self.width - esq, self.height - base - topo_livre
        maximo = max([a + d for _, a, d in self.itens] + [1])
        bruto = maximo / 3
        mag = 10 ** max(0, len(str(int(bruto))) - 1)
        passo = next(p * mag for p in (1, 2, 2.5, 5, 10) if p * mag >= bruto)
        teto = max(passo, -(-maximo // passo) * passo)
        c.setFont(TEXTO, 6.5)
        v = 0
        while v <= teto + 1e-9:
            y = base + h * v / teto
            c.setStrokeColor(LINHA if v else colors.HexColor("#CFC2B6"))
            c.setLineWidth(0.5 if v else 0.7)
            c.setDash(1.5, 2.5) if v else c.setDash()
            c.line(esq, y, self.width, y)
            c.setFillColor(GRAFITE)
            c.drawRightString(esq - 5, y - 2.2, numero(v))
            v += passo
        c.setDash()
        n = max(1, len(self.itens))
        fatia = w / n
        larg = max(1.5, min(16, fatia * 0.62))
        cada = max(1, -(-n // max(1, int(w // 34))))
        for i, (rotulo, aprov, defe) in enumerate(self.itens):
            x = esq + fatia * i + (fatia - larg) / 2
            ha, hd = h * aprov / teto, h * defe / teto
            if ha:
                c.setFillColor(APROVADA)
                c.rect(x, base, larg, ha, stroke=0, fill=1)
            if hd:
                c.setFillColor(DEFEITO)
                c.rect(x, base + ha + (0.8 if ha else 0), larg, hd, stroke=0, fill=1)
            if i % cada == 0:
                c.setFillColor(GRAFITE)
                c.drawCentredString(x + larg / 2, base - 9, rotulo)
        # legenda
        c.setFont(TEXTO, 7)
        x = self.width
        for nome, cor in (("Com defeito", DEFEITO), ("Aprovadas", APROVADA)):
            tw = pdfmetrics.stringWidth(nome, TEXTO, 7)
            x -= tw
            c.setFillColor(GRAFITE)
            c.drawString(x, self.height - 7, nome)
            x -= 9
            c.setFillColor(cor)
            c.roundRect(x, self.height - 7.5, 6, 6, 1.5, stroke=0, fill=1)
            x -= 12


def _meta(itens):
    """Linha fina com os dados do relatório: rótulo pequeno em cima, valor embaixo."""
    itens = [(r, v) for r, v in itens if v not in (None, "")]
    if not itens:
        return Spacer(1, 0)
    celulas = [[_p(r, E_ROTULO), Spacer(1, 1), _p(v, E_VALOR)] for r, v in itens]
    t = Table([celulas], colWidths=[LARGURA / len(celulas)] * len(celulas))
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
              ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LINEABOVE", (0, 0), (-1, 0), 0.6, LINHA),
              ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINHA)]
    t.setStyle(TableStyle(estilo))
    return t


def _ficha(itens):
    return _meta(itens)


def _indicadores(itens):
    """Faixa de números grandes separados por linhas finas."""
    celulas = []
    for rotulo, valor, detalhe in itens:
        bloco = [_p(valor, E_NUMERO), Spacer(1, 3), _p(rotulo, E_ROTULO)]
        if detalhe:
            bloco.append(_p(detalhe, E_NUMERO_DETALHE))
        celulas.append(bloco)
    t = Table([celulas], colWidths=[LARGURA / len(celulas)] * len(celulas))
    estilo = [("BACKGROUND", (0, 0), (-1, -1), OSSO), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 11),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 11), ("ROUNDEDCORNERS", [6, 6, 6, 6])]
    for i in range(1, len(celulas)):
        estilo.append(("LINEBEFORE", (i, 0), (i, 0), 0.6, LINHA))
    t.setStyle(TableStyle(estilo))
    return t


E_DESTAQUE = _estilo("destaque", fontSize=9.3, leading=13.5)
E_DESTAQUE_TITULO = _estilo("destaque_t", fontName=NEGRITO, fontSize=8, leading=10, textColor=TERRACOTA)


def _destaques(frases, largura=LARGURA):
    """Caixa com o que merece atenção, em frases curtas (aceita <b>negrito</b>)."""
    corpo = [_p("O QUE MERECE ATENÇÃO", E_DESTAQUE_TITULO), Spacer(1, 4)]
    for f in frases:
        corpo.append(Paragraph("•&nbsp;&nbsp;" + f, E_DESTAQUE))
        corpo.append(Spacer(1, 2))
    t = Table([[corpo]], colWidths=[largura])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TERRACOTA_TINTA), ("LEFTPADDING", (0, 0), (-1, -1), 14),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 14), ("TOPPADDING", (0, 0), (-1, -1), 10),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LINEBEFORE", (0, 0), (0, -1), 3, TERRACOTA),
                           ("ROUNDEDCORNERS", [4, 4, 4, 4])]))
    return t


def _barras(itens, vazio, largura=LARGURA):
    if not itens:
        return _p(vazio, E_PEQUENO)
    estreito = largura < LARGURA * 0.7
    if estreito:
        # Meia largura: rótulo e número em cima, barra embaixo.
        dados = []
        for rotulo, fracao, valor in itens:
            dados.append([_p(rotulo, E_CELULA), _p(valor, E_CELULA_D)])
            dados.append([_Barra(fracao, largura, altura=4), ""])
        t = Table(dados, colWidths=[largura * 0.62, largura * 0.38])
        estilo = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                  ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]
        for i in range(1, len(dados), 2):
            estilo += [("SPAN", (0, i), (1, i)), ("BOTTOMPADDING", (0, i), (-1, i), 5)]
        t.setStyle(TableStyle(estilo))
        return t
    largura_barra = largura * 0.42
    dados = [[_p(rotulo, E_CELULA), _Barra(fracao, largura_barra), _p(valor, E_CELULA_D)]
             for rotulo, fracao, valor in itens]
    t = Table(dados, colWidths=[largura * 0.34, largura_barra + 10, largura * 0.24 - 10])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINHA)]))
    return t


E_CELULA_P = _estilo("celula_p", fontSize=7.8, leading=10)
E_CELULA_PD = _estilo("celula_pd", fontSize=7.8, leading=10, alignment=TA_RIGHT)
E_CELULA_DEF = _estilo("celula_def", fontName=NEGRITO, fontSize=8.8, leading=11.5, textColor=DEFEITO, alignment=TA_RIGHT)


def _tabela(colunas, linhas, larguras=None, direita=(), vazio="Nada no período.", largura=LARGURA,
            compacta=False, alerta=None):
    """Tabela com cabeçalho repetido a cada página. `alerta`: {(linha, coluna)} pintadas de vermelho."""
    if not linhas:
        return _p(vazio, E_PEQUENO)
    larguras = larguras or [1 / len(colunas)] * len(colunas)
    normal, normal_d = (E_CELULA_P, E_CELULA_PD) if compacta else (E_CELULA, E_CELULA_D)
    alerta = set(map(tuple, alerta or ()))
    cab = [_p(c, E_CABECA_D if i in direita else E_CABECA) for i, c in enumerate(colunas)]
    corpo = [[_p(v, E_CELULA_DEF if (j, i) in alerta else (normal_d if i in direita else normal))
              for i, v in enumerate(l)] for j, l in enumerate(linhas)]
    t = Table([cab] + corpo, colWidths=[largura * f for f in larguras], repeatRows=1)
    pad = 4 if compacta else 6
    estilo = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#CFC2B6")),
              ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
              ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
              ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
              ("LINEBELOW", (0, 1), (-1, -2), 0.4, LINHA)]
    t.setStyle(TableStyle(estilo))
    return t


def _secao(secao, largura=LARGURA):
    """Título (+ texto) e o corpo de uma seção, como lista de flowables."""
    vazio = secao.get("vazio", "Nada no período.")
    if "barras" in secao:
        corpo = _barras(secao["barras"], vazio, largura)
    elif "grafico_dias" in secao:
        corpo = _GraficoDias(secao["grafico_dias"], largura)
    elif "destaques" in secao:
        corpo = _destaques(secao["destaques"], largura)
    else:
        corpo = _tabela(vazio=vazio, largura=largura, **secao["tabela"])
    cabeca = [_p(secao["titulo"], E_SECAO)] if secao.get("titulo") else []
    if secao.get("texto"):
        cabeca += [_p(secao["texto"], E_PEQUENO), Spacer(1, 6)]
    return cabeca, corpo


def relatorio(*, rotulo: str, sobretitulo: str, titulo: str, subtitulo: str, ficha, indicadores,
              secoes, nota: str) -> bytes:
    """Monta o PDF.

    ficha: [(rótulo, valor)] · indicadores: [(rótulo, valor, detalhe|None)]
    secoes: [{"titulo", "texto"?, uma de: "barras": [(rótulo, fração, texto)] | "tabela": {...}
              | "grafico_dias": [(rótulo, aprovadas, defeitos)] | "destaques": [frase],
              "vazio"?}] ou {"colunas": [seção, seção]} para duas lado a lado.
    """
    stream = io.BytesIO()
    doc = BaseDocTemplate(stream, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM,
                          topMargin=30 * mm, bottomMargin=22 * mm, title=f"{titulo} - Ponto Certo",
                          author="Ponto Certo")
    doc.addPageTemplates([PageTemplate(id="pagina", frames=[Frame(MARGEM, 22 * mm, LARGURA, A4[1] - 52 * mm, id="f",
                                                                    leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)])])
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")
    historia = [_p(sobretitulo.upper(), E_SOBRETITULO), Spacer(1, 4), _p(titulo, E_TITULO), Spacer(1, 3),
                _p(subtitulo, E_SUBTITULO), Spacer(1, 12), _meta(list(ficha) + [("Gerado em", gerado)]),
                Spacer(1, 12), _indicadores(indicadores), Spacer(1, 16)]
    for secao in secoes:
        if "colunas" in secao:
            vao = 8 * mm
            meia = (LARGURA - vao) / 2
            partes = [_secao(s, meia) for s in secao["colunas"]]
            t = Table([[cab + [corpo] for cab, corpo in partes]], colWidths=[meia + vao, meia])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (0, -1), vao), ("RIGHTPADDING", (1, 0), (1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
            historia += [t, Spacer(1, 16)]
            continue
        cabeca, corpo = _secao(secao)
        if "tabela" in secao and len(secao["tabela"].get("linhas") or []) > 12:
            historia += cabeca + [corpo, Spacer(1, 16)]
        else:
            historia += [KeepTogether(cabeca + [corpo]), Spacer(1, 16)]
    linha = Table([[""]], colWidths=[LARGURA], rowHeights=[1])
    linha.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.6, LINHA)]))
    historia += [KeepTogether([linha, Spacer(1, 6), _p("Sobre este relatório", _estilo("ns", fontName=NEGRITO, fontSize=8.5, textColor=TINTA)),
                               Spacer(1, 2), _p(nota, E_PEQUENO)])]
    doc.build(historia, canvasmaker=lambda *a, **k: _CanvasNumerado(*a, rotulo=rotulo, **k))
    return stream.getvalue()


def pct(valor: float) -> str:
    return f"{valor * 100:.1f}%".replace(".", ",")


def numero(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def pecas(valor) -> str:
    return numero(valor) + (" peça" if int(valor) == 1 else " peças")
