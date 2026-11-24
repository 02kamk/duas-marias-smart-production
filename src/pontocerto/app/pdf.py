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


def _ficha(itens):
    """Dados do relatório em duas colunas de pares rótulo/valor."""
    celulas = [[_p(r, E_ROTULO), _p(v, E_VALOR)] for r, v in itens if v not in (None, "")]
    if len(celulas) % 2:
        celulas.append(["", ""])
    linhas = [[a[0], b[0]] for a, b in zip(celulas[0::2], celulas[1::2])]
    valores = [[a[1], b[1]] for a, b in zip(celulas[0::2], celulas[1::2])]
    dados = []
    for r, v in zip(linhas, valores):
        dados += [r, v]
    t = Table(dados, colWidths=[LARGURA / 2] * 2)
    estilo = [("BACKGROUND", (0, 0), (-1, -1), OSSO), ("LEFTPADDING", (0, 0), (-1, -1), 12),
              ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
              ("ROUNDEDCORNERS", [6, 6, 6, 6])]
    for i in range(0, len(dados), 2):
        estilo += [("TOPPADDING", (0, i), (-1, i), 9 if i == 0 else 7), ("BOTTOMPADDING", (0, i + 1), (-1, i + 1), 9 if i + 2 >= len(dados) else 3)]
    t.setStyle(TableStyle(estilo))
    return t


def _indicadores(itens):
    """Faixa de números grandes separados por linhas finas."""
    celulas = []
    for rotulo, valor, detalhe in itens:
        bloco = [_p(valor, E_NUMERO), Spacer(1, 3), _p(rotulo, E_ROTULO)]
        if detalhe:
            bloco.append(_p(detalhe, E_NUMERO_DETALHE))
        celulas.append(bloco)
    t = Table([celulas], colWidths=[LARGURA / len(celulas)] * len(celulas))
    estilo = [("BOX", (0, 0), (-1, -1), 0.6, LINHA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 11),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 11), ("ROUNDEDCORNERS", [6, 6, 6, 6])]
    for i in range(1, len(celulas)):
        estilo.append(("LINEBEFORE", (i, 0), (i, 0), 0.6, LINHA))
    t.setStyle(TableStyle(estilo))
    return t


def _barras(itens, vazio):
    if not itens:
        return _p(vazio, E_PEQUENO)
    largura_barra = LARGURA * 0.42
    dados = [[_p(rotulo, E_CELULA), _Barra(fracao, largura_barra), _p(valor, E_CELULA_D)]
             for rotulo, fracao, valor in itens]
    t = Table(dados, colWidths=[LARGURA * 0.34, largura_barra + 10, LARGURA * 0.24 - 10])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINHA)]))
    return t


def _tabela(colunas, linhas, larguras=None, direita=(), vazio="Nada no período."):
    if not linhas:
        return _p(vazio, E_PEQUENO)
    larguras = larguras or [1 / len(colunas)] * len(colunas)
    cab = [_p(c, E_CABECA_D if i in direita else E_CABECA) for i, c in enumerate(colunas)]
    corpo = [[_p(v, E_CELULA_D if i in direita else E_CELULA) for i, v in enumerate(l)] for l in linhas]
    t = Table([cab] + corpo, colWidths=[LARGURA * f for f in larguras], repeatRows=1)
    estilo = [("BACKGROUND", (0, 0), (-1, 0), AREIA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
              ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
              ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINHA)]
    for i in range(2, len(corpo) + 1, 2):
        estilo.append(("BACKGROUND", (0, i), (-1, i), OSSO))
    t.setStyle(TableStyle(estilo))
    return t


def relatorio(*, rotulo: str, sobretitulo: str, titulo: str, subtitulo: str, ficha, indicadores,
              secoes, nota: str) -> bytes:
    """Monta o PDF.

    ficha: [(rótulo, valor)] · indicadores: [(rótulo, valor, detalhe|None)]
    secoes: [{"titulo", "barras": [(rótulo, fração, texto)] | "tabela": {"colunas", "linhas", "larguras", "direita"}, "vazio"}]
    """
    stream = io.BytesIO()
    doc = BaseDocTemplate(stream, pagesize=A4, leftMargin=MARGEM, rightMargin=MARGEM,
                          topMargin=30 * mm, bottomMargin=22 * mm, title=f"{titulo} - Ponto Certo",
                          author="Ponto Certo")
    doc.addPageTemplates([PageTemplate(id="pagina", frames=[Frame(MARGEM, 22 * mm, LARGURA, A4[1] - 52 * mm, id="f",
                                                                    leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)])])
    gerado = datetime.now().strftime("%d/%m/%Y às %H:%M")
    historia = [_p(sobretitulo.upper(), E_SOBRETITULO), Spacer(1, 4), _p(titulo, E_TITULO), Spacer(1, 4),
                _p(subtitulo, E_SUBTITULO), Spacer(1, 14), _ficha(list(ficha) + [("Gerado em", gerado)]),
                Spacer(1, 14), _indicadores(indicadores), Spacer(1, 20)]
    for secao in secoes:
        corpo = (_barras(secao["barras"], secao.get("vazio", "Nada no período."))
                 if "barras" in secao else _tabela(vazio=secao.get("vazio", "Nada no período."), **secao["tabela"]))
        cabeca = [_p(secao["titulo"], E_SECAO)]
        if secao.get("texto"):
            cabeca += [_p(secao["texto"], E_PEQUENO), Spacer(1, 6)]
        if "barras" in secao:
            historia += [KeepTogether(cabeca + [corpo]), Spacer(1, 18)]
        else:
            historia += cabeca + [corpo, Spacer(1, 18)]
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
