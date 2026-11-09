"""Treina SOMENTE os novos modelos sintéticos, sem tocar na CNN ou nas imagens."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pontocerto.management.experiment import train

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--saida',type=Path,default=Path(__file__).resolve().parents[1]/'artifacts'/'gestao_ml')
    args=parser.parse_args()
    result=train(args.saida)
    print('Treino sintético concluído:',args.saida)
    print('F1 no teste sintético:',result['test']['randomForest']['f1'])
    print(result['notice'])
