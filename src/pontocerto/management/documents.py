"""OCR local de OPs e relatório de gestão; nenhuma imagem é enviada para fora."""
import io
import re
from collections import Counter
from threading import Lock
from xml.sax.saxutils import escape
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from PIL import Image
from starlette.concurrency import run_in_threadpool
from pontocerto.config import variavel_env

_engine=None
_lock=Lock()
SIZES=('PP','P','M','G','GG','XG','XGG')


def recognize(data):
    from rapidocr_onnxruntime import RapidOCR
    global _engine
    with _lock:
        if _engine is None:
            _engine=RapidOCR()
        return _engine(data)


def suggestions(text):
    """Extrai apenas campos explicitamente rotulados; todo resultado é um rascunho."""
    fields={}
    for key,pattern in {
        'code':r'(?:\bOP|ORDEM\s+(?:DE\s+)?PRODU[ÇC][ÃA]O)\s*[:#\-]?\s*(\d[\d.\-/]{2,30})',
        'client':r'CLIENTE\s*[:\-]\s*([^\n]{2,100})',
        'model':r'(?:MODELO|PRODUTO)\s*[:\-]\s*([^\n]{2,100})',
        'quantity':r'(?:QUANTIDADE|QTD\.?|TOTAL\s+DE\s+PE[ÇC]AS)\s*[:\-]?\s*(\d{1,7})\b',
    }.items():
        match=re.search(pattern,text,re.I)
        if match:
            fields[key]=int(match[1]) if key=='quantity' else match[1].strip()
    grade=[]
    for size in SIZES:
        match=re.search(r'(?<!\w)'+size+r'\s*[:=]\s*(\d{1,6})\b',text,re.I)
        if match:
            grade.append({'name':size,'expected':int(match[1]),'received':0})
    return fields,grade


def pdf_report(title,paragraphs,columns,rows):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    stream=io.BytesIO();styles=getSampleStyleSheet()
    story=[Paragraph(escape(title),styles['Title'])]
    story += [Paragraph(escape(str(p)),styles['BodyText']) for p in paragraphs]
    story.append(Spacer(1,18))
    content=[[Paragraph(escape(str(v)),styles['BodyText']) for v in columns]]
    content += [[Paragraph(escape(str(v)),styles['BodyText']) for v in row] for row in rows]
    table=Table(content,colWidths=[(A4[0]-80)/len(columns)]*len(columns),repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#efe3e8')),
        ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#d8cdd2')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    story.append(table)
    SimpleDocTemplate(stream,pagesize=A4,leftMargin=40,rightMargin=40,topMargin=45,bottomMargin=45).build(story)
    return stream.getvalue()


def router(store):
    api=APIRouter(prefix='/api/gestao')

    @api.post('/op/read')
    async def read_op(arquivo:UploadFile=File(...)):
        data=await arquivo.read(10*1024*1024+1)
        await arquivo.close()
        if not data or len(data)>10*1024*1024:
            raise HTTPException(422,'Envie uma foto de até 10 MB.')
        try:
            image=Image.open(io.BytesIO(data))
            if image.width*image.height>20_000_000:
                raise ValueError()
            image.verify()
        except Exception:
            raise HTTPException(422,'Imagem inválida ou acima de 20 megapixels. Use JPG ou PNG legível.')
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            raise HTTPException(503,'OCR local não instalado. Instale requirements-ocr.txt ou preencha a grade manualmente.')
        try:
            result,_elapsed=await run_in_threadpool(recognize,data)
        except Exception:
            raise HTTPException(422,'Não foi possível ler a OP. Fotografe de frente, com iluminação e resolução maiores.')
        lines=result or []
        text='\n'.join(str(row[1]) for row in lines)
        fields,grade=suggestions(text)
        return {'text':text,'suggestions':fields,'grade':grade,'requiresReview':True,
                'averageConfidence':sum(float(r[2]) for r in lines)/len(lines) if lines else None,
                'notice':'Rascunho de leitura local. Confira cada campo e a grade com a OP. A foto não conta as peças físicas; manuscritos e tabelas podem ser lidos incorretamente.'}

    @api.get('/report.pdf')
    def report():
        state=store.read();orders=state['orders'];receipts=state.get('receipts',[])
        data=pdf_report('Duas Marias - acompanhamento da produção',
            [f'Lotes: {len(orders)} | Colaboradores: {len(state["employees"])} | Recebimentos: {len(receipts)}',
             f'Conferências com divergência: {sum(r["status"]=="divergente" for r in receipts)}',
             'Base de testes. Recebimento e peças finalizadas são contagens diferentes.'],
            ['Lote','Peça','Produção / total','Prazo','Situação'],
            [[o['code'],o['model'],f'{o["produced"]} / {o["quantity"]}',o['dueDate'],o['status']] for o in orders])
        return Response(data,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="relatorio-producao.pdf"'})

    @api.get('/configuration')
    def configuration():
        needed=['SUPABASE_DB_URL','SUPABASE_URL','SUPABASE_SECRET_KEY','SUPABASE_BUCKET']
        missing=[key for key in needed if not variavel_env(key) or 'troque' in variavel_env(key) or 'SEU-' in variavel_env(key)]
        return {'storage':getattr(store,'backend','local'),'supabaseMissing':missing,
                'steps':['Executar supabase/schema.sql e supabase/gestao.sql no projeto de testes.',
                         'Criar bucket privado Capturas.',
                         'Preencher as variáveis no .env local e reiniciar.',
                         'Usar GESTAO_STORAGE=supabase para a gestão remota; local mantém os testes neste computador.'],
                'notice':'Nenhuma chave ou senha é exibida nesta tela.'}
    return api
