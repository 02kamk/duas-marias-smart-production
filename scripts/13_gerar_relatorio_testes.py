"""Gera o PDF com apresentação acadêmica baseada na NBR 14724:2024.

Dependência de documentação: pip install reportlab
"""
from pathlib import Path
import argparse
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, KeepTogether, PageBreak
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/testes/2026-11-14.md'
OUTPUT = ROOT / 'output/pdf/relatorio-testes-2026-11-14.pdf'
AUTHORS = ['Kamily Hilario das Luzes', 'Kaua Lucas Alves Barbosa', 'Raffael Michels Arcego']


class AcademicReport(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in ('Heading2', 'Heading3', 'ReferencesTitle'):
            level = 1 if flowable.style.name == 'Heading3' else 0
            self.notify('TOCEntry', (level, flowable.getPlainText(), self.page - 1))


def inline(value):
    value = escape(value)
    value = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', value)
    return re.sub(r'`([^`]+)`', r'\1', value)


def main():
    global SOURCE, OUTPUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--rodada',default='')
    parser.add_argument('--original',default='docs/testes/fontes/2026-11-14-original.pdf')
    parser.add_argument('--original-title',default='Documento de teste')
    parser.add_argument('--original-pages',type=int,default=2)
    args=parser.parse_args()
    SOURCE=args.source
    OUTPUT=args.output
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont('Arial', 'C:/Windows/Fonts/arial.ttf'))
    pdfmetrics.registerFont(TTFont('Arial-Bold', 'C:/Windows/Fonts/arialbd.ttf'))
    pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial', boldItalic='Arial-Bold')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BodyReport', fontName='Arial', fontSize=12,
                             leading=18, spaceAfter=0, alignment=TA_JUSTIFY,
                             firstLineIndent=1.25*cm, allowWidows=0, allowOrphans=0))
    styles.add(ParagraphStyle(name='CenterReport', parent=styles['BodyReport'],
                             alignment=TA_CENTER, firstLineIndent=0))
    styles.add(ParagraphStyle(name='NatureReport', parent=styles['BodyReport'],
                             leftIndent=(A4[0]-5*cm)/2, leading=12, firstLineIndent=0))
    styles.add(ParagraphStyle(name='ReferencesReport', parent=styles['BodyReport'],
                             alignment=TA_LEFT, leading=12, firstLineIndent=0, spaceAfter=12))
    for name in ('Title', 'Heading2', 'Heading3'):
        styles[name].fontName = 'Arial-Bold'
        styles[name].fontSize = 12
        styles[name].leading = 18
        styles[name].textColor = colors.black
        styles[name].spaceAfter = 18
    styles['Heading2'].spaceBefore = 0
    styles['Heading3'].spaceBefore = 18
    styles['Heading3'].keepWithNext = True
    styles.add(ParagraphStyle(name='ReferencesTitle', parent=styles['Heading2'], alignment=TA_CENTER))

    def center(text):
        return Paragraph(escape(text), styles['CenterReport'])

    story = [center('UNISATC'), Spacer(1, 36)]
    story += [center(name.upper()) for name in AUTHORS]
    story += [Spacer(1, 5*cm), Paragraph('RELATÓRIO DE TESTES E PLANO DE CORREÇÃO', styles['Title']),
              center('Duas Marias Smart Production'+(' - '+args.rodada if args.rodada else '')), Spacer(1, 12*cm), center('Criciúma - SC'), center('2026'), PageBreak()]
    story += [center(name.upper()) for name in AUTHORS]
    story += [Spacer(1, 4.5*cm), Paragraph('RELATÓRIO DE TESTES E PLANO DE CORREÇÃO', styles['Title']),
              center('Duas Marias Smart Production'), Spacer(1, 2*cm),
              Paragraph('Relatório de testes locais do projeto Duas Marias Smart Production, elaborado para '
                        'registrar falhas observadas, correções realizadas e critérios de aceite das '
                        'funcionalidades em desenvolvimento.', styles['NatureReport']),
              Spacer(1, 10.5*cm), center('Criciúma - SC'), center('2026'), PageBreak(),
              Paragraph('SUMÁRIO', styles['Title']), Spacer(1, 18)]
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle('TOCReport', fontName='Arial', fontSize=12, leading=18,
                                     spaceBefore=9, rightIndent=24),
                       ParagraphStyle('TOCSubReport', fontName='Arial', fontSize=12, leading=18,
                                      spaceBefore=0, leftIndent=1.25*cm, rightIndent=24)]
    story += [toc, PageBreak()]
    section_number = 0
    occurrence = 0
    for line in SOURCE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('|'):
            cells = [x.strip() for x in line.strip('|').split('|')]
            if cells[0] in ('ID', '---'):
                continue
            title, diagnosis, acceptance = cells[1:4]
            occurrence += 1
            story.append(KeepTogether([
                Paragraph(inline(f'{section_number}.{occurrence} {cells[0]} {title}'), styles['Heading3']),
                Paragraph(inline(diagnosis), styles['BodyReport']),
                Paragraph(inline('Critério de aceite e reteste: ' + acceptance), styles['BodyReport']),
            ]))
        elif line.startswith('# '):
            continue
        elif line.startswith('## '):
            if section_number:
                story.append(PageBreak())
            section_number += 1
            story.append(Paragraph(inline(f'{section_number} {line[3:].upper()}'), styles['Heading2']))
        else:
            if section_number == 0:
                continue
            story.append(Paragraph(inline(line.removeprefix('- ')), styles['BodyReport']))

    # Fonte de orientação de apresentação; não se trata de uma monografia completa.
    story += [PageBreak(), Paragraph('REFERÊNCIAS', styles['ReferencesTitle']),
              Paragraph('UNIVERSIDADE DE BRASÍLIA. Biblioteca Central. <b>Normalização de trabalhos '
                        'acadêmicos: atualização em fevereiro de 2025</b>. Brasília, DF: UnB, 2025. '
                        'Disponível em: https://bce.unb.br/wp-content/uploads/2025/02/'
                        'ABNT-ATUALIZADO-em-fevereiro-2025.pdf. Acesso em: 14 nov. 2026.', styles['ReferencesReport']),
              Paragraph('<b>'+escape(args.original_title)+'</b>. [S. l.: s. n.], 2026. '+str(args.original_pages)+' p. Documento de trabalho '
                        'fornecido pelos responsáveis pelo projeto em 14 nov. 2026. '
                        'Cópia preservada em '+escape(args.original)+'.', styles['ReferencesReport']),
              Paragraph('<b>DUAS MARIAS SMART PRODUCTION</b>. Código-fonte do projeto. GitHub, 2026. '
                        'Versão de referência e785017, acrescida de correções locais. Disponível em: '
                        'https://github.com/02kamk/duas-marias-smart-production. '
                        'Acesso em: 14 nov. 2026.', styles['ReferencesReport'])]

    # Referências em ordem alfabética, preservando o título centralizado.
    ref_index=next(i for i,item in enumerate(story) if isinstance(item,Paragraph) and item.style.name=='ReferencesTitle')
    story[ref_index+1:]=sorted(story[ref_index+1:],key=lambda item:item.getPlainText().casefold())

    def footer(canvas, doc):
        canvas.saveState()
        if doc.page >= 4:
            canvas.setFont('Arial', 10)
            canvas.drawRightString(A4[0]-2*cm, A4[1]-2*cm, str(doc.page-1))
        canvas.restoreState()

    doc = AcademicReport(str(OUTPUT), pagesize=A4, rightMargin=2*cm, leftMargin=3*cm,
                      topMargin=3*cm, bottomMargin=2*cm,
                      title='Relatório de testes - Duas Marias - 14/11/2026',
                      author='; '.join(AUTHORS))
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id='ABNT', frames=frame, onPage=footer))
    doc.multiBuild(story)
    print(OUTPUT)


if __name__ == '__main__':
    main()
