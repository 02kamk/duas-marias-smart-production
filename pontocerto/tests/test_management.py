import os
import csv
import json
from datetime import date,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pontocerto.management.api import create_router
from pontocerto.management.app import extend
from pontocerto.management.domain import apply_record,snapshot,feature_row,recommendations
from pontocerto.management.experiment import DelayModel,FEATURES
from pontocerto.management.store import Store,seed

ROOT=Path(__file__).resolve().parents[1]


class ManagementTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(dir=os.environ.get('PC_TEST_TMP'))
        self.root=Path(self.temp.name)
        self.store=Store(self.root/'demo.json')
        self.model=DelayModel(self.root/'absent_model')
        app=FastAPI()
        app.include_router(create_router(self.store,self.model))
        self.client=TestClient(app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def record(self,**updates):
        return {'orderId':'1','employeeId':'1','operation':'Revisão final',
                'goodQuantity':10,'reworkQuantity':2,'day':date.today().isoformat(),**updates}

    def test_final_stage_only_and_persistence(self):
        self.assertEqual(self.client.post('/api/gestao/records',json=self.record(operation='Gola')).status_code,201)
        self.assertEqual(self.store.read()['orders'][0]['produced'],1950)
        self.assertEqual(self.client.post('/api/gestao/records',json=self.record()).status_code,201)
        self.assertEqual(Store(self.root/'demo.json').read()['orders'][0]['produced'],1960)
        self.assertEqual(len(self.store.read()['audit']),2)

    def test_invalid_records_are_atomic(self):
        before=self.store.read()
        for body in [self.record(goodQuantity=-1),self.record(goodQuantity=1.5),self.record(goodQuantity=True),
                     self.record(goodQuantity=0,reworkQuantity=0),self.record(goodQuantity=1051),
                     self.record(employeeId='missing'),self.record(operation='inválida'),
                     self.record(day=(date.today()+timedelta(days=1)).isoformat()),
                     self.record(employeeId='3',operation='Gola')]:
            self.assertEqual(self.client.post('/api/gestao/records',json=body).status_code,422,body)
        self.assertEqual(before,self.store.read())

    def test_complete_order_and_reject_further_records(self):
        self.assertEqual(self.client.post('/api/gestao/records',json=self.record(goodQuantity=1050)).status_code,201)
        self.assertEqual(self.store.read()['orders'][0]['status'],'Concluído')
        self.assertEqual(self.client.post('/api/gestao/records',json=self.record()).status_code,422)

    def test_duplicate_code_and_plan_audit(self):
        order=self.store.read()['orders'][0]
        body={k:order[k] for k in ['code','client','model','quantity','dueDate','capacityPerDay','recentRate','reworkRate']}
        self.assertEqual(self.client.post('/api/gestao/orders',json=body).status_code,422)
        body['code']='NEW-001'
        self.assertEqual(self.client.post('/api/gestao/orders',json=body).status_code,201)
        plan={k:order[k] for k in ['dueDate','capacityPerDay','recentRate','reworkRate']}
        plan.update({'capacityPerDay':300,'reason':'Revisão de capacidade demo'})
        self.assertEqual(self.client.patch('/api/gestao/orders/1/plan',json=plan).status_code,200)
        change=self.store.read()['decisions'][-1]
        self.assertEqual(change['before']['capacityPerDay'],286)
        self.assertEqual(change['after']['capacityPerDay'],300)

    def test_reservations_eligibility_and_rejection(self):
        body={'orderId':'1','employeeId':'1','operation':'Gola','minutes':180,'period':date.today().isoformat(),
              'decision':'rejected','reason':'Revisão humana demo'}
        self.assertEqual(self.client.post('/api/gestao/assignments',json=body).status_code,201)
        self.assertEqual(len(self.store.read()['assignments']),0)
        body['decision']='accepted'
        self.assertEqual(self.client.post('/api/gestao/assignments',json=body).status_code,201)
        self.assertEqual(self.client.post('/api/gestao/assignments',json=body).status_code,422)
        body['employeeId']='3'
        self.assertEqual(self.client.post('/api/gestao/assignments',json=body).status_code,422)

    def test_missing_model_is_explicit_and_baseline_separate(self):
        response=self.client.get('/api/gestao/orders/1/analysis').json()
        self.assertFalse(response['mlAvailable'])
        self.assertIsNone(response['ml'])
        self.assertTrue(response['snapshot']['baselineLate'])
        self.assertIn('Execute',response['reason'])
        self.assertEqual(self.client.get('/api/gestao/orders/missing/analysis').status_code,404)

    def test_snapshot_is_not_future_label(self):
        order=self.store.read()['orders'][0]
        self.assertEqual(len(feature_row(order,date.today())),5)
        self.assertEqual(FEATURES,['remaining','days','capacityPerDay','recentRate','reworkRate'])
        order['dueDate']=(date.today()-timedelta(days=1)).isoformat()
        self.assertIsNone(snapshot(order,date.today())['requiredPerDay'])
        self.store.state['orders'][0]=order
        response=self.client.get('/api/gestao/orders/1/analysis').json()
        self.assertFalse(response['mlAvailable'])

    def test_additive_extension_keeps_original_page_and_routes(self):
        app=FastAPI()
        from fastapi.responses import HTMLResponse
        @app.get('/')
        def original():
            return HTMLResponse('<html><body><button id="camera-original">Camera</button></body></html>')
        @app.get('/api/camera/original')
        def camera():
            return {'preserved':True}
        extended=extend(app,self.root)
        with TestClient(extended) as client:
            response=client.get('/')
            self.assertIn('camera-original',response.text)
            self.assertIn('href="/gestao"',response.text)
            self.assertTrue(client.get('/api/camera/original').json()['preserved'])
            self.assertEqual(client.get('/gestao').status_code,200)
            self.assertEqual(client.post('/api/gestao/orders',json={},headers={'origin':'https://other.example'}).status_code,403)


class ModelEvidenceTest(unittest.TestCase):
    def test_trained_artifact_and_split_manifest(self):
        directory=ROOT/'artifacts'/'gestao_ml'
        model=DelayModel(directory)
        status=model.status()
        self.assertTrue(status['available'])
        prediction=model.predict([1050,3,286,220,.05])
        self.assertTrue(0<=prediction['riskScore']<=1)
        self.assertGreater(prediction['futureRate'],0)
        with (directory/'dataset.csv').open(encoding='utf-8') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),2400)
        self.assertEqual(len({r['lotId'] for r in rows}),2400)
        split_ids={split:{r['lotId'] for r in rows if r['split']==split} for split in ['train','validation','test']}
        self.assertFalse(split_ids['train']&split_ids['test'])
        self.assertFalse(split_ids['validation']&split_ids['test'])
        self.assertFalse(split_ids['train']&split_ids['validation'])


if __name__=='__main__':
    unittest.main()
