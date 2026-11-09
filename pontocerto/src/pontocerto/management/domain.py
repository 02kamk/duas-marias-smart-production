"""Regras da demonstração local. Quantidades finais não somam operações."""
from datetime import date, datetime, timezone
import math


def now():
    return datetime.now(timezone.utc).isoformat()


def snapshot(order, reference):
    remaining = order['quantity'] - order['produced']
    days = max(0, (date.fromisoformat(order['dueDate']) - reference).days)
    rate = order['recentRate']
    capacity = order['capacityPerDay']
    required = remaining / days if days else None
    factors = []
    if not days and remaining:
        factors.append('Prazo atingido ou vencido com saldo pendente.')
    if required is not None and rate < required:
        factors.append('Ritmo recente informado abaixo da necessidade por dia.')
    if required is not None and capacity < required:
        factors.append('Capacidade planejada abaixo da necessidade por dia.')
    if order['reworkRate'] >= .1:
        factors.append('Retrabalho informado igual ou superior a 10%.')
    if not factors:
        factors.append('Sem alerta na comparação determinística de capacidade.')
    return {'remaining': remaining, 'days': days, 'requiredPerDay': required,
            'estimatedDaysAtRecentRate': math.ceil(remaining/rate) if rate else None,
            'baselineLate': bool(remaining and (not days or remaining > min(rate, capacity)*days)),
            'factors': factors, 'referenceDate': reference.isoformat(),
            'calendar': 'dias corridos; prazo diário exclusivo, sem produção futura no dia-base'}


FEATURES = ['remaining', 'days', 'capacityPerDay', 'recentRate', 'reworkRate']


def feature_row(order, reference):
    s = snapshot(order, reference)
    return [s['remaining'], s['days'], order['capacityPerDay'], order['recentRate'], order['reworkRate']]


def apply_record(state, record):
    order = next((o for o in state['orders'] if o['id'] == record['orderId']), None)
    if order is None:
        raise ValueError('Lote não encontrado.')
    employee = next((e for e in state['employees'] if e['id'] == record['employeeId']), None)
    if employee is None or not employee['active']:
        raise ValueError('Colaborador inexistente ou inativo.')
    if record['operation'] not in employee['skills']:
        raise ValueError('Colaborador não habilitado para a operação.')
    if order['produced'] == order['quantity']:
        raise ValueError('Lote concluído não recebe novos apontamentos.')
    if not record['goodQuantity'] + record['reworkQuantity']:
        raise ValueError('Informe ao menos uma peça.')
    if record['goodQuantity'] + record['reworkQuantity'] > order['quantity']:
        raise ValueError('Quantidade do apontamento excede o lote.')
    # Neste módulo somente revisão final produz peças finais boas.
    if record['operation'] == 'Revisão final':
        if order['produced'] + record['goodQuantity'] > order['quantity']:
            raise ValueError('Produção boa excede o saldo; nada foi truncado.')
        order['produced'] += record['goodQuantity']
    order['status'] = 'Concluído' if order['produced'] == order['quantity'] else 'Em andamento'
    state['records'].append(record)


def recommendations(state, operation, minutes, period):
    eligible, excluded = [], []
    for employee in state['employees']:
        reserved = sum(a['minutes'] for a in state['assignments']
                       if a['employeeId'] == employee['id'] and a['period'] == period)
        available = max(0, employee['availableMinutes'] - reserved)
        skill = employee['skills'].get(operation)
        reason = None
        if not employee['active']:
            reason = 'Inativo'
        elif not skill:
            reason = 'Sem habilitação'
        elif available < minutes:
            reason = 'Disponibilidade insuficiente no período'
        elif any(skill.get(k) is None for k in ['rate', 'quality', 'experience']):
            reason = 'Histórico incompleto; revisão humana necessária'
        if reason:
            excluded.append({'employeeId': employee['id'], 'name': employee['name'], 'reason': reason})
        else:
            eligible.append({'employeeId': employee['id'], 'name': employee['name'],
                             'availableMinutes': available, 'skill': skill})
    maximum = max((e['skill']['rate'] for e in eligible), default=1)
    for e in eligible:
        skill = e.pop('skill')
        components = {'productivity': skill['rate']/maximum, 'quality': skill['quality'],
                      'experience': skill['experience']/5, 'availability': min(1, e['availableMinutes']/480)}
        e['components'] = components
        e['score'] = round(100*sum(components[k]*w for k,w in
                                 {'productivity': .35, 'quality': .3, 'experience': .2, 'availability': .15}.items()), 2)
    return {'executionMode': 'heuristic', 'dataOrigin': 'mock', 'weightsVersion': 'demo-v1',
            'weights': {'productivity': .35, 'quality': .3, 'experience': .2, 'availability': .15},
            'eligible': sorted(eligible, key=lambda e: (-e['score'], e['employeeId'])),
            'excluded': excluded, 'notice': 'Score demonstrativo por operação; não é ML nem otimização global.'}
