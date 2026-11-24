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
    from pontocerto.config import variavel_env
    if variavel_env('GESTAO_STORAGE') == 'supabase':
        from .postgres import PostgresStore
        store=PostgresStore()
    else:
        store=Store(root/'artifacts'/'gestao_demo'/'state.json')
    model=DelayModel(root/'artifacts'/'gestao_ml')
    from .receiving import router as receiving_router
    app.include_router(receiving_router(store))
    from .documents import router as documents_router
    app.include_router(documents_router(store))
    app.include_router(create_router(store,model))
    @app.get('/api/gestao/inspecao')
    def lotes_para_inspecao(request: Request):
        """OPs em aberto com os números da inspeção, para escolher o lote em produção."""
        estado=getattr(request.app.state,'estado',None)
        resumo=estado.resumo_por_lote() if estado is not None else {}
        ativo=estado.lote_ativo if estado is not None else None
        lotes=[{**{k:o.get(k) for k in ('id','code','client','model','fabric','quantity','produced','dueDate','status')},
                'inspecao':resumo.get(o['code'],{'inspecionadas':0,'defeitos':0,'pendentes':0})}
               for o in store.read()['orders'] if o.get('status')!='Concluído']
        return {'lotes':lotes,'ativo':ativo}

    @app.post('/api/gestao/orders/{order_id}/inspecionar')
    def inspecionar_lote(order_id: str, request: Request):
        order=next((o for o in store.read()['orders'] if o['id']==order_id),None)
        if order is None:
            return JSONResponse({'detail':'Lote não encontrado.'},status_code=404)
        if order.get('status')=='Concluído':
            return JSONResponse({'detail':'Lote concluído não recebe novas inspeções.'},status_code=409)
        ativar=getattr(request.app.state,'ativar_lote',None)
        if ativar is None:
            return JSONResponse({'detail':'Inspeção indisponível neste servidor.'},status_code=503)
        lote=ativar({'ordem_id':order['id'],'codigo':order['code'],'cliente':order['client'],
                     'modelo_peca':order['model'],'tecido':order.get('fabric') or None,
                     'quantidade':order['quantity'],'prazo_entrega':order['dueDate']})
        return {'lote':lote}

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
            # A leitura da OP recebe a foto como formulário; o resto só aceita JSON.
            tipo=request.headers.get('content-type','')
            foto_op=request.url.path=='/api/gestao/op/read' and tipo.startswith('multipart/form-data')
            if not foto_op and not tipo.startswith('application/json'):
                return JSONResponse({'detail':'Envie JSON.'},status_code=415)
        return await call_next(request)
    return app

