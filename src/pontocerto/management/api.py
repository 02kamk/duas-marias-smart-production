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
    fabric: str = Field(default='',max_length=60)


class PlanInput(Input):
    dueDate: date
    capacityPerDay: float = Field(gt=0,le=10000)
    recentRate: float = Field(ge=0,le=11000)
    reworkRate: float = Field(ge=0,le=.3)
    reason: str = Field(default='Ajuste de planejamento',min_length=3,max_length=300)


class RecordInput(Input):
    orderId: str
    employeeId: str
    operation: str
    goodQuantity: int = Field(strict=True,ge=0,le=1000000)
    reworkQuantity: int = Field(strict=True,ge=0,le=1000000)
    day: date


class RecordEdit(Input):
    goodQuantity: int = Field(strict=True,ge=0,le=1000000)
    reworkQuantity: int = Field(strict=True,ge=0,le=1000000)
    reason: str = Field(min_length=3,max_length=300)


class RecordRemoval(Input):
    reason: str = Field(min_length=3,max_length=300)


class AssignmentInput(Input):
    orderId: str
    employeeId: str
    operation: str
    minutes: int = Field(strict=True,gt=0,le=480)
    period: date
    decision: Literal['accepted','rejected'] = 'accepted'
    reason: str = Field(default='Atribuída na distribuição de tarefas',min_length=3,max_length=300)


class EmployeeInput(Input):
    name: str = Field(min_length=2, max_length=100)
    availableMinutes: int = Field(strict=True, ge=1, le=480)
    operations: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def valid_operations(self):
        if len(set(self.operations)) != len(self.operations) or any(op not in OPERATIONS for op in self.operations):
            raise ValueError('Selecione operações válidas, sem repetições.')
        return self


class EmployeeUpdate(Input):
    availableMinutes: int | None = Field(default=None, strict=True, ge=1, le=480)
    operations: list[str] | None = None
    active: bool | None = None

    @model_validator(mode='after')
    def valid_operations(self):
        if self.operations is not None and (not self.operations or len(set(self.operations)) != len(self.operations)
                                            or any(op not in OPERATIONS for op in self.operations)):
            raise ValueError('Selecione ao menos uma operação válida, sem repetições.')
        return self


class ReallocationInput(Input):
    employeeId: str
    period: date
    minutes: int = Field(strict=True,gt=0,le=480)
    reason: str = Field(default='Tarefa passada para outra pessoa',min_length=3,max_length=300)


def create_router(store: Store, model: DelayModel):
    router = APIRouter(prefix='/api/gestao', tags=['Gestão demonstrativa'])

    @router.get('/state')
    def state():
        data=store.read()
        today=date.today()
        # Previsão simples por lote, para a lista mostrar o risco sem abrir o detalhe.
        for order in data['orders']:
            snap=snapshot(order,today)
            dias=snap['estimatedDaysAtRecentRate']
            order['forecast']={'late':snap['baselineLate'],'remaining':snap['remaining'],
                               'estimatedDeliveryDate':(today+timedelta(days=dias)).isoformat() if dias is not None and snap['remaining'] else None}
        return {**data, 'operations': OPERATIONS, 'referenceDate': today.isoformat(),
                'notice': 'Ambiente de testes. Confira a origem dos dados antes de tomar decisões operacionais.',
                'storage':getattr(store,'backend','local')}

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
        return mutate('create_employee', 'Cadastro sem histórico de produtividade', change)

    @router.patch('/employees/{employee_id}')
    def update_employee(employee_id: str, body: EmployeeUpdate):
        def change(state):
            employee = next((e for e in state['employees'] if e['id'] == employee_id), None)
            if employee is None:
                raise ValueError('Colaborador não encontrado.')
            if body.availableMinutes is not None:
                employee['availableMinutes'] = body.availableMinutes
            if body.active is not None:
                employee['active'] = body.active
            if body.operations is not None:
                # Mantém o histórico das operações que continuam habilitadas.
                employee['skills'] = {op: employee['skills'].get(op, {'rate': None, 'quality': None, 'experience': None})
                                      for op in body.operations}
            return employee
        return mutate('update_employee', 'Cadastro de colaborador atualizado', change)

    @router.post('/orders',status_code=201)
    def create_order(body: OrderInput):
        def change(state):
            if any(o['code'].casefold()==body.code.casefold() for o in state['orders']):
                raise ValueError('Código de lote já existe.')
            order={**body.model_dump(mode='json'),'id':str(uuid4()),'produced':0,'status':'Planejado'}
            state['orders'].append(order)
            return order
        return mutate('create_order','Cadastro de lote',change)

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
            item={**body.model_dump(mode='json'),'id':str(uuid4()),'createdAt':now()}
            apply_record(state,item)
            return item
        return mutate('record_production','Apontamento de produção',change)

    def situacao_do_lote(state,order):
        if order['produced']==order['quantity']:
            return 'Concluído'
        tem_registro=any(r['orderId']==order['id'] for r in state['records'])
        return 'Em andamento' if order['produced'] or tem_registro else 'Planejado'

    def achar_registro(state,record_id):
        item=next((r for r in state['records'] if r['id']==record_id),None)
        if item is None:
            raise ValueError('Apontamento não encontrado.')
        order=next((o for o in state['orders'] if o['id']==item['orderId']),None)
        if order is None:
            raise ValueError('Lote não encontrado.')
        return item,order

    @router.patch('/records/{record_id}')
    def edit_record(record_id: str, body: RecordEdit):
        """Corrige as quantidades de um apontamento, com motivo na trilha de auditoria."""
        def change(state):
            item,order=achar_registro(state,record_id)
            if not body.goodQuantity+body.reworkQuantity:
                raise ValueError('Informe ao menos uma peça. Para remover o apontamento, use Excluir.')
            if body.goodQuantity+body.reworkQuantity>order['quantity']:
                raise ValueError('Quantidade do apontamento excede o lote.')
            if item['operation']=='Revisão final':
                produced=order['produced']-item['goodQuantity']+body.goodQuantity
                if produced>order['quantity']:
                    raise ValueError('Produção boa excede o saldo do lote.')
                order['produced']=max(0,produced)
            antes={'goodQuantity':item['goodQuantity'],'reworkQuantity':item['reworkQuantity']}
            item.update(goodQuantity=body.goodQuantity,reworkQuantity=body.reworkQuantity,editedAt=now())
            order['status']=situacao_do_lote(state,order)
            state['decisions'].append({'id':str(uuid4()),'type':'record_edit','recordId':record_id,'before':antes,
                                       'after':{'goodQuantity':body.goodQuantity,'reworkQuantity':body.reworkQuantity},
                                       'at':now(),'reason':body.reason})
            return item
        return mutate('record_edit',body.reason,change)

    @router.delete('/records/{record_id}')
    def remove_record(record_id: str, body: RecordRemoval):
        """Exclui um apontamento lançado por engano e devolve as peças ao saldo do lote."""
        def change(state):
            item,order=achar_registro(state,record_id)
            if item['operation']=='Revisão final':
                order['produced']=max(0,order['produced']-item['goodQuantity'])
            state['records'].remove(item)
            order['status']=situacao_do_lote(state,order)
            state['decisions'].append({'id':str(uuid4()),'type':'record_removal','before':item,'at':now(),'reason':body.reason})
            return {'removed':record_id}
        return mutate('record_removal',body.reason,change)

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
            conditions.append('Valores fora da faixa em que o modelo experimental foi treinado.')
        # A previsão principal vem do ritmo informado; o modelo é só um detalhe opcional.
        dias_ritmo=baseline['estimatedDaysAtRecentRate']
        result={'modelVersion':VERSION,'generatedAt':now(),'orderId':order_id,
                'snapshot':baseline,'notice':NOTICE,'mlAvailable':False,'ml':None,
                'estimatedDeliveryDate':(reference+timedelta(days=dias_ritmo)).isoformat() if dias_ritmo is not None else None}
        if conditions:
            result['reason']=' '.join(conditions)
        else:
            try:
                prediction=model.predict(row)
                result['ml']={**prediction,'estimatedDays':baseline['remaining']/prediction['futureRate'] if prediction['futureRate']>0 else None}
                result['mlAvailable']=True
            except Exception as exc:
                result['reason']=str(exc)
        result['suggestions']=sugestoes(order,baseline)
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


def sugestoes(order,snap):
    """O que fazer agora, a partir da situação deste lote."""
    itens=[]
    falta=snap['remaining']
    if not falta:
        return ['Lote concluído. Nada a fazer.']
    necessario=snap['requiredPerDay']
    if not snap['days']:
        itens.append('O prazo venceu com peças pendentes: combine uma nova data com o cliente.')
    elif necessario is not None and order['recentRate']<necessario:
        extra=math.ceil(necessario-order['recentRate'])
        itens.append(f'Aumente a produção em cerca de {extra} peças por dia, ou renegocie o prazo.')
        if order['capacityPerDay']<necessario:
            itens.append('A capacidade planejada não cobre o prazo: distribua mais tarefas para este lote em Produção.')
    if order['reworkRate']>=.1:
        itens.append('O retrabalho está alto: confira os defeitos mais frequentes na inspeção deste lote.')
    if not itens:
        itens.append('O ritmo atual atende ao prazo. Mantenha o acompanhamento diário.')
    return itens


def find(state,order_id):
    order=next((o for o in state['orders'] if o['id']==order_id),None)
    if order is None:
        raise HTTPException(404,'Lote não encontrado.')
    return order
