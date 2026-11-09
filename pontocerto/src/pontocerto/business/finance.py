"""Diagnóstico de caixa e projeções locais; premissas abertas, sem LLM externo."""
from datetime import date,timedelta
from statistics import mean
import hashlib
import json
from .ledger import now
from .ledger import month_shift


def monthly(state,asof):
    settings=state['settings']
    start,end=settings['historyStartMonth'],settings['historyThroughMonth']
    if not start or not end or end>=asof.isoformat()[:7]:
        return []
    rows=[]
    current=start
    while current<=end:
        row={'month':current,'invoicedCents':0,'receiptsCents':0,'paymentsCents':0,'operatingReceiptsCents':0,'operatingPaymentsCents':0}
        for entry in state['entries']:
            if entry['status']=='cancelled':
                continue
            if entry['type']=='income' and entry['nature']=='operating' and entry['documentDate'][:7]==current:
                row['invoicedCents']+=entry['amountCents']
            if entry['status']=='settled' and entry['settledDate'][:7]==current:
                row['receiptsCents' if entry['type']=='income' else 'paymentsCents']+=entry['amountCents']
                if entry['nature']=='operating':
                    row['operatingReceiptsCents' if entry['type']=='income' else 'operatingPaymentsCents']+=entry['amountCents']
        rows.append(row)
        current=month_shift(current,1)
        if len(rows)>240:
            raise ValueError('Histórico máximo de 240 meses neste protótipo.')
    return rows


def forecasting(values,horizon):
    """Validação rolling e teste separado; ajuste final em todo histórico confirmado."""
    import numpy as np
    from sklearn.linear_model import Ridge
    n=len(values)
    def predict(name,history,steps):
        if name=='last_month':
            return [float(history[-1])]*steps
        if name=='mean_3':
            return [float(mean(history[-3:]))]*steps
        model=Ridge(alpha=10)
        model.fit(np.arange(len(history)).reshape(-1,1),history)
        return model.predict(np.arange(len(history),len(history)+steps).reshape(-1,1)).tolist()
    candidates=['last_month','mean_3','ridge_trend']
    def backtest(name,origins):
        errors=[abs(values[i]-max(0,predict(name,values[:i],1)[0])) for i in origins]
        return round(mean(errors))
    validation={name:backtest(name,range(n-6,n-3)) for name in candidates}
    chosen=min(validation,key=validation.get)
    test={name:backtest(name,range(n-3,n)) for name in candidates}
    return {'algorithm':chosen,'values':[max(0,round(v)) for v in predict(chosen,values,horizon)],
            'validationMAECents':validation,'testMAECents':test,
            'protocol':'Seleção nos 3 meses de validação; teste nos 3 meses seguintes; só depois ajuste final no histórico completo.',
            'notice':'Teste avalia 1 passo; projeções de 2–6 meses têm incerteza adicional. Sem sazonalidade ou intervalo de confiança.'}


def report(state,asof=None,horizon=3):
    asof=asof or date.today()
    today=asof.isoformat()
    settings=state['settings']
    entries=[e for e in state['entries'] if e['status']!='cancelled']
    cash=settings['openingBalanceCents']+sum(
        e['amountCents']*(1 if e['type']=='income' else -1) for e in entries
        if e['status']=='settled' and settings['openingDate']<=e['settledDate']<=today)
    pending=[e for e in entries if e['status']=='open']
    thirty=(asof+timedelta(days=30)).isoformat()
    commitments=sum(e['amountCents'] for e in pending if e['type']=='expense' and e['dueDate']<=thirty)
    receivable=sum(e['amountCents'] for e in pending if e['type']=='income' and e['dueDate']<=thirty)
    overdue=sum(e['amountCents'] for e in pending if e['type']=='expense' and e['dueDate']<today)
    rows=monthly(state,asof)
    last_complete=month_shift(today,-1)
    eligible=len(rows)>=12 and rows[-1]['month']==last_complete
    models={}
    if eligible:
        for key in ['invoicedCents','receiptsCents','paymentsCents']:
            column={'invoicedCents':'invoicedCents','receiptsCents':'operatingReceiptsCents','paymentsCents':'operatingPaymentsCents'}[key]
            models[key]=forecasting([r[column] for r in rows],horizon)
    average_expense=round(mean([r['operatingPaymentsCents'] for r in rows[-3:]])) if rows else None
    reserve_target=average_expense*settings['reserveMonths'] if average_expense is not None else None
    # Não usa recebíveis incertos para financiar compra imediata.
    reserve_funding=min(max(cash-commitments,0),reserve_target or 0)
    surplus=max(0,cash-commitments-(reserve_target or 0)) if eligible else 0
    next_month=month_shift(today,1)
    this_month_end=(date.fromisoformat(next_month+'-01')-timedelta(days=1)).isoformat()
    current_pending_in=sum(e['amountCents'] for e in pending if e['type']=='income' and e['dueDate']<=this_month_end)
    current_pending_out=sum(e['amountCents'] for e in pending if e['type']=='expense' and e['dueDate']<=this_month_end)
    stress=settings['scenarioPercent']/100
    base_cash=cash+current_pending_in-current_pending_out
    stress_cash=cash+round(current_pending_in*(1-stress))-round(current_pending_out*(1+stress))
    forecasts=[]
    for i in range(horizon):
        month=month_shift(today,i+1)
        known_in=sum(e['amountCents'] for e in pending if e['type']=='income' and e['dueDate'][:7]==month)
        known_out=sum(e['amountCents'] for e in pending if e['type']=='expense' and e['dueDate'][:7]==month)
        if eligible:
            # O histórico total já inclui padrões de contas; não somar novamente o total às contas conhecidas.
            other_in=sum(e['amountCents'] for e in pending if e['type']=='income' and e['nature']!='operating' and e['dueDate'][:7]==month)
            other_out=sum(e['amountCents'] for e in pending if e['type']=='expense' and e['nature']!='operating' and e['dueDate'][:7]==month)
            receipts=max(known_in-other_in,models['receiptsCents']['values'][i])+other_in
            payments=max(known_out-other_out,models['paymentsCents']['values'][i])+other_out
            invoiced=models['invoicedCents']['values'][i]
            base_cash+=receipts-payments
            low_receipts=round(receipts*(1-stress))
            high_payments=round(payments*(1+stress))
            stress_cash+=low_receipts-high_payments
            forecasts.append({'month':month,'receiptsCents':receipts,'paymentsCents':payments,'invoicedCents':invoiced,
                'scheduledReceiptsCents':known_in,'scheduledPaymentsCents':known_out,
                'cashCents':base_cash,'stressCashCents':stress_cash,
                'stressReceiptsCents':low_receipts,'stressPaymentsCents':high_payments})
        else:
            forecasts.append({'month':month,'receiptsCents':None,'paymentsCents':None,'invoicedCents':None,
                'scheduledReceiptsCents':known_in,'scheduledPaymentsCents':known_out,'cashCents':None,'stressCashCents':None})
    forecast_floor=min((r['stressCashCents'] for r in forecasts if r['stressCashCents'] is not None),default=0)
    budget_base=min(surplus,max(0,forecast_floor-(reserve_target or 0))) if eligible else 0
    blocked=not eligible or overdue>0 or any(r['stressCashCents']<0 for r in forecasts if r['stressCashCents'] is not None) or cash-commitments<0
    equipment=0 if blocked else budget_base*settings['equipmentPercent']//100
    contingency=0 if blocked else budget_base*settings['contingencyPercent']//100
    unallocated=surplus-equipment-contingency
    health='red' if cash<0 or cash-commitments<0 or any(r['stressCashCents']<0 for r in forecasts if r['stressCashCents'] is not None) else (
        'yellow' if blocked or reserve_target is None or cash-commitments<reserve_target else 'green')
    explanations=[]
    if not eligible:
        explanations.append('Confirme pelo menos 12 meses consecutivos completos até o mês anterior para projeções e distribuição de excedente.')
    if overdue:
        explanations.append('Existem despesas vencidas em aberto; sugestão de equipamento bloqueada.')
    if health=='red':
        explanations.append('Caixa ou cenário de cobertura negativo; revisar recebimentos, vencimentos e custos antes de compras.')
    if reserve_target is not None:
        explanations.append(f'Reserva-alvo = média dos últimos 3 meses pagos × {settings["reserveMonths"]} meses configurados.')
    explanations.append('Recebíveis não são dinheiro disponível; a reserva e o excedente usam caixa atual menos despesas até 30 dias.')
    explanations.append('A base de distribuição também é limitada pelo menor caixa projetado no estresse, preservando a reserva-alvo futura.')
    explanations.append('Equipamentos e contingência são simulação de orçamento pelos percentuais escolhidos; não executam compras ou investimentos.')
    return {'modelVersion':'cashflow-v1','generatedAt':now(),
        'inputSha256':hashlib.sha256(json.dumps({'settings':settings,'entries':entries},sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest(),
        'environment':state['environment'],'asOf':today,'currency':'BRL','unit':'centavos',
        'dataOrigin':'mock' if state['environment']=='demo' else 'user_provided_unverified',
        'health':health,'healthScope':'cobertura de caixa pelos registros; não é diagnóstico completo nem lucro contábil',
        'cashCents':cash,'payable30Cents':commitments,'receivable30Cents':receivable,'overduePayableCents':overdue,
        'history':rows,'forecastAvailable':eligible,'forecast':forecasts,'forecastModels':models,
        'executionMode':'statistical_model' if eligible else 'rules_only','scenarioPercent':settings['scenarioPercent'],
        'allocation':{'reserveTargetCents':reserve_target,'reserveFundedCents':reserve_funding,
            'reserveGapCents':max(0,(reserve_target or 0)-reserve_funding),'surplusCents':surplus,'budgetBaseCents':budget_base,
            'equipmentCents':equipment,'contingencyCents':contingency,'unallocatedCents':unallocated,'blocked':blocked},
        'explanations':explanations,'currentMonthBridge':{'scheduledReceiptsCents':current_pending_in,'scheduledPaymentsCents':current_pending_out},
        'notice':'Projeções locais condicionadas aos registros e premissas. Cenário de estresse não é intervalo de confiança. Sem envio a IA externa.'}
