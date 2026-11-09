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
NAV_MARCA='<!--nav-extensoes-->'
NAV_GESTAO=('<a class="nav-item" href="/gestao" title="Gestao de producao e atrasos">'
           '<span class="nav-icone" aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" focusable="false"><path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/></svg></span>'
           '<span class="nav-texto">Gestao</span></a>')


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
            if NAV_MARCA in body:
                # Item no menu lateral da inspecao (nao cobre a barra superior).
                body=body.replace(NAV_MARCA,NAV_GESTAO+NAV_MARCA)
            else:
                link='<a href="/gestao" style="position:fixed;right:20px;top:12px;z-index:9999;background:#81334f;color:white;padding:10px 14px;border-radius:8px;font:600 13px system-ui;text-decoration:none">Gestão de produção e atrasos →</a>'
                body=body.replace('</body>',link+'</body>')
            return HTMLResponse(body,background=response.background)
        return response
    return app


def create_app():
    from pontocerto.app.server import criar_app
    return extend(criar_app())
