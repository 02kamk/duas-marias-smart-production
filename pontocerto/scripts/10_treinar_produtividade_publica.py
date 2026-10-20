from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pontocerto.business.productivity import train
if __name__=='__main__':
    result=train(Path(__file__).resolve().parents[1]/'artifacts'/'productivity_public')
    print('Modelo selecionado na validacao:',result['selectedModel'])
    print('MAE no teste temporal:',result['test'][result['selectedModel']]['mae'])
    print(result['notice'])
