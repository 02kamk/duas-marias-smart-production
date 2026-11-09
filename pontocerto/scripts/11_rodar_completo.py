import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--porta',type=int,default=8000)
    args=parser.parse_args()
    import uvicorn
    print(f'Inspecao: http://127.0.0.1:{args.porta}/',flush=True)
    print(f'Gestao: http://127.0.0.1:{args.porta}/gestao',flush=True)
    print(f'Financeiro: http://127.0.0.1:{args.porta}/financeiro',flush=True)
    print(f'Produtividade UCI: http://127.0.0.1:{args.porta}/produtividade',flush=True)
    uvicorn.run('pontocerto.business.app:create_app',factory=True,host='127.0.0.1',port=args.porta)
