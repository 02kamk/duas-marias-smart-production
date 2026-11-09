"""Experimento UCI 597: produtividade de equipes, sem inferir atraso ou peças/dia."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
import urllib.request
import zipfile

URL='https://archive.ics.uci.edu/static/public/597/productivity+prediction+of+garment+employees.zip'
SOURCE='https://archive.ics.uci.edu/dataset/597/productivity'
VERSION='uci597-pre-shift-v1'
NUMERIC=['no_of_workers','no_of_style_change','targeted_productivity','smv','weekday']
CATEGORICAL=['department','team']
FEATURES=NUMERIC+CATEGORICAL
EXCLUDED=['actual_productivity','over_time','incentive','idle_time','idle_men','wip','quarter','day','date']
NOTICE='Modelo experimental em dados públicos de outra indústria; não validado na Duas Marias. Não prevê peças/dia ou atraso.'


def prepare(frame):
    frame=frame.copy()
    frame['department']=frame['department'].astype(str).str.strip().str.lower()
    frame['team']=frame['team'].astype(str)
    frame['weekday']=frame['date'].dt.dayofweek
    return frame


def train(directory:Path,download=True):
    import joblib
    import numpy as np
    import pandas as pd
    import sklearn
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder,StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.dummy import DummyRegressor
    from sklearn.metrics import mean_absolute_error,mean_squared_error,r2_score
    directory.mkdir(parents=True,exist_ok=True)
    raw=directory/'garments_worker_productivity.csv'
    archive=directory/'source.zip'
    if not raw.exists():
        if not download:
            raise ValueError('CSV público ausente. Execute o script com acesso à UCI.')
        with urllib.request.urlopen(URL,timeout=180) as response:
            archive.write_bytes(response.read(2_000_000))
        with zipfile.ZipFile(archive) as z:
            names=[n for n in z.namelist() if n.endswith('garments_worker_productivity.csv')]
            if len(names)!=1:
                raise ValueError('Arquivo oficial inesperado; confira manualmente a fonte.')
            raw.write_bytes(z.read(names[0]))
    df=pd.read_csv(raw)
    original_count=len(df)
    duplicates=int(df.duplicated().sum())
    df=df.drop_duplicates().copy()
    df['sourceRow']=df.index+2
    df['date']=pd.to_datetime(df['date'],format='%m/%d/%Y',errors='raise')
    df=prepare(df).sort_values(['date','sourceRow'])
    if not np.isfinite(df['actual_productivity']).all():
        raise ValueError('Alvos ausentes/não finitos; revisar a origem.')
    dates=sorted(df['date'].unique())
    train_end,validation_end=int(len(dates)*.70),int(len(dates)*.85)
    parts={'train':df[df['date'].isin(dates[:train_end])],
           'validation':df[df['date'].isin(dates[train_end:validation_end])],
           'test':df[df['date'].isin(dates[validation_end:])]}
    def preprocessor():
        return ColumnTransformer([
            ('numeric',Pipeline([('impute',SimpleImputer(strategy='median')),('scale',StandardScaler())]),NUMERIC),
            ('category',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CATEGORICAL)])
    candidates={
        'baseline_median':Pipeline([('prep',preprocessor()),('model',DummyRegressor(strategy='median'))]),
        'ridge':Pipeline([('prep',preprocessor()),('model',Ridge(alpha=10))]),
        'random_forest':Pipeline([('prep',preprocessor()),('model',RandomForestRegressor(n_estimators=160,max_depth=8,min_samples_leaf=8,random_state=42,n_jobs=1))])}
    def scores(model,part):
        y=part['actual_productivity']
        predicted=model.predict(part[FEATURES])
        return {'mae':float(mean_absolute_error(y,predicted)),
                'rmse':float(np.sqrt(mean_squared_error(y,predicted))), 'r2':float(r2_score(y,predicted))}
    validation={}
    for name,model in candidates.items():
        model.fit(parts['train'][FEATURES],parts['train']['actual_productivity'])
        validation[name]=scores(model,parts['validation'])
    selected=min(validation,key=lambda n:validation[n]['mae'])
    # Escolha só na validação; teste futuro permanece intocado até esta etapa.
    test={name:scores(model,parts['test']) for name,model in candidates.items()}
    artifact=directory/'productivity.joblib'
    joblib.dump({'pipeline':candidates[selected],'features':FEATURES,'version':VERSION},artifact)
    membership={}
    for name,part in parts.items():
        for i in part.index:
            membership[i]=name
    manifest=df[['sourceRow','date','team']].copy()
    manifest['split']=[membership[i] for i in manifest.index]
    manifest.to_csv(directory/'splits.csv',index=False)
    metadata={'version':VERSION,'generatedAt':datetime.now(timezone.utc).isoformat(),
        'source':SOURCE,'downloadUrl':URL,'doi':'10.24432/C51S6D','license':'CC BY 4.0',
        'attribution':'Productivity Prediction of Garment Employees [Dataset]. (2020). UCI Machine Learning Repository. https://doi.org/10.24432/C51S6D',
        'dataOrigin':'public','executionMode':'model','originalRows':original_count,'duplicatesRemoved':duplicates,
        'features':FEATURES,'excludedColumns':EXCLUDED,'selectedModel':selected,'selection':'Menor MAE na validação temporal; sem ajuste no teste.',
        'validation':validation,'test':test,'seed':42,'sklearnVersion':sklearn.__version__,
        'numpyVersion':np.__version__,'pandasVersion':pd.__version__,
        'datasetSha256':hashlib.sha256(raw.read_bytes()).hexdigest(),
        'modelSha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'notice':NOTICE,'targetRange':[float(df.actual_productivity.min()),float(df.actual_productivity.max())],
        'outOfUnitRangeTargets':int(((df.actual_productivity<0)|(df.actual_productivity>1)).sum()),
        'partitions':{name:{'rows':len(part),'firstDate':part.date.min().date().isoformat(),
                           'lastDate':part.date.max().date().isoformat()} for name,part in parts.items()},
        'numericRanges':{n:[float(df[n].min()),float(df[n].max())] for n in NUMERIC},
        'categories':{n:sorted(df[n].unique().tolist()) for n in CATEGORICAL},
        'assumption':'Equipe, efetivo, mudanças de estilo, meta e SMV precisam ser conhecidos antes do turno. Excluídos campos realizados/timing incerto. A disponibilidade real deve ser confirmada.',
        'limitations':['Índice não é peças/dia nem atraso de lote.','Mesmas equipes reaparecem em datas futuras; não mede transferência para equipe/fábrica nova.',
                       'Sem intervenção causal ou avaliação de trabalhadores individuais.','Alvos fora de 0–1 são preservados e reportados, sem truncamento silencioso.']}
    (directory/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return metadata


class PublicProductivity:
    def __init__(self,directory:Path):
        self.directory=directory
        self.model=None

    def status(self):
        try:
            metadata=json.loads((self.directory/'metadata.json').read_text(encoding='utf-8'))
            return {'available':(self.directory/'productivity.joblib').exists(),'metadata':metadata,'notice':NOTICE}
        except (OSError,ValueError):
            return {'available':False,'notice':NOTICE,'error':'Execute scripts/10_treinar_produtividade_publica.py.'}

    def predict(self,body):
        import joblib
        import pandas as pd
        import sklearn
        from datetime import date
        status=self.status()
        if not status['available']:
            raise ValueError(status.get('error','Artefato indisponível.'))
        meta=status['metadata']
        if meta['sklearnVersion']!=sklearn.__version__:
            raise ValueError('Scikit-learn diferente do treino; retreine o modelo público.')
        if body['department'] not in meta['categories']['department'] or str(body['team']) not in meta['categories']['team']:
            raise ValueError('Equipe/departamento fora da base pública; não é uma previsão validada para a empresa.')
        row={**body,'weekday':date.fromisoformat(body['date']).weekday(),'team':str(body['team'])}
        for key in NUMERIC:
            lo,hi=meta['numericRanges'][key]
            if not lo<=row[key]<=hi:
                raise ValueError(f'{key} fora do intervalo observado [{lo}, {hi}].')
        if self.model is None:
            artifact=self.directory/'productivity.joblib'
            if hashlib.sha256(artifact.read_bytes()).hexdigest()!=meta['modelSha256']:
                raise ValueError('Hash do modelo divergente; retreine antes de usar.')
            self.model=joblib.load(artifact)
        value=float(self.model['pipeline'].predict(pd.DataFrame([row])[FEATURES])[0])
        return {'value':value,'unit':'índice de produtividade da base UCI, sem conversão para peças',
                'executionMode':'model','trainingDataOrigin':'public','inputDataOrigin':'scenario',
                'modelVersion':meta['version'],'algorithm':meta['selectedModel'],
                'generatedAt':datetime.now(timezone.utc).isoformat(),'notice':NOTICE}
