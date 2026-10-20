import json
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter,HTTPException,Response
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .ledger import LedgerStore,add_entry,cents,csv_rows,now
from .finance import report
from .productivity import PublicProductivity

Environment=Literal['demo','real']


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True,allow_inf_nan=False)


class EntryInput(Input):
    reference:str=Field(min_length=1,max_length=80)
    type:Literal['income','expense']
    nature:Literal['operating','equipment','financing']='operating'
    category:str=Field(min_length=1,max_length=80)
    description:str=Field(min_length=1,max_length=200)
    amount:str=Field(min_length=1,max_length=30)
    documentDate:date
    dueDate:date
    settledDate:date|None=None

    @model_validator(mode='after')
    def valid(self):
        cents(self.amount)
        if self.dueDate<self.documentDate:
            raise ValueError('Vencimento anterior ao documento.')
        if self.settledDate and (self.settledDate<self.documentDate or self.settledDate>date.today()):
            raise ValueError('Liquidação anterior ao documento ou futura.')
        return self

    def entry(self):
        data=self.model_dump(mode='json',exclude={'amount'})
        return {**data,'amountCents':cents(self.amount),'status':'settled' if self.settledDate else 'open'}


class PolicyInput(Input):
    openingDate:date
    openingBalanceCents:int=Field(strict=True,ge=-100000000000,le=100000000000)
    historyStartMonth:str|None=None
    historyThroughMonth:str|None=None
    reserveMonths:int=Field(strict=True,ge=0,le=12)
    equipmentPercent:int=Field(strict=True,ge=0,le=100)
    contingencyPercent:int=Field(strict=True,ge=0,le=100)
    scenarioPercent:int=Field(strict=True,ge=0,le=50)
    reason:str=Field(min_length=3,max_length=300)

    @model_validator(mode='after')
    def valid(self):
        if self.equipmentPercent+self.contingencyPercent>100:
            raise ValueError('Percentuais de equipamento e contingência não podem somar mais de 100%.')
        if self.openingDate>date.today():
            raise ValueError('Saldo inicial não pode ter data futura.')
        if bool(self.historyStartMonth)!=bool(self.historyThroughMonth):
            raise ValueError('Preencha início e fim do histórico juntos.')
        if self.historyStartMonth:
            import re
            for m in [self.historyStartMonth,self.historyThroughMonth]:
                if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',m or ''):
                    raise ValueError('Mês deve estar em AAAA-MM.')
                date.fromisoformat(m+'-01')
            if self.historyStartMonth>self.historyThroughMonth or self.historyThroughMonth>=date.today().isoformat()[:7]:
                raise ValueError('Histórico deve ser consecutivo e terminar em mês já encerrado.')
            if self.historyStartMonth+'-01'<self.openingDate.isoformat():
                raise ValueError('Saldo inicial deve anteceder ou coincidir com o início dos meses confirmados.')
            a,b=self.historyStartMonth,self.historyThroughMonth
            if (int(b[:4])-int(a[:4]))*12+int(b[5:])-int(a[5:])>239:
                raise ValueError('Máximo de 240 meses.')
        return self


class Settlement(Input):
    settledDate:date
    reason:str=Field(min_length=3,max_length=300)


class Reason(Input):
    reason:str=Field(min_length=3,max_length=300)


class ImportInput(Input):
    csv:str=Field(min_length=1,max_length=500000)


class ProductivityInput(Input):
    date:date
    department:Literal['sweing','finishing']
    team:int=Field(strict=True,ge=1,le=12)
    no_of_workers:float=Field(gt=0,le=100)
    no_of_style_change:int=Field(strict=True,ge=0,le=10)
    targeted_productivity:float=Field(gt=0,le=1)
    smv:float=Field(gt=0,le=100)


def create_router(root:Path):
    router=APIRouter(prefix='/api/business',tags=['Financeiro local e produtividade pública'])
    stores={env:LedgerStore(root/'artifacts'/'finance_local'/f'{env}.json',env) for env in ['demo','real']}
    public=PublicProductivity(root/'artifacts'/'productivity_public')

    def mutate(env,action,reason,fn):
        try:
            return stores[env].update(action,reason,fn)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        except OSError as exc:
            raise HTTPException(503,'Falha na gravação local; alteração não aplicada.') from exc

    @router.get('/finance/{environment}/state')
    def state(environment:Environment):
        return stores[environment].read()

    @router.get('/finance/{environment}/report')
    def summary(environment:Environment,horizon:int=3):
        if not 1<=horizon<=6:
            raise HTTPException(422,'Use de 1 a 6 meses.')
        return report(stores[environment].read(),horizon=horizon)

    @router.post('/finance/{environment}/entries',status_code=201)
    def entry(environment:Environment,body:EntryInput):
        return mutate(environment,'create_entry','Cadastro local de documento',lambda state:add_entry(state,body.entry(),environment))

    @router.post('/finance/{environment}/import',status_code=201)
    def import_csv(environment:Environment,body:ImportInput):
        try:
            inputs=[]
            for i,row in enumerate(csv_rows(body.csv),start=2):
                try:
                    row['settledDate']=row['settledDate'] or None
                    inputs.append(EntryInput.model_validate(row).entry())
                except ValueError as exc:
                    raise ValueError(f'Linha {i}: campos inválidos; confira o modelo e datas.') from exc
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        def change(state):
            for item in inputs:
                add_entry(state,item,environment)
            return {'imported':len(inputs),'environment':environment}
        return mutate(environment,'import_csv',f'Importação transacional de {len(inputs)} documentos',change)

    @router.get('/finance/template.csv')
    def template():
        text='reference;type;nature;category;description;amount;documentDate;dueDate;settledDate\n'
        return Response(text,media_type='text/csv',headers={'Content-Disposition':'attachment; filename=financeiro-modelo.csv'})

    @router.post('/finance/{environment}/entries/{entry_id}/settle')
    def settle(environment:Environment,entry_id:str,body:Settlement):
        if body.settledDate>date.today():
            raise HTTPException(422,'Não é permitido liquidar no futuro.')
        def change(state):
            item=find_entry(state,entry_id)
            if item['status']!='open' or body.settledDate.isoformat()<item['documentDate']:
                raise ValueError('Documento não está aberto ou data anterior à emissão.')
            item.update(status='settled',settledDate=body.settledDate.isoformat())
            return item
        return mutate(environment,'settle_entry',body.reason,change)

    @router.post('/finance/{environment}/entries/{entry_id}/cancel')
    def cancel(environment:Environment,entry_id:str,body:Reason):
        def change(state):
            item=find_entry(state,entry_id)
            if item['status']!='open':
                raise ValueError('Somente documento em aberto pode ser cancelado; liquidação exige conciliação/estorno específico.')
            # Mantém registro original e motivo; nenhuma exclusão destrutiva.
            item['status']='cancelled'
            item['cancelReason']=body.reason
            return item
        return mutate(environment,'cancel_entry',body.reason,change)

    @router.patch('/finance/{environment}/settings')
    def settings(environment:Environment,body:PolicyInput):
        def change(state):
            if any(e['documentDate']<body.openingDate.isoformat() for e in state['entries']):
                raise ValueError('Não mova o saldo inicial para depois de documentos existentes.')
            before=state['settings'].copy()
            state['settings']=body.model_dump(mode='json',exclude={'reason'})
            state['audit'].append({'id':str(uuid4()),'at':now(),'action':'policy_diff','before':before,'after':state['settings'].copy()})
            return state['settings']
        return mutate(environment,'settings',body.reason,change)

    @router.get('/productivity/model')
    def productivity_status():
        return public.status()

    @router.post('/productivity/predict')
    def productivity_predict(body:ProductivityInput):
        try:
            return public.predict(body.model_dump(mode='json'))
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503,'Inferência pública indisponível; confira o ambiente e retreine.') from exc

    return router


def find_entry(state,entry_id):
    item=next((e for e in state['entries'] if e['id']==entry_id),None)
    if item is None:
        raise HTTPException(404,'Documento não encontrado neste ambiente.')
    return item
