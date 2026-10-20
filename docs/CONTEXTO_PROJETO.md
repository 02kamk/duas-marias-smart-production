# Duas Marias Smart Production — Contexto do projeto

Documento de referência para continuidade do desenvolvimento no Codex. Versão: 19/10/2026. Idioma do produto e da documentação: português brasileiro.

## 1. Origem, confiabilidade e estado do projeto

Este documento consolida o pedido atual e os trechos recuperáveis da conversa **IA para fábrica de roupas**, identificador `6a711722-3710-83e9-a6b5-e3808dcc1c9d`. O histórico recuperado contém propostas de protótipo, apresentação acadêmica, módulos inteligentes e fontes de dados. Algumas respostas antigas aparecem apenas como referências de conteúdo, sem texto recuperável.

**Limite de rastreabilidade:** a redação original dos requisitos RF01–RF40 e RNF01–RNF20 não está disponível no histórico recuperado. As listas deste documento são uma **especificação consolidada proposta, reconstruída a partir do escopo acessível e do pedido atual**, pendente de confronto com o documento acadêmico original. Não representam transcrição nem aprovação formal de requisitos anteriores. Os contratos de API, detalhes de entidades, critérios e regras operacionais abaixo também são propostas técnicas quando não explicitamente definidos na conversa.

O histórico descreve intenções e entregas desejadas; não comprova que código, banco, treinamento ou avaliação já foram executados. Não há evidência recuperada de modelo treinado, modelo validado, métricas experimentais, dataset baixado ou sistema implantado.

### Vocabulário obrigatório

| Situação | Significado | O que permite afirmar |
|---|---|---|
| Demonstração mock | Valores fictícios fixos ou respostas simuladas para navegar pelas telas | Demonstra o fluxo e a interface; não analisa de fato a produção ou imagem |
| Dados sintéticos | Registros gerados por regras documentadas para experimentos | Permitem testar o pipeline e comportamento sob hipóteses; não comprovam desempenho na empresa |
| Dataset público | Dados de terceiros, sujeitos à verificação de origem, licença e adequação | Pode apoiar experimentos após verificação; não representa automaticamente a Duas Marias |
| Dados reais | Registros e imagens coletados na empresa com autorização e rastreabilidade | Podem subsidiar avaliação local após análise de qualidade e protocolo experimental |
| Modelo treinado | Artefato produzido por execução documentada de treinamento | Só declarar quando houver artefato, configuração, origem de dados e registro da execução |
| Modelo validado | Modelo avaliado em conjunto independente segundo protocolo e métricas | Informar em qual população e cenário foi avaliado; teste público ou sintético não é validação na empresa |

## 2. Beneficiária, problema e objetivos

**Beneficiária:** Duas Marias Confecções Ltda., descrita na conversa como uma facção de costura. Localização, porte, responsáveis, quantidade de colaboradores e processos exatos não foram confirmados. Não inventar esses dados.

Problemas relatados no planejamento: acompanhamento manual da produção, dificuldade para antecipar atrasos, distribuição de operações apoiada na experiência, inspeção visual manual e ausência de histórico estruturado suficiente para treinar modelos específicos. Essas descrições são hipóteses de diagnóstico a confirmar com a empresa, não resultados de auditoria.

**Objetivo geral:** desenvolver um sistema de gestão da produção que estruture os dados operacionais e apoie decisões sobre prazo, distribuição do trabalho e qualidade, com módulos inteligentes introduzidos de forma gradual e verificável.

Objetivos específicos:

- Acompanhar lotes, prazos, operações e progresso produtivo.
- Registrar produção, retrabalho e inspeções com vínculo ao lote e à operação.
- Apresentar indicadores compreensíveis e rastreáveis.
- Demonstrar previsão de atraso inicialmente com mock e, em etapa experimental, dados sintéticos.
- Recomendar alocações por score explicável, respeitando disponibilidade e habilitação.
- Investigar classificação de defeitos de costura em imagens usando base pública verificável.
- Iniciar a coleta estruturada de dados reais para evolução e avaliação futura.
- Entregar evidências acadêmicas honestas sobre resultados, limitações e trabalhos futuros.

O sistema apoia a decisão humana. Recomendações não devem determinar automaticamente punição, remuneração ou avaliação individual de colaboradores.

## 3. Escopo, prioridades e marcos

### Marco imediato — protótipo frontend

Aplicação funcional e navegável com React, TypeScript, Vite, Tailwind, React Router, Recharts e Lucide React. Sem backend real, banco real ou treinamento nesta primeira entrega. Mock separado dos componentes, avisos visíveis e serviços substituíveis por API.

Prioridade inicial: Login → Dashboard → Lotes → Detalhe do lote → Qualidade. Completar Produção, Colaboradores, Operações, Inteligência IA e Configurações com fluxos coerentes. Cadastro e edições em memória podem demonstrar interação, com aviso de que os dados podem ser reiniciados.

### MVP acadêmico do semestre — meta planejada

O semestre e seu prazo final não foram especificados; confirmar calendário com a autora e o professor. O escopo desejado inclui protótipo web, cadastro/acompanhamento de lotes, dashboard, registro de produção, qualidade e estrutura de coleta real. Backend e persistência entram após o frontend. A prova de conceito de atraso sintético e o experimento de visão computacional são metas condicionadas a tempo, acesso aos dados e recursos.

| Prioridade proposta | Entregas | Dependências |
|---|---|---|
| P0 — base demonstrável | Frontend navegável, dados coerentes, avisos MOCK, documentação e execução reproduzível | Ambiente frontend |
| P1 — MVP operacional | API, banco, validações, lotes, produção, inspeção manual, autenticação real | Regras confirmadas e ambiente backend |
| P1 — IA acadêmica principal | Verificar dataset e executar experimento inicial de visão computacional, se viável | Licença, acesso, classes, capacidade computacional e protocolo |
| P2 — IA complementar | PoC de atraso sintético e score de balanceamento | Gerador documentado e regras aprovadas |
| P3 — evolução | Dataset próprio, avaliação local, fine-tuning, segmentação, implantação | Dados reais e validação |

A conversa priorizou visão computacional como IA principal, previsão de atraso como PoC complementar e balanceamento por score. Isso não elimina o risco de dados: encontrar um link não comprova acesso, licença adequada ou compatibilidade.

Não comprometer a entrega básica para simular treinamento inexistente. Se o experimento não for concluído, entregar o módulo mock com limitação explícita e registrar o trabalho pendente.

## 4. Requisitos funcionais — proposta consolidada

Legenda de fase: **F0** protótipo mock; **F1** MVP com API; **F2** experimento acadêmico; **F3** evolução com dados reais. Um requisito F0 pode evoluir em F1, sem que sua simulação conte como implementação real.

| ID | Requisito proposto | Fase inicial |
|---|---|---|
| RF01 | Disponibilizar entrada e saída da aplicação, com login demonstrativo identificado no protótipo | F0 |
| RF02 | Autenticar usuários reais e autorizar ações por perfil: administração, gestão, produção e qualidade, a confirmar | F1 |
| RF03 | Exibir dashboard com produção, meta, atingimento, lotes em andamento, risco e retrabalho | F0 |
| RF04 | Exibir série de produção dos últimos sete dias e distribuição de lotes por status | F0 |
| RF05 | Listar lotes que precisam de atenção com motivo e origem do indicador | F0 |
| RF06 | Listar lotes com busca, filtros por status/prazo e acesso ao detalhe | F0 |
| RF07 | Cadastrar lote com código único, cliente, modelo, quantidade e prazo | F1 |
| RF08 | Editar dados de lote com validação e rastreabilidade | F1 |
| RF09 | Controlar status e transições do lote, preservando histórico e evitando exclusão de registros usados | F1 |
| RF10 | Exibir detalhe com quantidade, produção, progresso, prazo e operações | F0 |
| RF11 | Cadastrar clientes e vinculá-los aos lotes, limitando dados pessoais ao necessário | F1 |
| RF12 | Cadastrar modelos de peças e sua identificação | F1 |
| RF13 | Cadastrar operações e produtividade/tempo de referência com unidade declarada | F1 |
| RF14 | Associar operações ordenadas e metas ao lote | F1 |
| RF15 | Cadastrar colaboradores com função e situação ativa | F1 |
| RF16 | Registrar habilitação, experiência e referências por colaborador e operação | F1 |
| RF17 | Registrar disponibilidade por período e impedir alocação incompatível | F1 |
| RF18 | Registrar produção por colaborador, lote, operação, quantidade e instante/período | F1 |
| RF19 | Registrar retrabalho separadamente da produção boa, sem dupla contagem | F1 |
| RF20 | Consultar e filtrar registros produtivos por data, lote, colaborador e operação | F0 |
| RF21 | Corrigir registros com motivo e trilha de auditoria | F1 |
| RF22 | Consolidar progresso por operação e conclusão do lote sem somar etapas como peças finais | F1 |
| RF23 | Registrar metas e parâmetros operacionais usados nos indicadores | F1 |
| RF24 | Criar inspeção vinculada a lote e, quando possível, operação e registro produtivo | F1 |
| RF25 | Selecionar imagem por arquivo ou arrastar e soltar, com prévia e validação | F0 |
| RF26 | Executar análise visual mock com carregamento e resultado explicitamente demonstrativo | F0 |
| RF27 | Registrar confirmação, rejeição ou correção humana do resultado da inspeção | F0 |
| RF28 | Consultar histórico de inspeções, defeitos e retrabalho com filtros | F1 |
| RF29 | Exibir módulos inteligentes, estado real de desenvolvimento e roadmap | F0 |
| RF30 | Exibir estimativa de atraso por lote com fatores e identificação da origem mock/sintética/real | F0 |
| RF31 | Gerar dataset sintético de atraso com semente, regras, versão e dicionário documentados | F2 |
| RF32 | Treinar e avaliar uma PoC de atraso contra baseline, sem alegar validade operacional | F2 |
| RF33 | Calcular recomendação por score explicável considerando produtividade, qualidade, experiência e disponibilidade | F2 |
| RF34 | Permitir que a gestão aceite ou rejeite sugestão de alocação e registre a decisão | F1 |
| RF35 | Integrar inferência visual real apenas quando houver modelo e contrato verificáveis | F2 |
| RF36 | Registrar versão do modelo, origem dos dados, instante e limites de cada inferência | F2 |
| RF37 | Permitir consulta/exportação autorizada de dados operacionais para análise acadêmica | F1 |
| RF38 | Coletar dados reais com procedência e separação dos ambientes demonstrativos | F1 |
| RF39 | Configurar parâmetros e limiares sem apresentar ajustes mock como calibração estatística | F1 |
| RF40 | Disponibilizar documentação de execução, escopo, limitações, fontes e pontos de integração | F0 |

## 5. Requisitos não funcionais — proposta consolidada

| ID | Requisito proposto e verificação |
|---|---|
| RNF01 | Frontend em React + TypeScript + Vite, com execução documentada por `npm install` e `npm run dev` |
| RNF02 | Interface em Tailwind, navegação React Router, gráficos Recharts e ícones Lucide React |
| RNF03 | Backend planejado em FastAPI, persistência SQLAlchemy, migrações Alembic e PostgreSQL |
| RNF04 | Separar apresentação, domínio, serviços, dados mock e integração; evitar arquivos monolíticos |
| RNF05 | Tipar entidades e contratos; não usar tipos permissivos para contornar incompatibilidades |
| RNF06 | Interface responsiva utilizável em computador e tela pequena, sem sobreposição essencial |
| RNF07 | Campos com rótulos, navegação por teclado e indicadores que não dependam apenas de cor |
| RNF08 | Identidade clara: branco/cinza claro, vinho ou rosa escuro, cards e sombras suaves |
| RNF09 | Tratar carregamento, vazio, erro e sucesso; não produzir erros de console nos fluxos de aceite |
| RNF10 | Manter interações comuns responsivas; medir desempenho antes de fixar metas numéricas de produção |
| RNF11 | Validar dados no cliente e no servidor, impondo restrições e integridade no banco |
| RNF12 | Proteger credenciais reais com hash adequado, sessões seguras e autorização no servidor |
| RNF13 | Aplicar minimização de dados pessoais, acesso restrito e política de retenção definida com a empresa |
| RNF14 | Validar upload por tipo efetivo e tamanho; armazenar arquivos fora de caminhos executáveis |
| RNF15 | Registrar auditoria de alterações e decisões sem expor senhas, tokens ou imagens em logs |
| RNF16 | Usar variáveis de ambiente, exemplo sem segredos e exclusão de credenciais do repositório |
| RNF17 | Versionar esquema, dependências, experimentos e modelos para reprodução |
| RNF18 | Testar regras críticas, permissões, integração e fluxos principais conforme a fase implementada |
| RNF19 | Isolar mock, sintético e real em dados, configuração e apresentação, preservando procedência |
| RNF20 | Documentar backup/restauração e migrações na fase persistente; não prometer disponibilidade sem operação medida |

## 6. Arquitetura e organização

```text
F0: React/TypeScript → serviços mock → fixtures locais

F1+: React/TypeScript → API FastAPI → serviços de domínio → SQLAlchemy → PostgreSQL
                                          ├─ inferência/score versionados
                                          └─ armazenamento protegido de imagens
                              Alembic → migrações do banco
```

Não instalar nem exigir backend para executar o primeiro protótipo. Preparar uma interface de serviço única para trocar os adaptadores sem reescrever páginas.

```text
frontend/
  src/
    components/
    pages/
    layouts/
    data/
    types/
    services/
    utils/
backend/                    # fase posterior
  app/
    api/
    schemas/
    models/
    services/
    repositories/
    core/
  alembic/
experiments/                # apenas quando os experimentos forem iniciados
docs/
  CONTEXTO_PROJETO.md
```

No protótipo isolado, `src/` pode ficar na raiz. Interfaces essenciais: `ProductionOrder`, `Employee`, `ProductionRecord`, `QualityInspection`, `AIPrediction` e `DashboardMetrics`.

Serviços inicialmente previstos: `predictDelayMock()`, `analyzeQualityMock()` e `recommendWorkerMock()` em `services/aiService.ts`. Retornar metadados explícitos, por exemplo `mode: 'mock'`, `dataOrigin: 'mock'`, `modelVersion: null` e `generatedAt`. Não usar nomes ou mensagens que insinuem execução de modelo real.

Separar modo de execução (`mock`, `heuristic`, `model`) da origem dos dados (`mock`, `synthetic`, `public`, `real`). Um modelo treinado com dados sintéticos executa inferência real, mas continua sem validação na empresa.

## 7. Modelo de domínio e relações — proposta

Usar identificadores estáveis, datas de criação/atualização e exclusão lógica quando necessária à integridade. Quantidades em peças inteiras; duração com unidade explícita; timestamps com fuso; prazos diários como data, sem conversão indevida de fuso.

| Entidade | Campos centrais e relações |
|---|---|
| User | id, email, password_hash, role, active; responsável por alterações e inspeções |
| Client | id, name; um cliente possui muitos lotes |
| GarmentModel | id, name, description; um modelo aparece em muitos lotes |
| ProductionOrder | id, code, client_id, model_id, quantity, start_date, due_date, completed_at, status; possui operações, registros e inspeções |
| Operation | id, name, reference_rate, rate_unit; catálogo de operações |
| OrderOperation | id, order_id, operation_id, sequence, target_quantity, status; liga lote e operação e define a etapa |
| Employee | id, display_name, role, active; possui habilidades, disponibilidade e registros |
| EmployeeSkill | employee_id, operation_id, experience_level, reference_productivity, quality_rate, measurement_period; relação muitos-para-muitos |
| Availability | id, employee_id, starts_at, ends_at, available_minutes, reason_category; registrar o mínimo necessário |
| Assignment | id, order_operation_id, employee_id, period, planned_minutes, decision_source; alocação decidida pela gestão |
| ProductionRecord | id, order_operation_id, employee_id, good_quantity, rework_quantity, rejected_quantity, started_at, ended_at, created_by; preservar motivo de correção |
| QualityInspection | id, order_id, order_operation_id opcional, production_record_id opcional, image_id opcional, predicted_label, human_label, decision, inspected_by |
| ImageAsset | id, protected_storage_key, mime_type, size, provenance, consent_reference quando aplicável; não expor caminho interno |
| AIPrediction | id, module, order_id/inspection_id, result, factors, execution_mode, data_origin, model_version, feature_snapshot_at, created_at |
| Recommendation | id, order_operation_id, employee_id, score, component_scores, weights_version, explanation, decision, decided_by |
| ModelVersion | id, module, artifact_reference, dataset_version, training_run, evaluation_reference, status; só criar evidência real quando executada |
| AuditLog | actor_id, action, entity, entity_id, timestamp, change_summary, reason |
| DashboardMetrics | contrato agregado de leitura; não precisa ser tabela persistida |

Regras de consistência:

- Não confundir colaborador com usuário de acesso; o vínculo entre ambos pode ser opcional.
- Progresso final do lote deve usar a etapa final aprovada ou outra regra formalizada. Somar gola + manga + acabamento conta a mesma peça várias vezes.
- Retrabalho não equivale automaticamente a refugo e não deve aumentar a produção boa sem regra explícita.
- Produção maior que a meta exige tratamento definido; não truncar silenciosamente registros.
- O alvo de atraso pode ser `completed_at > due_date` com política de calendário e horário limite documentada. Lote ainda aberto não tem rótulo final confirmado.
- Impedir valores negativos, datas inconsistentes, referência a operação fora do lote e alocação além da disponibilidade.
- Confirmar tratamento de feriados, dias úteis, turnos, terceirização e precedência de operações com a empresa.

## 8. APIs planejadas — contratos propostos

Prefixo `/api/v1`. Não são endpoints existentes. Definir schemas Pydantic e documentação OpenAPI ao implementar. Recursos de coleção devem suportar paginação e filtros; gravações devem validar permissão no servidor.

| Método e rota | Finalidade |
|---|---|
| POST `/auth/login`; POST `/auth/logout`; GET `/auth/me` | Sessão real apenas na fase F1 |
| GET `/dashboard?from=&to=` | Métricas e séries com período e definições |
| GET/POST `/orders`; GET/PATCH `/orders/{id}` | Consulta, criação e atualização de lotes |
| POST `/orders/{id}/transitions` | Mudança de status com motivo |
| GET/POST `/clients`; GET/PATCH `/clients/{id}` | Clientes |
| GET/POST `/garment-models`; GET/PATCH `/garment-models/{id}` | Modelos |
| GET/POST `/operations`; GET/PATCH `/operations/{id}` | Catálogo |
| GET/POST `/orders/{id}/operations` | Roteiro do lote |
| PATCH `/order-operations/{id}` | Ajuste de etapa |
| GET/POST `/employees`; GET/PATCH `/employees/{id}` | Colaboradores |
| GET/PUT `/employees/{id}/skills` | Habilidades por operação |
| GET/POST `/employees/{id}/availability` | Disponibilidade |
| GET/POST `/production-records`; PATCH `/production-records/{id}` | Produção e correções auditadas |
| GET/POST `/inspections`; GET `/inspections/{id}` | Inspeções |
| POST `/images` | Upload protegido com limites explícitos |
| POST `/inspections/{id}/decision` | Confirmar, rejeitar ou corrigir resultado |
| POST `/ai/delay-predictions` | Estimativa a partir de lote e instante de referência |
| POST `/ai/quality-analyses` | Inferência visual de imagem já validada |
| POST `/ai/balancing-recommendations` | Sugestões por score e restrições |
| POST `/assignments` | Aplicar decisão humana de alocação |
| GET `/ai/models`; GET `/ai/status` | Versões e estado verificável dos módulos |
| GET `/exports/production` | Exportação autorizada com minimização |
| GET/PATCH `/settings` | Parâmetros permitidos por perfil |

Envelope de resultado inteligente proposto:

```json
{
  "id": "demo-prediction-001",
  "module": "delay",
  "executionMode": "mock",
  "dataOrigin": "mock",
  "modelVersion": null,
  "result": { "riskScore": 0.81, "riskLevel": "high" },
  "factors": ["Produção diária demonstrativa abaixo da necessária"],
  "notice": "Resultado demonstrativo; não representa previsão validada."
}
```

No mock, `riskScore` não é probabilidade calibrada. Em modelo experimental, só usar “probabilidade” com definição e avaliação de calibração. Erros devem informar código e mensagem útil, sem stack trace ou segredos. Não devolver resultado mock silenciosamente se um serviço real falhar: apresentar indisponibilidade ou uma mudança explícita para modo de demonstração.

## 9. Páginas, identidade e comportamento do mock

Marca: **Duas Marias / Smart Production**. Subtítulo: **Gestão Inteligente da Produção**. Estilo corporativo limpo, fundo claro, branco/cinza, vinho/rosa escuro, cards, sombras suaves, menu lateral e gráficos legíveis; evitar estética futurista exagerada.

| Página/rota proposta | Conteúdo e interação |
|---|---|
| `/login` | Email, senha e Entrar; qualquer preenchimento pode entrar somente em demonstração, com aviso de ausência de autenticação real |
| `/dashboard` | Cards, linha dos últimos sete dias, lotes por status, lista de atenção |
| `/lotes` | Aproximadamente oito lotes fictícios; código, cliente, modelo, quantidade, produzido, percentual, prazo, status e risco demonstrativo |
| `/lotes/:id` | Dados do lote, progresso, operações, fatores do risco e aviso mock |
| `/producao` | Registros do dia: colaborador, lote, operação, quantidade, retrabalho e horário |
| `/colaboradores` | Nome fictício, função, produtividade com unidade, qualidade e disponibilidade |
| `/operacoes` | Gola, manga, barra, costura lateral, etiqueta, acabamento e revisão; referências de produtividade |
| `/qualidade` | Seleção de lote, upload/prévia, análise mock, carregamento de cerca de um segundo, confirmar/rejeitar e aviso visível |
| `/inteligencia-ia` | Três módulos, origem dos dados, estado real e roadmap |
| `/configuracoes` | Parâmetros demonstrativos e identificação do ambiente |

Fixtures citadas na conversa: produção de hoje 1.248 peças, meta 1.400, atingimento aproximado 89%, cinco lotes em andamento, dois em risco, retrabalho 3,4%. O rótulo antigo “eficiência” deve ser explicado como atingimento da meta (`1248 / 1400`), ou substituído por “Atingimento da meta”, pois eficiência operacional exige outra definição.

Lote exemplo OP-001: Cliente A, camiseta básica, 3.000 peças, 1.950 produzidas, 65% concluído e score mock de risco 81%. OP-004: score mock 58%. O histórico também citou OP-002 com 1.500/1.280 peças e 43%, e OP-003 com 2.000/1.900 e 12%. Escolher um conjunto coerente de limiares e declarar que são parâmetros de interface, sem valor estatístico validado.

O exemplo original usou prazo 17/09/2026 e “3 dias restantes”. Não reutilizar essa combinação como atual: definir uma data-base de demonstração ou recalcular prazos relativos. Fixar o relógio da fixture torna os testes reproduzíveis.

Operações demonstrativas do OP-001: corte 100%, costura lateral 85%, gola 60%, manga 45%, acabamento 20%. Esses percentuais ilustram etapas; não inferir que resultam automaticamente em 65% de peças finais. Ajustar a fixture ao modelo de progresso escolhido.

Resultado visual mock: “Possível defeito identificado — Costura torta — 87% (valor demonstrativo)”. O resultado não depende do conteúdo da imagem; informar isso. Confirmar/rejeitar registra apenas a interação demonstrativa. A interface não pode insinuar inspeção real nem aprendizado automático após o clique.

## 10. Dados públicos e StitchingNet — pendente de verificação

**Todas as informações desta seção são alegações trazidas pela conversa anterior e não foram verificadas neste documento.** Os links foram preservados como referências candidatas, sem garantia de existência, autoria, disponibilidade ou licença. Não baixar nem treinar automaticamente com base apenas nesta lista.

| Referência candidata | Link informado | Alegações a verificar |
|---|---|---|
| StitchingNet — GitHub | https://github.com/hyungjungkim/StitchingNet-dataset | Autoria, relação com artigo e fonte oficial |
| StitchingNet — Kaggle | https://www.kaggle.com/datasets/hyungjung/stitchingnet-dataset | Conteúdo, acesso, versão e licença |
| StitchingNet — Hugging Face | https://huggingface.co/datasets/hyungjungkim/StitchingNet | Correspondência com os demais repositórios |
| StitchingNet-Seg | https://github.com/hyungjungkim/StitchingNet-Seg | Existência, máscaras, formato COCO e licença |
| TILDA | https://lmb.informatik.uni-freiburg.de/resources/datasets/tilda.en.html | Disponibilidade e adequação a costuras |
| MVTec AD | https://www.mvtec.com/research-teaching/datasets/mvtec-ad | Licença, categorias e adequação ao problema |

A conversa atribuiu ao StitchingNet: **14.565 imagens**, **dez classes de defeitos**, **onze tipos de tecido**, resolução **224 × 224**, publicação associada em **2025** e licença **CC BY-NC 4.0**. Nenhum desses itens deve ser tratado como confirmado aqui. Também é pendente verificar presença e quantidade de imagens normais: dez classes de defeitos não implicam automaticamente uma classe normal disponível para classificação binária.

Classes mencionadas, com tradução provisória: skipped stitch (ponto falhado), broken stitch (ponto rompido), pinched fabric (tecido pinçado), crooked seam (costura torta), thread sagging (linha frouxa), puckering (franzimento/enrugamento), stain and damage (mancha/dano), needle mark (marca de agulha), bobbin thread pulling up (linha da bobina puxada para cima) e overlapped stitch (ponto sobreposto).

O StitchingNet-Seg foi descrito como contendo máscaras e anotações COCO sob CC BY 4.0; isso também está pendente. TILDA foi descrito como tendo 3.200 imagens e oito tipos de tecido. MVTec AD foi descrito como contendo mais de 5.000 imagens, quinze categorias e licença CC BY-NC-SA 4.0. “Ten Fabrics Dataset” foi citado sem URL verificável; manter como pista de pesquisa, não fonte utilizada.

Antes de qualquer uso, registrar: URL acessada e data, autores e artigo/DOI confirmados, licença exata de cada componente, atribuição exigida, restrições acadêmicas/comerciais, arquivos e checksums, versão, contagens por classe, presença de normais, modalidade de anotação, duplicatas e partições. Verificar se diferentes imagens derivam da mesma peça, sessão ou sequência. Confirmar licença novamente antes de distribuição do dataset, imagens, pesos ou uso pela empresa. A compatibilidade de uso não foi estabelecida.

Não escrever “fonte de dados resolvida”. A adequação depende de domínio visual, iluminação, escala, câmera, tecido, defeitos e qualidade das anotações.

## 11. Dados sintéticos e previsão de atraso

Não foi identificada no histórico recuperado uma base operacional pública confirmada que represente os lotes, pessoas, prazos, faltas e conclusão da Duas Marias. Isso não prova inexistência de bases; indica uma lacuna de dados do projeto.

O gerador sintético proposto deve produzir lotes, operações, capacidades, produção por período, retrabalho, disponibilidade e conclusão segundo hipóteses explícitas. Registrar semente aleatória, distribuições, unidades, correlações, limites, cenários extremos, versão e dicionário. Não incluir nomes reais.

Variáveis candidatas no instante da previsão: quantidade planejada, quantidade boa concluída, tempo restante, taxa recente de produção, operações pendentes, capacidade disponível conhecida e retrabalho observado até aquele instante. Definir frequência de observação e horizonte da previsão.

Alvo futuro: atraso da conclusão em relação ao prazo acordado. Evitar vazamento: data real de conclusão, produção futura, retrabalho futuro e qualquer campo calculado após o instante de previsão não podem entrar como atributos. Separar todos os snapshots do mesmo lote no mesmo subconjunto; preferir separação temporal para avaliação operacional futura.

Etapas propostas:

1. Baseline operacional: comparar produção necessária por dia com capacidade estimada.
2. Regressão logística como baseline estatístico e Random Forest como alternativa exploratória.
3. Treino/validação/teste separados, com transformações ajustadas apenas no treino.
4. Relatar precisão, recall da classe atraso, F1, matriz de confusão, PR-AUC quando pertinente e calibração se houver probabilidades.
5. Testar sensibilidade a mudanças no gerador e relatar distribuição de classes.

**Limitação central:** se o alvo é gerado por regras, o modelo pode apenas aprender essas regras. Bom desempenho sintético não demonstra previsão real nem impacto empresarial. Não apresentar acurácia sem experimento reproduzível e nunca transferir métricas sintéticas para a empresa.

## 12. Balanceamento por score

Primeira implementação planejada: heurística explicável, não modelo de ML treinado. Aplicar primeiro restrições de elegibilidade (habilitação, disponibilidade e compatibilidade da operação). Depois ordenar candidatos elegíveis por score.

Exemplo proposto, com pesos ainda não aprovados:

```text
score = wp × produtividade_normalizada
      + wq × qualidade_normalizada
      + we × experiencia_normalizada
      + wd × disponibilidade_normalizada
wp + wq + we + wd = 1
```

Normalizar produtividade dentro da mesma operação e unidade, considerando período e condições comparáveis. Definir tratamento de faltantes, amostras pequenas e empates; não atribuir zero silenciosamente a quem não tem histórico. Disponibilidade deve atuar também como restrição de capacidade para evitar dupla alocação.

Exibir pesos, componentes, justificativa e limitações. A gestão confirma a decisão. Não afirmar otimização global de linha: dependências entre operações, gargalos e carga simultânea exigem modelagem adicional. Avaliar cenários conhecidos e cobertura das restrições; não usar dados sensíveis ou características protegidas como fatores de ranking.

## 13. Visão computacional

No protótipo, upload e resultado são apenas demonstração. Na fase experimental, começar por problema de classificação compatível com as anotações realmente disponíveis. Classificação normal/defeito depende da existência de exemplos normais adequados; multiclasses depende de rótulos confirmados. Classificação não fornece automaticamente localização do defeito. Segmentação é fase futura e exige máscaras.

Pipeline proposto: verificar fonte/licença → inventariar e limpar → dividir por peça/sessão quando possível → preparar imagens → baseline → treinamento → avaliação independente → versionar artefato → integrar inferência → avaliar transferência para imagens reais autorizadas.

Transfer learning pode ser investigado, com arquitetura escolhida após inspeção do conjunto e recursos. Aplicar aumento de dados apenas no treino, preservando significado do defeito. Não manter variantes ou recortes da mesma imagem nos conjuntos de treino e teste.

Relatar precisão, recall e F1 por classe, macro-F1, matriz de confusão, suporte por classe e exemplos de erro. Para segmentação futura, definir métricas apropriadas como IoU/Dice. Não inventar números. O score de saída do classificador não é garantia de correção; prever resultado inconclusivo e revisão humana.

O teste em dataset público avalia aquele domínio. Uso real exige protocolo de captura, imagens locais rotuladas, revisão por pessoa habilitada e avaliação independente. Não enviar imagens da empresa a terceiros sem autorização.

## 14. Metodologia acadêmica e evidências

Enquadramento proposto: pesquisa aplicada, desenvolvimento de artefato e estudo exploratório com avaliação técnica. Confirmar a metodologia exigida pela instituição e pelo professor; não afirmar entrevistas, visitas, aprovações éticas ou resultados não realizados.

1. Confirmar problema e requisitos com a beneficiária, documentando fonte e data.
2. Modelar processos, entidades, regras e fluxos; revisar prioridades.
3. Implementar protótipo navegável e avaliar compreensão/usabilidade dos fluxos.
4. Verificar bases públicas e planejar coleta real autorizada.
5. Implementar persistência e coleta estruturada.
6. Executar experimentos com protocolo, baseline, versões e resultados reproduzíveis.
7. Integrar os módulos concluídos mantendo identificação da evidência disponível.
8. Relatar limitações, ameaças à validade e evolução futura.

Separar três avaliações: **software** (fluxos, integridade e permissões), **experimentos** (métricas no conjunto definido) e **benefício operacional** (ainda depende de estudo na empresa). Mock funcional não valida IA; teste de IA não comprova redução de atrasos ou retrabalho.

Entregas acadêmicas recomendadas: matriz de requisitos e evidências, arquitetura, dicionário de dados, protocolo experimental, registro de origem/licença, resultados efetivamente obtidos, limitações, manual de execução e roteiro demonstrativo. Não criar bibliografia com autores, DOI ou títulos inventados.

## 15. Critérios de aceite

### Protótipo F0

- Instala e inicia pelas instruções do README; navegação principal e acesso direto às rotas funcionam.
- Login demonstrativo está identificado e não coleta credenciais reais.
- Telas prioritárias estão completas; demais itens do menu levam a tela coerente ou indicam planejamento claramente.
- Lotes e registros vêm de fixtures separadas e mantêm relações e cálculos coerentes.
- Dashboard explicita período, unidades e fórmula dos indicadores.
- Seleção de lote, detalhe e fluxo de imagem funcionam com estados vazio, carregamento e resultado.
- Resultado de IA possui aviso MOCK próximo ao valor, inclusive em detalhe e eventual exportação.
- Confirmação/rejeição da inspeção atualiza o estado demonstrativo e não afirma treinar modelo.
- Layout é utilizável em tela pequena e por teclado; console sem erros nos fluxos exercitados.
- README identifica telas implementadas, persistência usada, limites e pontos de integração futura.

### MVP persistente F1

- Lote, operações, produção e inspeções persistem e podem ser consultados após reiniciar.
- Regras de quantidade/progresso são verificadas; correções não apagam a rastreabilidade.
- Autorização é aplicada na API e upload inválido é recusado.
- Migrações reproduzem o esquema e restauração é ensaiada antes do uso operacional.
- Dados reais permanecem separados dos demonstrativos e exportações respeitam permissões.

### Experimentos F2

- Dataset possui origem, licença verificada, versão e partição documentadas.
- Experimento registra código/configuração, semente, baseline, métricas, limitações e artefato, quando houver.
- Não há vazamento conhecido entre treino e teste; ocorrências e limitações são relatadas.
- Inferência integrada informa versão e origem dos dados e trata indisponibilidade sem inventar saída.
- Relatório diferencia resultado público, sintético e local; nenhuma alegação de validação na Duas Marias sem estudo próprio.

## 16. Segurança, privacidade e operação

No mock, usar nomes e imagens fictícios ou autorizados; evitar senhas reais. Qualquer login aceito é um recurso exclusivo de demonstração, nunca mecanismo de segurança.

Na etapa real: acesso por menor privilégio, autorização em cada recurso, hash de senha com biblioteca mantida, transporte seguro no ambiente publicado, configuração de origens permitidas e segredos apenas no servidor. Escolher estratégia de sessão e proteção contra CSRF conforme o mecanismo adotado; não persistir credenciais de forma improvisada no navegador.

Imagens podem conter rostos, etiquetas, pedidos e informação comercial. Minimizar captura, remover metadados desnecessários, controlar acesso e definir retenção e exclusão. Limitar tamanho e tipo de upload, usar nomes gerados, verificar conteúdo efetivo e impedir caminhos fornecidos pelo usuário. Não registrar imagens ou tokens nos logs.

Confirmar com a empresa responsabilidades, finalidade, autorização de coleta, base legal aplicável e procedimento de acesso/eliminação de dados pessoais; este documento não constitui análise jurídica. Não atribuir consentimento ou conformidade que não tenham sido documentados.

Separar ambientes demonstrativo, desenvolvimento e operacional; não copiar dados reais para fixtures. Dependências devem ter versões compatíveis e lockfile. Definir backup, restauração, monitoramento e resposta a falhas antes de implantação real.

## 17. Roadmap e pendências

Sequência de referência, ajustável após confirmação de recursos:

1. Protótipo frontend com mock e apresentação demonstrável.
2. Banco, API e registros operacionais.
3. Dataset sintético e baseline de atraso.
4. Verificação do StitchingNet e experimento visual.
5. Integração dos módulos efetivamente disponíveis.
6. Coleta estruturada de dados reais — pode começar antes dos experimentos se houver autorização.
7. Dataset próprio, avaliação local e eventual fine-tuning.
8. Segmentação, otimização mais completa e implantação após validação.

Pendências prioritárias:

- Recuperar e conferir a lista original RF/RNF; reconciliar IDs antes de usá-los como contrato acadêmico oficial.
- Confirmar calendário do semestre e critérios do professor.
- Validar diagnóstico e fluxo de produção com a beneficiária.
- Definir produção boa, retrabalho, conclusão de lote, eficiência, calendário e capacidade.
- Verificar todas as referências, licenças e características do StitchingNet.
- Confirmar infraestrutura e recursos de treinamento.
- Formalizar coleta, acesso, retenção e rotulagem dos dados reais.
- Decidir o escopo mínimo se o treinamento não couber no prazo.

## 18. Instruções práticas para o Codex

1. Ler este documento como contexto de produto e conferir o estado real do repositório antes de afirmar o que existe. Respeitar instruções atuais da usuária e regras aplicáveis do projeto.
2. Implementar primeiro o frontend mock quando a tarefa for o protótipo inicial; não ampliar para backend ou treino sem necessidade do marco solicitado.
3. Manter fixtures e serviços separados das páginas, interfaces TypeScript claras e componentes reutilizáveis.
4. Mostrar “Demonstração com dados fictícios” e rotular cada resultado simulado; manter `modelVersion` ausente/nulo quando nenhum modelo existir.
5. Não criar precisão, métricas, histórico real, depoimentos da empresa ou alegações de treinamento/validação.
6. Tratar RF/RNF e contratos propostos como pendentes de conferência, mantendo rastreabilidade das alterações. Não renumerar silenciosamente requisitos após obter os originais.
7. Tratar links e números dos datasets como referências não verificadas até haver evidência. Registrar verificações e fontes sem substituir pendência por suposição.
8. Não misturar dados mock, sintéticos, públicos e reais. Toda previsão deve revelar modo de execução e procedência.
9. Não substituir falha de API por retorno mock oculto. Erros devem ser visíveis e recuperáveis.
10. Usar dados demonstrativos coerentes, relógio de referência explícito, fórmulas documentadas e unidade em taxas de produção.
11. Preservar revisão humana da inspeção e das recomendações. Score heurístico não deve ser apresentado como ML.
12. Executar verificações adequadas ao que mudou: compilação/tipos e navegação no frontend; integridade/permissões na API; protocolo reproduzível nos experimentos.
13. Ao entregar, informar arquivos e telas implementados, como executar, verificações feitas, limitações e próximos pontos de integração. Distinguir “planejado”, “implementado”, “executado” e “avaliado”.

**Estado de referência desta documentação:** contexto consolidado e propostas técnicas; nenhuma comprovação de implementação, treinamento ou validação acompanha este arquivo.
