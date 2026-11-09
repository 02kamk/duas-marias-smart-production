"""Nova fábrica aditiva; os comandos e arquivos anteriores não são alterados."""
from pathlib import Path
from fastapi import Request
from fastapi.responses import HTMLResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from .api import create_router

ROOT=Path(__file__).resolve().parents[3]
STATIC=Path(__file__).resolve().parent/'static'


def extend_business(app,root=ROOT):
    app.include_router(create_router(root))
    app.mount('/business-assets',StaticFiles(directory=str(STATIC),check_dir=False),name='business-assets')
    @app.get('/financeiro',include_in_schema=False)
    @app.get('/produtividade',include_in_schema=False)
    def page():
        index=STATIC/'business.html'
        if not index.exists():
            return HTMLResponse('<h1>Compile a extensão com vite.business.config.ts</h1>',status_code=503)
        return HTMLResponse(index.read_text(encoding='utf-8'))

    @app.middleware('http')
    async def access(request:Request,call_next):
        if request.url.path.startswith('/api/business') and request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin')
            if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Origem não permitida.'},status_code=403)
            if not request.headers.get('content-type','').startswith('application/json'):
                return JSONResponse({'detail':'Envie JSON.'},status_code=415)
            try:
                too_large=int(request.headers.get('content-length','0'))>600000
            except ValueError:
                too_large=True
            if too_large:
                return JSONResponse({'detail':'Conteúdo acima de 600 KB.'},status_code=413)
        response=await call_next(request)
        if request.url.path in ('/','/gestao','/gestao/') and response.status_code==200:
            body=b''.join([part async for part in response.body_iterator]).decode('utf-8')
            link='<a href="/financeiro" style="position:fixed;right:20px;bottom:82px;z-index:9999;background:#225747;color:white;border-radius:8px;padding:10px 14px;font:600 13px system-ui;text-decoration:none">Financeiro e produtividade pública →</a>'
            return HTMLResponse(body.replace('</body>',link+'</body>'),background=response.background)
        return response
    return app


def create_app():
    from pontocerto.management.app import create_app as management
    return extend_business(management())
