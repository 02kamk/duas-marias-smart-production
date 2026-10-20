"""Novo comando aditivo; o script 05 e a inspeção permanecem intactos."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--porta',type=int,default=8000)
    args=parser.parse_args()
    import uvicorn
    print('Ponto Certo original: http://127.0.0.1:'+str(args.porta)+'/',flush=True)
    print('Gestão adicional: http://127.0.0.1:'+str(args.porta)+'/gestao',flush=True)
    uvicorn.run('pontocerto.management.app:create_app',factory=True,host='127.0.0.1',port=args.porta)
