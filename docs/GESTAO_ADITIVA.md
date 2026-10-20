# Gestão adicional do Ponto Certo — 20/10/2026

## Preservação do trabalho original

Nenhum arquivo já versionado do Ponto Certo foi editado. Os scripts 00–05, CNN, pesos, config.yaml, HTML/CSS/JS originais e todas as rotas de inspeção/câmera/foto permanecem intactos. O frontend demonstrativo anterior também foi preservado.

O novo script 07 chama a fábrica original da aplicação e acrescenta rotas de gestão e um link de acesso na resposta HTML da raiz, em tempo de execução. Não modifica o HTML salvo. Câmera ao vivo, captura de fotos, análise de arquivo, histórico, treinamento, relatórios, ajustes e opções de dispositivos continuam usando o código original. A câmera continua desligada até a ação do operador.

## Executar no VS Code

Na pasta `pontocerto`, encerre somente a instância que você está usando do servidor antigo com Ctrl+C. Inicie a versão estendida:

```powershell
C:\Users\kamil\Documents\Codex\venvs\pc\Scripts\python.exe -u scripts\07_rodar_com_gestao.py
```

Ou use o atalho novo no PowerShell:

```powershell
.\Iniciar-Gestao.ps1
```

Se a política do PowerShell impedir o atalho, use o comando Python acima; não é necessário alterar a política. Abra http://127.0.0.1:8000 para inspeção ou http://127.0.0.1:8000/gestao para gestão. Deixe o terminal aberto. Se quiser manter o servidor antigo rodando, passe `--porta 8001` ao script Python, ou `-Porta 8001` ao atalho.

O novo HTML já foi compilado e incluído. Não precisa rodar npm para usar a gestão pelo Python. O script 05 continua iniciando exclusivamente o sistema antigo, como antes. Nenhuma opção de câmera foi removida ou redesenhada.

## Telas e fluxos adicionados

- Resumo: lotes ativos, produção boa/retrabalho do dia e ritmo informado versus capacidade planejada. Não chama esse indicador de eficiência operacional.
- Lotes: cadastro, busca, filtro de status/prazo, saldo e acesso ao planejamento.
- Produção: apontamento por lote, colaborador, operação e data; boas e retrabalho separados; histórico com filtros. Só Revisão final aumenta peças concluídas.
- Atrasos e capacidade: saldo, dias corridos, necessidade diária, regra de capacidade, inferência experimental e estimativa de ritmo futuro; replanejamento com motivo e registro do antes/depois.
- Balanceamento: restrições de habilitação e disponibilidade, score explicável, aceitação/rejeição humana, reserva de minutos por data e consulta das alocações.
- Colaboradores: consulta de referências e habilidades fictícias por operação.
- Modelo e evidências: versões, origem, contagens e métricas sintéticas, comparadas aos baselines.
- Auditoria: ações locais da demonstração com instante e motivo.

Todos os novos dados operacionais são fictícios, inclusive cadastros digitados nesta extensão. Não há entrada de dados reais nem alegação de autenticação. Registros iniciais representam saldos anteriores; o resumo do dia usa apenas apontamentos da Revisão final na data atual do servidor local. O relógio da gestão é separado da fixture fixa do frontend anterior.

Replanejamento usa ritmo recente e retrabalho **informados como premissas**. Não recalcula taxa por um único apontamento sem tempo produtivo, evitando inventar produtividade. Prazos são dias corridos; o dia-base não conta como dia futuro; feriados e turnos não foram modelados. Lotes concluídos ou com prazo atingido não recebem inferência futura.

## Modelos novos e independentes

A CNN original não foi retreinada. O novo experimento usa:

1. RandomForestClassifier para score de atraso (120 árvores, profundidade 9, folhas com mínimo de 8 exemplos).
2. RandomForestRegressor para ritmo futuro em peças boas/dia.
3. Regressão logística e regra determinística de capacidade para comparação.

Implementação baseada na documentação primária do [Random Forest do scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html) e nas orientações de [separação de treino e teste](https://scikit-learn.org/stable/modules/cross_validation.html).

Os scores não foram calibrados e não representam probabilidades validadas na empresa. O módulo orienta revisão humana; não altera prazo, produção ou alocação automaticamente. Fatores exibidos são da regra de capacidade, não explicações causais da Random Forest. Balanceamento é heurística, não ML nem otimização global.

## Dados sintéticos e protocolo

Gerador v1, semente 42, 2.400 lotes independentes, um snapshot por lote:

| Campo | Unidade / geração |
|---|---|
| remaining | peças inteiras uniformes de 50 a 8.000 |
| days | dias inteiros uniformes de 1 a 30 |
| capacityPerDay | peças/dia uniformes de 50 a 600 |
| reworkRate | fração uniforme de 0 a 0,30 |
| recentRate | capacidade × uniforme(0,35; 1,10) × (1 − retrabalho) |
| futureRate_TARGET_ONLY | mínimo(capacidade, ritmo recente) × choque lognormal(-0,03; 0,20) × (1 − retrabalho × 0,4) |
| late_TARGET_ONLY | ritmo futuro × dias < saldo |

Os campos futuros entram apenas no alvo e no CSV de evidências; não entram nos atributos. Não há snapshots repetidos, peças reais ou pessoas reais no gerador. Divisão por ID de lote: 1.680 treino, 360 validação, 360 teste, estratificada com sementes 42/43. StandardScaler ajustado só no treino para a regressão logística. RF tem parâmetros fixados, limiar 0,5; não foi escolhida pelo resultado de teste. Essa partição é sintética e não substitui um protocolo temporal futuro com dados reais.

O alvo nasce das hipóteses do gerador. Logo, bom desempenho pode apenas refletir aprendizado dessas hipóteses. A avaliação não comprova redução de atrasos ou ganho de produtividade na Duas Marias. Não houve treinamento com dados públicos operacionais ou da empresa. StitchingNet e imagens de costura não foram usados neste experimento de atraso.

## Resultados efetivamente executados

Treino em 20/10/2026, scikit-learn 1.9.1, numpy 2.5.4. Teste sintético independente de 360 lotes, 239 atrasados:

| Método | F1 atraso | Observação |
|---|---:|---|
| Random Forest | 0,9507 | score não calibrado |
| Regressão logística | 0,9351 | baseline estatístico |
| Regra de capacidade | 0,9567 | melhor F1 entre os três neste teste |

Para ritmo futuro, erro absoluto médio: RF 31,55 peças/dia, baseline 34,57 peças/dia. A Random Forest de atraso **não superou** a regra de capacidade neste experimento. A interface mantém os dois resultados separados; não recomenda trocar a regra por ML com base nesses números.

Precisão, recall, matriz de confusão, PR-AUC por average precision, Brier score e validação estão em `pontocerto/artifacts/gestao_ml/metadata.json`. Dataset, partições e hashes também estão preservados; o artefato contém os dois modelos. Desempenho sob gerador alternativo, calibração, validação temporal e validação local continuam pendentes.

## Reproduzir e verificar

Na pasta pontocerto, usando o mesmo ambiente:

```powershell
C:\Users\kamil\Documents\Codex\venvs\pc\Scripts\python.exe scripts\06_treinar_gestao.py
C:\Users\kamil\Documents\Codex\venvs\pc\Scripts\python.exe scripts\08_testar_gestao.py
```

O treino só escreve em `artifacts/gestao_ml`. Não usa nem altera `artifacts/modelo.pt`. Para preservar uma execução anterior, passe `--saida` com outra pasta no script 06; o servidor usa o diretório padrão. Retreine e reinicie o servidor se mudar a versão do scikit-learn. Nunca carregue modelos pickle/joblib recebidos de terceiros.

Frontend, a partir da pasta frontend:

```powershell
npm.cmd ci
npx.cmd tsc --noEmit
npm.cmd test
npx.cmd vite build --config vite.gestao.config.ts
```

Não use `npm run build` para gerar a extensão: esse comando continua gerando o frontend anterior. A configuração adicional gera somente o novo bundle em `pontocerto/src/pontocerto/management/static`. Fontes React/TypeScript ficam em `frontend/src/management`.

## Persistência e limites de escopo

`artifacts/gestao_demo/state.json` guarda **apenas a demonstração**, com gravação atômica, lock de processo e log local de ações. Esse arquivo não é versionado. Não foi introduzido SQLite nem alterada a decisão de PostgreSQL/SQLAlchemy/Alembic: eles continuam como próxima fase operacional. JSON não substitui essa arquitetura. Execute uma instância da gestão por arquivo; não há coordenação entre processos, autenticação, permissões por perfil, backup operacional ou auditoria com identidade verificada.

Cadastro de clientes/modelos é textual e demonstrativo; colaboradores e operações são catálogo fictício, ainda sem CRUD completo. Apontamentos não têm correção auditada nem calendário de turnos. Inspeções antigas não foram vinculadas automaticamente a lotes, pois isso mudaria o fluxo original. Todos os recursos de câmera/foto continuam na inspeção, com acesso direto na gestão. Não houve nova validação da CNN ou captura de câmera nesta entrega.

Próxima fase: contratos persistentes de lotes/operações/produção e inspeções no PostgreSQL, autenticação real, autorização por recurso, coleta aprovada, vínculos auditados e avaliação local independente. Não considerar esta extensão um MVP operacional completo.
