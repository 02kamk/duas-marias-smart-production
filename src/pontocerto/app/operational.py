"""Entrada operacional com autenticação local e aplicação web instalável."""
from pathlib import Path
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from .auth import secure

ROOT=Path(__file__).resolve().parents[3]
STATIC=Path(__file__).parent/'static'


def extend(app,root=ROOT,supabase=None,admins=None):
    from .relatorios import registrar as registrar_relatorios
    registrar_relatorios(app)

    @app.get('/manifest.webmanifest',include_in_schema=False)
    def manifest():
        return JSONResponse({'name':'Ponto Certo','short_name':'Ponto Certo',
            'id':'/','start_url':'/','scope':'/','display':'standalone','lang':'pt-BR',
            'background_color':'#ffffff','theme_color':'#C1502E',
            'icons':[{'src':f'/static/icon-{size}.png','sizes':f'{size}x{size}','type':'image/png','purpose':'any'} for size in (192,512)]},
            media_type='application/manifest+json')

    @app.get('/sw.js',include_in_schema=False)
    def service_worker():
        return FileResponse(STATIC/'js'/'sw.js',media_type='application/javascript',headers={'Service-Worker-Allowed':'/','Cache-Control':'no-cache'})

    @app.get('/offline',include_in_schema=False)
    def offline():
        return HTMLResponse('<!doctype html><html lang="pt-BR"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sem conexão</title><h1>Conecte-se ao servidor Ponto Certo</h1><p>Inspeções, fotos e dados de sessão não são armazenados no cache do navegador. A câmera e o modelo dependem do servidor.</p><a href="/">Tentar novamente</a></html>')

    return secure(app,root,supabase,admins=admins)
