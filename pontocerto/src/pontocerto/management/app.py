"""Fábrica estendida: reutiliza a aplicação antiga sem editar seus arquivos."""
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .api import create_router
from .experiment import DelayModel
from .store import Store

ROOT=Path(__file__).resolve().parents[3]
STATIC=Path(__file__).resolve().parent/'static'


def extend(app: FastAPI, root=ROOT):
    store=Store(root/'artifacts'/'gestao_demo'/'state.json')
    model=DelayModel(root/'artifacts'/'gestao_ml')
    app.include_router(create_router(store,model))
    app.mount('/gestao-assets',StaticFiles(directory=str(STATIC),check_dir=False),name='gestao-assets')

    @app.get('/gestao',include_in_schema=False)
    @app.get('/gestao/',include_in_schema=False)
    def management_page():
        index=STATIC/'gestao.html'
        if not index.exists():
            return HTMLResponse('<h1>Gestão ainda não compilada</h1><p>Consulte docs/GESTAO_ADITIVA.md para gerar a interface.</p>',status_code=503)
        return HTMLResponse(index.read_text(encoding='utf-8'))

    @app.middleware('http')
    async def additive_access(request: Request,call_next):
        # Escritas apenas no navegador local; não cria segurança operacional/autenticação.
        if request.url.path.startswith('/api/gestao') and request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin')
            if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Origem de gravação não permitida.'},status_code=403)
            if not request.headers.get('content-type','').startswith('application/json'):
                return JSONResponse({'detail':'Envie JSON.'},status_code=415)
        response=await call_next(request)
        if request.url.path=='/' and response.status_code==200 and 'text/html' in response.headers.get('content-type',''):
            body=b''.join([chunk async for chunk in response.body_iterator]).decode('utf-8')
            # Acrescenta só um acesso; todos os controles de câmera continuam no HTML original.
            link='<a href="/gestao" style="position:fixed;right:20px;top:12px;z-index:9999;background:#81334f;color:white;padding:10px 14px;border-radius:8px;font:600 13px system-ui;text-decoration:none">Gestão de produção e atrasos →</a>'
            return HTMLResponse(body.replace('</body>',link+'</body>'),background=response.background)
        return response
    return app


def create_app():
    from pontocerto.app.server import criar_app
    return extend(criar_app())
