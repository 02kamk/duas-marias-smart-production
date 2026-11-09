# Continuidade e fontes de dados

Verificação documental em 19/10/2026. Não houve download, inventário de imagens, treinamento ou nova avaliação. Informações abaixo descrevem páginas dos autores; contagens e licenças dos arquivos efetivamente obtidos continuam sujeitas à conferência.

## Sequência sugerida

1. Demonstrar o frontend à beneficiária; confirmar produção boa, retrabalho, conclusão, calendário, turnos e critérios acadêmicos. Recuperar requisitos originais antes de formalizar RF/RNF.
2. Implementar API FastAPI, SQLAlchemy, Alembic e PostgreSQL: começar por lotes e operações, depois registros e inspeções. Testar integridade, autorização, correções auditadas e persistência. Manter adaptadores e procedência explícitos.
3. Estruturar coleta autorizada de imagens e registros locais. Campos: lote, operação, instante com fuso, câmera/sessão/peça, tecido, iluminação, rótulo revisado e procedência. Separar treino/teste por peça ou sessão para evitar vazamento.
4. Auditar o Ponto Certo: versões, hash dos pesos, configuração, dados usados, partições, duplicatas e métricas. O split atual descrito estratifica por tecido/classe, mas isso não garante separação por peça/sessão. Reexecutar avaliação independente antes de integrar a inferência.
5. Investigar atraso por baseline operacional (necessidade diária versus capacidade); só depois regressão logística/Random Forest com sintéticos documentados. Semente, gerador, snapshots e split por lote devem ser versionados; não usar conclusão futura como entrada.
6. Implementar balanceamento por heurística: restrições de habilidade/disponibilidade antes do score. Expor componentes e pesos; registrar decisão humana. Não usar ranking punitivo de pessoas.

## Datasets candidatos

### StitchingNet — classificação, candidato principal

Fonte primária: https://github.com/hyungjungkim/StitchingNet . Corrige o endereço candidato terminado em `StitchingNet-dataset` do contexto.

O README dos autores informa 14.565 imagens de costura de 224×224, onze tecidos, normais e dez tipos de defeito. Aponta artigo de Jung et al. (2025), DOI https://doi.org/10.1093/jcde/qwaf037, downloads Kaggle/Mendeley e licença CC BY-NC 4.0. É o candidato mais próximo da taxonomia atual do Ponto Certo; essa correspondência ainda requer inventário dos arquivos. A restrição não comercial precisa ser resolvida antes de uso empresarial. Não confundir classificação da região com localização de defeito.

### StitchingNet-Seg — evolução para segmentação

Fonte primária: https://github.com/hyungjungkim/StitchingNet-Seg . O README informa imagens derivadas do StitchingNet, máscaras e COCO, licença CC BY 4.0 e classes diferentes da base original. Verificar licença no arquivo distribuído, cadeia de derivação e atribuição; não assumir que a licença desta versão altera a do conjunto original. Não misturar derivados e originais entre treino e teste. Reservar para etapa posterior que exija localização, com protocolo e modelo próprios.

### MVTec AD — comparação exploratória

Fonte primária: https://www.mvtec.com/research-teaching/datasets/mvtec-ad . Conjunto de inspeção industrial e texturas; útil para estudar anomalias, sem substituir exemplos de costura. A página informa CC BY-NC-SA 4.0 e restrição a uso comercial. Não transferir desempenho desse domínio para a Duas Marias.

### Dados de prazo e capacidade

Nenhuma base operacional representativa da Duas Marias foi verificada nesta entrega. Usar fixtures somente na interface, sintéticos somente em PoC e registros reais autorizados para futura avaliação local. Uma imagem de defeito não fornece alvo de atraso de lote.

## Antes de usar qualquer conjunto

Registrar fonte/versão/data, licença dos arquivos e imagens, autores/atribuição, checksums, contagens e distribuição, normais, duplicatas, grupos de peça/sessão e partições. Separar transformações de treino e teste. Avaliar baseline, macro-F1/recall por classe, matriz de confusão e erros. Preservar conjunto local independente para medir mudança de domínio. Sem essa etapa, não há evidência de desempenho na empresa.
