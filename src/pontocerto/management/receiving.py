"""Conferência de recebimento e avisos revisados pelo operador."""
from datetime import date
from uuid import uuid4
from urllib.parse import quote
import re
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator
from pontocerto.config import variavel_env
from .domain import now


class Count(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name: str=Field(min_length=1,max_length=60)
    expected: int=Field(strict=True,ge=0,le=1000000)
    received: int=Field(strict=True,ge=0,le=1000000)


class Receipt(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    day: date
    grade: list[Count]=Field(min_length=1,max_length=100)
    supplies: list[Count]=Field(default_factory=list,max_length=100)
    note: str=Field(default='',max_length=1000)

    @model_validator(mode='after')
    def valid(self):
        if self.day>date.today():
            raise ValueError('Recebimento não pode ter data futura.')
        for items in (self.grade,self.supplies):
            names=[i.name.casefold() for i in items]
            if len(names)!=len(set(names)):
                raise ValueError('Itens repetidos na mesma conferência.')
        return self


class Intake(Receipt):
    """Receber uma OP nova: cadastro do lote e conferência num formulário só."""
    code: str=Field(min_length=1,max_length=40)
    client: str=Field(min_length=1,max_length=100)
    model: str=Field(min_length=1,max_length=100)
    fabric: str=Field(default='',max_length=60)
    dueDate: date

    @model_validator(mode='after')
    def quantity(self):
        if not sum(i.expected for i in self.grade):
            raise ValueError('Informe a quantidade esperada de pelo menos um tamanho.')
        return self


def ritmo_padrao(state,quantidade,prazo):
    """Ritmo inicial do lote: média dos lotes em andamento ou o necessário para o prazo."""
    ativos=[o['recentRate'] for o in state['orders'] if o.get('status')!='Concluído' and o.get('recentRate')]
    if ativos:
        return round(sum(ativos)/len(ativos),1)
    dias=max(1,(prazo-date.today()).days)
    return float(max(1,-(-quantidade//dias)))


class SendInput(BaseModel):
    recipient: str=Field(min_length=5,max_length=254)
    confirm: bool=False


def outlook_config():
    keys=('OUTLOOK_TENANT_ID','OUTLOOK_CLIENT_ID','OUTLOOK_CLIENT_SECRET','OUTLOOK_SENDER')
    return {k:variavel_env(k) for k in keys}


def send_outlook(recipient,subject,text):
    cfg=outlook_config()
    if not all(cfg.values()):
        raise HTTPException(503,'Outlook não configurado. Confira o guia de configuração Microsoft 365.')
    try:
        with httpx.Client(timeout=25) as client:
            token=client.post('https://login.microsoftonline.com/'+quote(cfg['OUTLOOK_TENANT_ID'],safe='')+'/oauth2/v2.0/token',
                data={'client_id':cfg['OUTLOOK_CLIENT_ID'],'client_secret':cfg['OUTLOOK_CLIENT_SECRET'],
                      'scope':'https://graph.microsoft.com/.default','grant_type':'client_credentials'})
            token.raise_for_status()
            response=client.post('https://graph.microsoft.com/v1.0/users/'+quote(cfg['OUTLOOK_SENDER'],safe='')+'/sendMail',
                headers={'Authorization':'Bearer '+token.json()['access_token']},
                json={'message':{'subject':subject,'body':{'contentType':'Text','content':text},
                                 'toRecipients':[{'emailAddress':{'address':recipient}}]},'saveToSentItems':True})
            response.raise_for_status()
    except (httpx.HTTPError,KeyError):
        raise HTTPException(502,'O Microsoft 365 recusou ou não respondeu ao envio. Verifique permissões e a caixa de enviados antes de repetir.')


def router(store):
    api=APIRouter(prefix='/api/gestao')

    @api.get('/integrations')
    def integrations():
        return {'outlookConfigured':all(outlook_config().values()),'storage':getattr(store,'backend','local'),
                'notice':'O aviso só é enviado após revisão e confirmação do operador.'}

    def conferir(state,order,body):
            item={**Receipt(**body.model_dump(include={'day','grade','supplies','note'})).model_dump(mode='json'),
                  'id':str(uuid4()),'orderId':order['id'],'createdAt':now()}
            differences=[{'group':group,'name':i.name,'difference':i.received-i.expected}
                         for group,rows in [('grade',body.grade),('aviamentos',body.supplies)]
                         for i in rows if i.received!=i.expected]
            item['differences']=differences
            item['status']='divergente' if differences else 'conferido'
            item['mailStatus']='pendente' if differences else 'não necessário'
            item['subject']=f'Conferência de recebimento - {order["code"]}'
            lines=[f'Lote: {order["code"]}',f'Data: {body.day.isoformat()}']
            lines += [f'{d["group"]} / {d["name"]}: '+('faltam ' if d['difference']<0 else 'sobram ')+str(abs(d['difference'])) for d in differences]
            item['message']='\n'.join(lines+([body.note] if body.note else []))
            state.setdefault('receipts',[]).append(item)
            return item

    @api.post('/intake',status_code=201)
    def intake(body:Intake):
        if body.dueDate<date.today():
            raise HTTPException(422,'O prazo de entrega não pode estar no passado.')
        def change(state):
            if any(o['code'].casefold()==body.code.casefold() for o in state['orders']):
                raise ValueError('Já existe um lote com este código.')
            quantidade=sum(i.expected for i in body.grade)
            ritmo=ritmo_padrao(state,quantidade,body.dueDate)
            order={'id':str(uuid4()),'code':body.code,'client':body.client,'model':body.model,'fabric':body.fabric,
                   'quantity':quantidade,'produced':0,'dueDate':body.dueDate.isoformat(),
                   'capacityPerDay':ritmo,'recentRate':ritmo,'reworkRate':.05,'status':'Planejado'}
            state['orders'].append(order)
            return {'order':order,'receipt':conferir(state,order,body)}
        try:
            return store.update('intake','Recebimento de OP com conferência',change)
        except ValueError as exc:
            raise HTTPException(422,str(exc))

    @api.post('/orders/{order_id}/receipts',status_code=201)
    def receive(order_id:str,body:Receipt):
        def change(state):
            order=next((o for o in state['orders'] if o['id']==order_id),None)
            if not order:
                raise ValueError('Lote não encontrado.')
            if sum(i.expected for i in body.grade)!=order['quantity']:
                raise ValueError('A soma da grade deve ser igual à quantidade do lote.')
            return conferir(state,order,body)
        try:
            return store.update('receipt','Conferência de grade e aviamentos',change)
        except ValueError as exc:
            raise HTTPException(422,str(exc))

    @api.post('/receipts/{receipt_id}/notify')
    def notify(receipt_id:str,body:SendInput):
        if not body.confirm or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',body.recipient):
            raise HTTPException(422,'Confira o destinatário e confirme explicitamente o envio.')
        # Segura o lock durante o envio para impedir duplo clique concorrente.
        with store.lock:
            item=next((r for r in store.read().get('receipts',[]) if r['id']==receipt_id),None)
            if not item:
                raise HTTPException(404,'Conferência não encontrada.')
            if not item['differences'] or item.get('mailStatus') in ('enviado','em envio'):
                raise HTTPException(409,'Não há aviso pendente para envio.')
            def mark(state,status):
                r=next(r for r in state['receipts'] if r['id']==receipt_id)
                r.update(mailStatus=status,recipient=body.recipient,mailUpdatedAt=now())
                return r
            store.update('receipt_mail','Envio confirmado pelo operador',lambda s:mark(s,'em envio'))
            try:
                send_outlook(body.recipient,item['subject'],item['message'])
            except HTTPException:
                store.update('receipt_mail','Conferir caixa de enviados antes de tentar novamente',lambda s:mark(s,'verificar envio'))
                raise
            return store.update('receipt_mail','Aceito pelo Microsoft 365',lambda s:mark(s,'enviado'))
    return api
