from datetime import date, timedelta
import math
from pathlib import Path
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict, model_validator
from .domain import now, snapshot, feature_row, apply_record, recommendations
from .experiment import DelayModel, NOTICE, VERSION
from .store import Store, OPERATIONS


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class OrderInput(Input):
    code: str = Field(min_length=1,max_length=40)
    client: str = Field(min_length=1,max_length=100)
    model: str = Field(min_length=1,max_length=100)
    quantity: int = Field(strict=True,ge=1,le=1000000)
    dueDate: date
    capacityPerDay: float = Field(gt=0,le=10000)
    recentRate: float = Field(ge=0,le=11000)
    reworkRate: float = Field(ge=0,le=.3)


class PlanInput(Input):
    dueDate: date
    capacityPerDay: float = Field(gt=0,le=10000)
    recentRate: float = Field(ge=0,le=11000)
    reworkRate: float = Field(ge=0,le=.3)
    reason: str = Field(min_length=3,max_length=300)


class RecordInput(Input):
    orderId: str
    employeeId: str
    operation: str
    goodQuantity: int = Field(strict=True,ge=0,le=1000000)
    reworkQuantity: int = Field(strict=True,ge=0,le=1000000)
    day: date


class AssignmentInput(Input):
    orderId: str
    employeeId: str
    operation: str
    minutes: int = Field(strict=True,gt=0,le=480)
    period: date
    decision: Literal['accepted','rejected']
    reason: str = Field(min_length=3,max_length=300)


class EmployeeInput(Input):
    name: str = Field(min_length=2, max_length=100)
    availableMinutes: int = Field(strict=True, ge=1, le=480)
    operations: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def valid_operations(self):
        if len(set(self.operations)) != len(self.operations) or any(op not in OPERATIONS for op in self.operations):
            raise ValueError('Selecione operações válidas, sem repetições.')
        return self


class ReallocationInput(Input):
    employeeId: str
    period: date
    minutes: int = Field(strict=True,gt=0,le=480)
    reason: str = Field(min_length=3,max_length=300)


def create_router(store: Store, model: DelayModel):
    router = APIRouter(prefix='/api/gestao', tags=['Gestão demonstrativa'])

    @router.get('/state')
    def state():
        return {**store.read(), 'operations': OPERATIONS, 'referenceDate': date.today().isoformat(),
                'notice': 'Ambiente de testes. Confira a origem dos dados antes de tomar decisões operacionais.',
                'storage':getattr(store,'backend','local')}

    @router.get('/model')
    def model_status():
        return model.status()

    @router.post('/employees', status_code=201)
    def create_employee(body: EmployeeInput):
        def change(state):
            if any(e['name'].casefold() == body.name.casefold() for e in state['employees']):
                raise ValueError('Nome de colaborador já cadastrado nesta demonstração.')
            employee = {'id': str(uuid4()), 'name': body.name, 'active': True,
                        'availableMinutes': body.availableMinutes,
                        'skills': {op: {'rate': None, 'quality': None, 'experience': None}
                                   for op in body.operations}}
            state['employees'].append(employee)
            return employee
        return mutate('create_employee', 'Cadastro local sem histórico de produtividade', change)

    @router.post('/orders',status_code=201)
    def create_order(body: OrderInput):
        def change(state):
            if any(o['code'].casefold()==body.code.casefold() for o in state['orders']):
                raise ValueError('Código de lote já existe.')
            order={**body.model_dump(mode='json'),'id':str(uuid4()),'produced':0,'status':'Planejado','dataOrigin':'mock'}
            state['orders'].append(order)
            return order
        return mutate('create_order','Cadastro demonstrativo',change)

    @router.patch('/orders/{order_id}/plan')
    def change_plan(order_id: str, body: PlanInput):
        def change(state):
            order=find(state,order_id)
            before={k:order[k] for k in ['dueDate','capacityPerDay','recentRate','reworkRate']}
            order.update(body.model_dump(mode='json',exclude={'reason'}))
            state['decisions'].append({'id':str(uuid4()),'type':'plan','orderId':order_id,'before':before,
                                       'after':body.model_dump(mode='json'),'at':now()})
            return order
        return mutate('update_plan',body.reason,change)

    @router.post('/records',status_code=201)
    def record(body: RecordInput):
        if body.day>date.today():
            raise HTTPException(422,'Não é permitido registrar produção futura.')
        if body.operation not in OPERATIONS:
            raise HTTPException(422,'Operação inválida.')
        def change(state):
            item={**body.model_dump(mode='json'),'id':str(uuid4()),'createdAt':now(),'dataOrigin':'mock'}
            apply_record(state,item)
            return item
        return mutate('record_production','Apontamento demonstrativo de produção',change)

    @router.get('/orders/{order_id}/analysis')
    def analysis(order_id: str):
        order=find(store.read(),order_id)
        reference=date.today()
        baseline=snapshot(order,reference)
        row=feature_row(order,reference)
        conditions=[]
        if baseline['remaining']==0:
            conditions.append('Lote já concluído; sem previsão futura.')
        if baseline['days']==0:
            conditions.append('Prazo atingido ou vencido; sem classificação futura.')
        ranges=[(50,8000),(1,30),(50,600),(0,660),(0,.3)]
        if any(not lo<=value<=hi for value,(lo,hi) in zip(row,ranges)):
            conditions.append('Entrada fora dos intervalos do gerador sintético.')
        result={'executionMode':'model','inputDataOrigin':'mock','trainingDataOrigin':'synthetic',
                'modelVersion':VERSION,'generatedAt':now(),'orderId':order_id,
                'snapshot':baseline,'featureSnapshot':dict(zip(['remaining','days','capacityPerDay','recentRate','reworkRate'],row)),
                'notice':NOTICE,'calibrated':False,'mlAvailable':False,'ml':None,
                'estimatedDeliveryDate':None}
        if conditions:
            result['reason']=' '.join(conditions)
        else:
            try:
                prediction=model.predict(row)
                result['ml']={**prediction,'estimatedDays':baseline['remaining']/prediction['futureRate'] if prediction['futureRate']>0 else None}
                result['mlAvailable']=True
                if prediction['futureRate']>0:
                    result['estimatedDeliveryDate']=(reference+timedelta(days=math.ceil(baseline['remaining']/prediction['futureRate']))).isoformat()
            except Exception as exc:
                result['reason']=str(exc)
        result['suggestions']=[
            'Revisar capacidade e prazo com a gestão; não aplicar automaticamente.',
            'Conferir gargalos por operação e disponibilidade antes de redistribuir tarefas.',
            'Investigar retrabalho e qualidade sem somar etapas como peças concluídas.']
        return result

    @router.get('/recommendations')
    def recommend(operation:str,period:date,minutes:int=60):
        if period < date.today():
            raise HTTPException(422,'Use um período atual ou futuro.')
        if operation not in OPERATIONS or not 1<=minutes<=480:
            raise HTTPException(422,'Operação ou duração inválida.')
        return recommendations(store.read(),operation,minutes,period.isoformat())

    @router.post('/assignments',status_code=201)
    def assign(body: AssignmentInput):
        if body.period<date.today():
            raise HTTPException(422,'Use um período atual ou futuro.')
        def change(state):
            order=find(state,body.orderId)
            if order['status']=='Concluído':
                raise ValueError('Lote concluído não recebe alocação.')
            eligible=recommendations(state,body.operation,body.minutes,body.period.isoformat())['eligible']
            if not any(e['employeeId']==body.employeeId for e in eligible):
                raise ValueError('Colaborador não elegível; atualize as recomendações.')
            decision={**body.model_dump(mode='json'),'id':str(uuid4()),'at':now(),'executionMode':'heuristic','dataOrigin':'mock'}
            state['decisions'].append(decision)
            if body.decision=='accepted':
                state['assignments'].append(decision)
            return decision
        return mutate('assignment_decision',body.reason,change)

    @router.post('/assignments/{assignment_id}/reallocate')
    def reallocate(assignment_id:str,body:ReallocationInput):
        if body.period<date.today():
            raise HTTPException(422,'Use um período atual ou futuro.')
        def change(state):
            previous=next((a for a in state['assignments'] if a['id']==assignment_id),None)
            if previous is None:
                raise ValueError('Alocação não encontrada ou já redistribuída.')
            if date.fromisoformat(previous['period'])<date.today():
                raise ValueError('Alocação passada não pode ser redistribuída.')
            order=find(state,previous['orderId'])
            if order['status']=='Concluído':
                raise ValueError('Lote concluído não pode ser redistribuído.')
            state['assignments'].remove(previous)
            eligible=recommendations(state,previous['operation'],body.minutes,body.period.isoformat())['eligible']
            if not any(e['employeeId']==body.employeeId for e in eligible):
                raise ValueError('Destino sem habilitação ou minutos disponíveis.')
            current={**previous,**body.model_dump(mode='json'),'id':str(uuid4()),'at':now()}
            state['assignments'].append(current)
            state['decisions'].append({'id':str(uuid4()),'type':'reallocation','before':previous,'after':current,'at':now(),'reason':body.reason})
            return current
        return mutate('reallocation',body.reason,change)

    def mutate(action,reason,callback):
        try:
            return store.update(action,reason,callback)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        except OSError as exc:
            raise HTTPException(503,'Falha ao gravar a demonstração. Nenhuma alteração foi aplicada.') from exc

    return router


def find(state,order_id):
    order=next((o for o in state['orders'] if o['id']==order_id),None)
    if order is None:
        raise HTTPException(404,'Lote não encontrado.')
    return order
