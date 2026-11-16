"""Entrada operacional com autenticação local e aplicação web instalável."""
from pathlib import Path
from datetime import date
from collections import Counter
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from .auth import secure

ROOT=Path(__file__).resolve().parents[3]
STATIC=Path(__file__).parent/'static'


def extend(app,root=ROOT):
    def inspection_rows(day):
        return app.state.estado.eventos(limite=500,dia=day.isoformat() if day else None)

    @app.get('/api/relatorios/resumo')
    def report_summary(dia:date|None=None):
        events=inspection_rows(dia)
        return {'total':len(events),'defeitos':sum(e['e_falha'] for e in events),
                'revisadas':sum(bool(e['revisao_humana']) for e in events),
                'pendentes':sum(bool(e.get('precisa_revisao')) for e in events),
                'classes':dict(Counter(e['nome_final'] for e in events)),
                'scope':'Até 500 inspeções mais recentes no período selecionado.'}

    @app.get('/api/relatorios/pdf')
    def inspection_pdf(dia:date|None=None):
        from pontocerto.management.documents import pdf_report
        from fastapi.responses import Response
        events=inspection_rows(dia)
        summary=report_summary(dia)
        data=pdf_report('Duas Marias - relatório de inspeções',
            [f'Período: {dia.isoformat() if dia else "todos os dias"}',
             f'Inspeções: {summary["total"]} | Defeitos: {summary["defeitos"]} | Conferidas: {summary["revisadas"]}',
             summary['scope'],'As sugestões do modelo permanecem distintas das classes conferidas.'],
            ['Data / hora','Sugestão original','Classe atual','Conferência'],
            [[e['data']+' '+e['hora'],e['nome'],e['nome_final'],
              'Conferida' if e['revisao_humana'] else ('Aguardando' if e.get('precisa_revisao') else 'Automática')] for e in events])
        return Response(data,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="relatorio-inspecoes.pdf"'})

    @app.get('/manifest.webmanifest',include_in_schema=False)
    def manifest():
        return JSONResponse({'name':'Duas Marias Smart Production','short_name':'Duas Marias',
            'id':'/','start_url':'/','scope':'/','display':'standalone','lang':'pt-BR',
            'background_color':'#ffffff','theme_color':'#C1502E',
            'icons':[{'src':f'/static/icon-{size}.png','sizes':f'{size}x{size}','type':'image/png','purpose':'any'} for size in (192,512)]},
            media_type='application/manifest+json')

    @app.get('/sw.js',include_in_schema=False)
    def service_worker():
        return FileResponse(STATIC/'js'/'sw.js',media_type='application/javascript',headers={'Service-Worker-Allowed':'/','Cache-Control':'no-cache'})

    @app.get('/offline',include_in_schema=False)
    def offline():
        return HTMLResponse('<!doctype html><html lang="pt-BR"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sem conexão</title><h1>Conecte-se ao servidor Duas Marias</h1><p>Inspeções, fotos e dados de sessão não são armazenados no cache do navegador. A câmera e o modelo dependem do servidor.</p><a href="/">Tentar novamente</a></html>')

    return secure(app,root)
