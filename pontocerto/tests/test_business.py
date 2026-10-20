import copy
import csv
import json
import os
from datetime import date,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pontocerto.business.api import create_router
from pontocerto.business.app import extend_business
from pontocerto.business.finance import report,monthly,forecasting
from pontocerto.business.ledger import LedgerStore,cents,month_shift,empty
from pontocerto.business.productivity import PublicProductivity,FEATURES,EXCLUDED

ROOT=Path(__file__).resolve().parents[1]


def history_fixture():
    state=empty('real')
    current=date.today().isoformat()[:7]
    start=month_shift(current,-12)
    state['settings'].update(openingDate=start+'-01',openingBalanceCents=1000000,
                              historyStartMonth=start,historyThroughMonth=month_shift(current,-1))
    for i in range(12):
        month=month_shift(start,i)
        for kind,amount in [('income',100000),('expense',80000)]:
            state['entries'].append({'id':f'{month}-{kind}','reference':f'{month}-{kind}','type':kind,'nature':'operating',
                'category':'Teste','description':'Fixture','amountCents':amount,'documentDate':month+'-01',
                'dueDate':month+'-15','settledDate':month+'-15','status':'settled'})
    return state


class FinanceRulesTest(unittest.TestCase):
    def test_money_uses_integer_cents(self):
        self.assertEqual(cents('1234.56'),123456)
        self.assertEqual(cents('1.234,56'),123456)
        self.assertEqual(cents('0.29'),29)
        for bad in ['1.005','-1','0','NaN','Infinity',True,'abc']:
            with self.assertRaises(ValueError):
                cents(bad)

    def test_empty_actual_environment_has_no_fabricated_forecast(self):
        result=report(empty('real'))
        self.assertFalse(result['forecastAvailable'])
        self.assertIsNone(result['forecast'][0]['cashCents'])
        self.assertEqual(result['health'],'yellow')
        self.assertEqual(result['allocation']['equipmentCents'],0)

    def test_capital_inflow_does_not_become_invoiced_revenue(self):
        state=history_fixture()
        last=state['settings']['historyThroughMonth']
        state['entries'].append({'id':'capital','reference':'CAP','type':'income','nature':'financing',
            'amountCents':500000,'documentDate':last+'-01','dueDate':last+'-02','settledDate':last+'-02','status':'settled'})
        row=monthly(state,date.today())[-1]
        self.assertEqual(row['invoicedCents'],100000)
        self.assertEqual(row['operatingReceiptsCents'],100000)
        self.assertEqual(row['receiptsCents'],600000)

    def test_invoice_is_not_cash_and_scheduled_receipts_not_double_counted(self):
        state=history_fixture()
        before=report(state)
        nextmonth=month_shift(date.today().isoformat(),1)
        state['entries'].append({'id':'pending','reference':'P','type':'income','nature':'operating','amountCents':70000,
            'documentDate':date.today().isoformat(),'dueDate':nextmonth+'-10','settledDate':None,'status':'open'})
        result=report(state)
        self.assertEqual(result['cashCents'],before['cashCents'])
        self.assertEqual(result['forecast'][0]['receiptsCents'],100000)
        self.assertEqual(result['forecast'][0]['scheduledReceiptsCents'],70000)

    def test_equipment_obligation_is_added_without_recurring_history_duplication(self):
        state=history_fixture()
        m=month_shift(date.today().isoformat(),1)
        state['entries'].append({'id':'equip','reference':'E','type':'expense','nature':'equipment','amountCents':25000,
            'documentDate':date.today().isoformat(),'dueDate':m+'-10','settledDate':None,'status':'open'})
        result=report(state)
        self.assertEqual(result['forecast'][0]['paymentsCents'],105000)

    def test_overdue_blocks_equipment_budget(self):
        state=history_fixture()
        yesterday=(date.today()-timedelta(days=1)).isoformat()
        state['entries'].append({'id':'due','reference':'D','type':'expense','nature':'operating','amountCents':10000,
            'documentDate':yesterday,'dueDate':yesterday,'settledDate':None,'status':'open'})
        result=report(state)
        self.assertTrue(result['allocation']['blocked'])
        self.assertEqual(result['allocation']['equipmentCents'],0)
        self.assertEqual(result['overduePayableCents'],10000)

    def test_allocations_never_exceed_cash_after_commitments_and_reserve(self):
        result=report(history_fixture())
        a=result['allocation']
        self.assertLessEqual(a['equipmentCents']+a['contingencyCents']+a['unallocatedCents'],a['surplusCents'])
        self.assertLessEqual(a['surplusCents']+a['reserveFundedCents']+result['payable30Cents'],result['cashCents'])
        floor=min(r['stressCashCents'] for r in result['forecast'])
        self.assertLessEqual(a['equipmentCents']+a['contingencyCents'],max(0,floor-a['reserveTargetCents']))

    def test_future_test_values_do_not_select_algorithm(self):
        original=[100+i*10 for i in range(18)]
        changed=original[:-3]+[100000,200000,300000]
        self.assertEqual(forecasting(original,3)['algorithm'],forecasting(changed,3)['algorithm'])


class BusinessApiTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(dir=os.environ.get('PC_TEST_TMP'))
        self.root=Path(self.temp.name)
        self.app=FastAPI()
        self.app.include_router(create_router(self.root))
        self.client=TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def body(self,**changes):
        today=date.today().isoformat()
        return {'reference':'NF-001','type':'income','nature':'operating','category':'Serviços','description':'Teste local',
                'amount':'1234.56','documentDate':today,'dueDate':today,'settledDate':None,**changes}

    def test_demo_and_real_are_isolated_and_real_starts_empty(self):
        actual=self.client.get('/api/business/finance/real/state').json()
        demonstration=self.client.get('/api/business/finance/demo/state').json()
        self.assertEqual(len(actual['entries']),0)
        self.assertEqual(len(demonstration['entries']),72)
        self.assertEqual(self.client.post('/api/business/finance/real/entries',json=self.body()).status_code,201)
        self.assertEqual(len(self.client.get('/api/business/finance/demo/state').json()['entries']),72)
        self.assertEqual(len(LedgerStore(self.root/'artifacts/finance_local/real.json','real').read()['entries']),1)

    def test_settlement_once_and_cancel_paid_document_disallowed(self):
        item=self.client.post('/api/business/finance/real/entries',json=self.body()).json()
        url=f"/api/business/finance/real/entries/{item['id']}"
        body={'settledDate':date.today().isoformat(),'reason':'Recebimento conferido'}
        self.assertEqual(self.client.post(url+'/settle',json=body).status_code,200)
        self.assertEqual(self.client.post(url+'/settle',json=body).status_code,422)
        self.assertEqual(self.client.post(url+'/cancel',json={'reason':'Teste de cancelamento'}).status_code,422)
        result=self.client.get('/api/business/finance/real/report').json()
        self.assertEqual(result['cashCents'],123456)

    def test_cancel_open_keeps_record_and_reason(self):
        item=self.client.post('/api/business/finance/real/entries',json=self.body()).json()
        self.assertEqual(self.client.post(f"/api/business/finance/real/entries/{item['id']}/cancel",json={'reason':'Documento incorreto'}).status_code,200)
        state=self.client.get('/api/business/finance/real/state').json()
        self.assertEqual(len(state['entries']),1)
        self.assertEqual(state['entries'][0]['status'],'cancelled')
        self.assertEqual(len(state['audit']),2)

    def test_import_is_atomic_and_references_unique(self):
        today=date.today().isoformat()
        header='reference;type;nature;category;description;amount;documentDate;dueDate;settledDate\n'
        row=f'CSV-1;expense;operating;Energia;Teste;10,25;{today};{today};\n'
        response=self.client.post('/api/business/finance/real/import',json={'csv':header+row+row})
        self.assertEqual(response.status_code,422)
        self.assertEqual(len(self.client.get('/api/business/finance/real/state').json()['entries']),0)
        self.assertEqual(self.client.post('/api/business/finance/real/import',json={'csv':header+row}).status_code,201)
        self.assertEqual(self.client.post('/api/business/finance/real/import',json={'csv':header+row}).status_code,422)
        self.assertEqual(len(self.client.get('/api/business/finance/real/state').json()['entries']),1)

    def test_invalid_money_dates_and_origin_are_rejected(self):
        for changes in [{'amount':'-10'},{'amount':'1.234'},{'settledDate':(date.today()+timedelta(days=1)).isoformat()},
                        {'dueDate':'2000-01-01'},{'documentDate':'2000-01-01','dueDate':'2000-01-02'}]:
            self.assertEqual(self.client.post('/api/business/finance/real/entries',json=self.body(**changes)).status_code,422)
        self.assertEqual(self.client.get('/api/business/finance/unknown/state').status_code,422)

    def test_policy_rejects_overallocation_and_invalid_complete_months(self):
        settings=self.client.get('/api/business/finance/real/state').json()['settings']
        settings.update(equipmentPercent=80,contingencyPercent=40,reason='Alteração de cenário')
        self.assertEqual(self.client.patch('/api/business/finance/real/settings',json=settings).status_code,422)
        settings.update(equipmentPercent=20,contingencyPercent=10,historyStartMonth='2020-01',historyThroughMonth=date.today().isoformat()[:7])
        self.assertEqual(self.client.patch('/api/business/finance/real/settings',json=settings).status_code,422)

    def test_additive_routes_do_not_remove_old_routes(self):
        app=FastAPI()
        from fastapi.responses import HTMLResponse
        @app.get('/')
        def original():
            return HTMLResponse('<html><body><button id="camera-original">Câmera</button></body></html>')
        extend_business(app,self.root)
        with TestClient(app) as client:
            self.assertIn('camera-original',client.get('/').text)
            self.assertIn('/financeiro',client.get('/').text)
            self.assertEqual(client.get('/financeiro').status_code,200)
            self.assertEqual(client.get('/produtividade').status_code,200)
            self.assertEqual(client.post('/api/business/finance/real/entries',json=self.body(),headers={'origin':'https://outside.example'}).status_code,403)


class PublicEvidenceTest(unittest.TestCase):
    def test_temporal_groups_source_and_features(self):
        directory=ROOT/'artifacts/productivity_public'
        metadata=json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['originalRows'],1197)
        self.assertEqual(metadata['license'],'CC BY 4.0')
        self.assertEqual(metadata['selectedModel'],min(metadata['validation'],key=lambda n:metadata['validation'][n]['mae']))
        self.assertTrue(set(FEATURES).isdisjoint(EXCLUDED))
        with (directory/'splits.csv').open(encoding='utf-8') as stream:
            rows=list(csv.DictReader(stream))
        dates={split:{r['date'] for r in rows if r['split']==split} for split in ['train','validation','test']}
        self.assertLess(max(dates['train']),min(dates['validation']))
        self.assertLess(max(dates['validation']),min(dates['test']))
        self.assertEqual(sum(p['rows'] for p in metadata['partitions'].values()),1197)
        result=PublicProductivity(directory).predict({'date':'2015-03-12','department':'sweing','team':8,'no_of_workers':59,
              'no_of_style_change':0,'targeted_productivity':.8,'smv':26.16})
        self.assertGreater(result['value'],0)
        self.assertEqual(result['trainingDataOrigin'],'public')


if __name__=='__main__':
    unittest.main()
