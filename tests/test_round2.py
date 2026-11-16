import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pontocerto.management.documents import router,suggestions
from pontocerto.management.store import Store


class RoundTwo(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'state.json')
        app=FastAPI();app.include_router(router(self.store));self.client=TestClient(app)

    def tearDown(self):
        self.client.close();self.tmp.cleanup()

    def test_ocr_suggestions_do_not_invent_unreadable_fields(self):
        fields,grade=suggestions('OP: 123456\nCLIENTE: Teste\nMODELO: Camiseta\nQUANTIDADE: 100\nPP: 10\nM: 90')
        self.assertEqual(fields['code'],'123456')
        self.assertEqual(fields['quantity'],100)
        self.assertEqual(sum(r['expected'] for r in grade),100)
        self.assertEqual(suggestions('texto não estruturado'),({},[]))

    @unittest.skipUnless(importlib.util.find_spec('rapidocr_onnxruntime'),'OCR opcional não instalado (requirements-ocr.txt)')
    def test_ocr_is_preview_only_and_requires_review(self):
        img=io.BytesIO();Image.new('RGB',(100,100),'white').save(img,format='PNG')
        before=self.store.read()
        with patch('rapidocr_onnxruntime.RapidOCR') as constructor:
            constructor.return_value.return_value=([[[], 'OP: 123456', .9],[[], 'M: 100', .8]],0.1)
            with patch('pontocerto.management.documents._engine',None):
                result=self.client.post('/api/gestao/op/read',files={'arquivo':('op.png',img.getvalue(),'image/png')})
        self.assertEqual(result.status_code,200)
        self.assertTrue(result.json()['requiresReview'])
        self.assertEqual(result.json()['suggestions']['code'],'123456')
        self.assertEqual(before,self.store.read())
        self.assertEqual(self.client.post('/api/gestao/op/read',files={'arquivo':('bad.png',b'not an image','image/png')}).status_code,422)

    def test_pdf_export_and_configuration_do_not_expose_secrets(self):
        response=self.client.get('/api/gestao/report.pdf')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertIn('attachment',response.headers['content-disposition'])
        import pymupdf
        pdf=pymupdf.open(stream=response.content,filetype='pdf')
        text=''.join(p.get_text() for p in pdf)
        self.assertIn('OP-001',text)
        pdf.close()
        with patch('pontocerto.management.documents.variavel_env',return_value=None):
            config=self.client.get('/api/gestao/configuration').json()
        self.assertIn('SUPABASE_DB_URL',config['supabaseMissing'])
        self.assertNotIn('postgresql://',str(config))
