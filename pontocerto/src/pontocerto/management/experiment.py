"""PoC reproduzível de atraso e ritmo futuro em dados exclusivamente sintéticos."""
import csv
import hashlib
import json
from pathlib import Path
from .domain import FEATURES, now

VERSION = 'delay-synthetic-v1'
NOTICE = 'Experimento sintético: não validado na Duas Marias. Não automatiza decisões.'


def train(destination: Path, count=2400, seed=42):
    import joblib
    import numpy as np
    import sklearn
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (precision_score, recall_score, f1_score, confusion_matrix,
                                 average_precision_score, brier_score_loss, mean_absolute_error)
    rng = np.random.default_rng(seed)
    capacity = rng.uniform(50, 600, count)
    days = rng.integers(1, 31, count)
    remaining = rng.integers(50, 8001, count)
    rework = rng.uniform(0, .3, count)
    recent = capacity*rng.uniform(.35, 1.1, count)*(1-rework)
    # Choques futuros não observados entram SOMENTE no alvo.
    future = np.minimum(capacity, recent)*rng.lognormal(-.03, .20, count)*(1-rework*.4)
    labels = (future*days < remaining).astype(int)
    x = np.column_stack([remaining, days, capacity, recent, rework])
    ids = np.arange(count)
    tr, rest = train_test_split(ids, test_size=.3, random_state=seed, stratify=labels)
    va, te = train_test_split(rest, test_size=.5, random_state=seed+1, stratify=labels[rest])
    classifier = RandomForestClassifier(n_estimators=120, max_depth=9, min_samples_leaf=8,
                                        random_state=seed, n_jobs=1, class_weight='balanced')
    regressor = RandomForestRegressor(n_estimators=120, max_depth=9, min_samples_leaf=8,
                                      random_state=seed, n_jobs=1)
    logistic = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=seed))
    classifier.fit(x[tr], labels[tr])
    regressor.fit(x[tr], future[tr])
    logistic.fit(x[tr], labels[tr])
    def classification(y, prediction, scores=None):
        report = {'precision': float(precision_score(y,prediction,zero_division=0)),
                  'recall': float(recall_score(y,prediction,zero_division=0)),
                  'f1': float(f1_score(y,prediction,zero_division=0)),
                  'confusionMatrix': confusion_matrix(y,prediction,labels=[0,1]).tolist(),
                  'classOrder': ['no_delay','delay']}
        if scores is not None:
            report['prAucAveragePrecision'] = float(average_precision_score(y,scores))
            report['brierScore'] = float(brier_score_loss(y,scores))
        return report
    def evaluate(indices):
        probability = classifier.predict_proba(x[indices])[:,1]
        deterministic = (np.minimum(recent[indices],capacity[indices])*days[indices]<remaining[indices]).astype(int)
        return {'support': len(indices), 'lateCount': int(labels[indices].sum()),
                'randomForest': classification(labels[indices], probability>=.5, probability),
                'logisticRegression': classification(labels[indices],logistic.predict(x[indices]),logistic.predict_proba(x[indices])[:,1]),
                'capacityBaseline': classification(labels[indices], deterministic),
                'productionMAE': float(mean_absolute_error(future[indices],regressor.predict(x[indices]))),
                'productionBaselineMAE': float(mean_absolute_error(future[indices],np.minimum(recent[indices],capacity[indices])))}
    destination.mkdir(parents=True, exist_ok=True)
    splits = {int(i): split for split, group in [('train',tr),('validation',va),('test',te)] for i in group}
    dataset = destination/'dataset.csv'
    with dataset.open('w',newline='',encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['lotId',*FEATURES,'futureRate_TARGET_ONLY','late_TARGET_ONLY','split'])
        for i in ids:
            writer.writerow([int(i),*x[i].tolist(),float(future[i]),int(labels[i]),splits[int(i)]])
    artifact = destination/'model.joblib'
    joblib.dump({'classifier': classifier, 'regressor': regressor, 'version': VERSION,
                 'features': FEATURES, 'sklearnVersion': sklearn.__version__},artifact)
    metadata = {'version': VERSION, 'executionMode': 'model', 'trainingDataOrigin': 'synthetic',
                'generatedAt': now(), 'seed': seed, 'generatorVersion': 'v1', 'count': count,
                'features': FEATURES, 'trainCount': len(tr), 'validation': evaluate(va), 'test': evaluate(te),
                'sklearnVersion': sklearn.__version__, 'numpyVersion': np.__version__,
                'datasetSha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
                'modelSha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'parameters': classifier.get_params(), 'regressorParameters': regressor.get_params(),
                'notice': NOTICE, 'calibrated': False,
                'protocol': 'Um snapshot por lote independente; 70/15/15 estratificado; teste não usado no ajuste; limiar fixo 0.5.',
                'limitation': 'O modelo aprende hipóteses do gerador. Brier é reportado, mas não houve calibração nem validação operacional.'}
    (destination/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return metadata


class DelayModel:
    def __init__(self, directory: Path):
        self.directory = directory
        self.artifact = None
        self.error = None
        self.metadata = None

    def status(self):
        if not (self.directory/'metadata.json').exists() or not (self.directory/'model.joblib').exists():
            return {'available': False, 'error': 'Execute scripts/06_treinar_gestao.py.', 'notice': NOTICE}
        if self.metadata is None:
            try:
                self.metadata = json.loads((self.directory/'metadata.json').read_text(encoding='utf-8'))
            except (ValueError,OSError):
                return {'available': False, 'error': 'Metadados inválidos; execute novamente o treino.', 'notice': NOTICE}
        return {'available': self.error is None, 'error': self.error, 'metadata': self.metadata, 'notice': NOTICE}

    def predict(self, row):
        import sklearn
        import joblib
        status = self.status()
        if not status['available']:
            raise ValueError(status['error'])
        if self.artifact is None:
            meta = self.metadata
            if meta['sklearnVersion'] != sklearn.__version__:
                raise ValueError('Versão do scikit-learn diferente do treino. Retreine neste ambiente.')
            artifact = self.directory/'model.joblib'
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != meta['modelSha256']:
                raise ValueError('Hash do modelo divergente. Retreine antes de usar.')
            # Apenas artefato local produzido pelo script do projeto; nunca aceita upload de pickle.
            self.artifact = joblib.load(artifact)
            if self.artifact['features'] != FEATURES:
                raise ValueError('Contrato de atributos incompatível.')
        return {'riskScore': float(self.artifact['classifier'].predict_proba([row])[0,1]),
                'futureRate': float(self.artifact['regressor'].predict([row])[0])}
