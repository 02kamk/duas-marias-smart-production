"""Ensaio de leitura do app completo: não liga câmera nem grava produção."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))

if __name__=='__main__':
    from fastapi.testclient import TestClient
    from pontocerto.management.app import create_app
    root=Path(__file__).resolve().parents[1]
    app=create_app()
    with TestClient(app) as client:
        results={}
        for path in ['/','/gestao','/api/status','/api/saude','/api/taxonomia',
                     '/api/gestao/state','/api/gestao/model']:
            response=client.get(path)
            if response.status_code!=200:
                raise RuntimeError(f'{path}: HTTP {response.status_code}')
            results[path]=response.status_code
        original=(root/'src/pontocerto/app/static/index.html').read_text(encoding='utf-8')
        served=client.get('/').text.replace('\r\n','\n')
        if not all(fragment in served for fragment in original.split('</body>')):
            raise RuntimeError('A extensão não preservou o HTML original.')
        results['originalHtmlPreserved']=True
        orders=client.get('/api/gestao/state').json()['orders']
        if orders:
            analysis=client.get(f"/api/gestao/orders/{orders[0]['id']}/analysis")
            if analysis.status_code!=200:
                raise RuntimeError('Falha no endpoint de análise.')
            results['analysis']=analysis.json()
        print(json.dumps(results,ensure_ascii=True,indent=2))
