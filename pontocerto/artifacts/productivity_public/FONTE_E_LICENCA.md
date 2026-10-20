# Fonte e atribuição dos dados públicos

Productivity Prediction of Garment Employees [Dataset]. (2020). UCI Machine Learning Repository. https://doi.org/10.24432/C51S6D

Fonte primária: https://archive.ics.uci.edu/dataset/597/productivity . Arquivo baixado do link oficial UCI em 20/10/2026.

Licença declarada pela UCI: **Creative Commons Attribution 4.0 International (CC BY 4.0)**. Texto: https://creativecommons.org/licenses/by/4.0/ . Ao reutilizar/distribuir dados e resultados derivados, manter atribuição, link à licença e indicar transformações.

`source.zip` e `garments_worker_productivity.csv` são os dados originais obtidos da fonte. O CSV não foi alterado. O pipeline normaliza espaços/capitalização de departamento, cria dia da semana a partir da data e transforma código de equipe em categoria. Mantém a grafia `sweing` da fonte. Não remove nem trunca os 37 alvos acima de 1 encontrados. Não foram encontradas linhas duplicadas exatas.

`splits.csv` identifica linha original e conjunto temporal. `productivity.joblib` é derivado treinado, `metadata.json` registra hashes, versões, atributos, protocolo e métricas. Não representa treinamento financeiro, previsão de atraso de lote ou validação na Duas Marias.
