# Financeiro local e produtividade pública — 20/10/2026

Esta entrega é adicional: preserva arquivos e comandos anteriores, CNN, câmeras, fotos, qualidade, gestão de lotes, produção, atraso sintético e balanceamento.

## Iniciar todas as partes

No terminal da pasta `pontocerto`, encerre sua instância antiga com Ctrl+C e execute:

```powershell
C:\Users\kamil\Documents\Codex\venvs\pc\Scripts\python.exe -u scripts\11_rodar_completo.py
```

Ou use `./Iniciar-Completo.ps1`. Se a política do PowerShell impedir o atalho, use diretamente o comando Python; não precisa mudar a política. `--porta 8001` permite manter outra instância de inspeção aberta, mas não rode duas instâncias financeiras escrevendo nos mesmos JSONs.

| Endereço | Parte |
|---|---|
| http://127.0.0.1:8000/ | Inspeção original, câmeras, fotos e qualidade |
| http://127.0.0.1:8000/gestao | Gestão já entregue: lotes, produção, atraso e balanceamento |
| http://127.0.0.1:8000/financeiro | Novo financeiro |
| http://127.0.0.1:8000/produtividade | Novo experimento público |

Os scripts 05 e 07 continuam com seu comportamento anterior. O novo comando 11 acrescenta os módulos sem editar as fábricas antigas. Links adicionais são inseridos na resposta HTML em execução. As páginas novas já estão compiladas; não precisa iniciar npm para utilizá-las pelo Python.

## Base financeira da empresa

Dois ambientes separados por arquivos:

- **DEMO:** 18 meses fictícios determinísticos, com 72 documentos e saldo inicial ilustrativo. Serve para testar telas, métodos e regras, não representa dinheiro da empresa.
- **Dados locais da empresa:** começa vazio. Nenhum lançamento demo é copiado. Dados fornecidos pelo operador são identificados como não conciliados/validados independentemente.

`pontocerto/artifacts/finance_local/demo.json` e `real.json` são ignorados pelo Git. Gravação atômica e lock atendem uma instância local; não substituem PostgreSQL, autenticação, permissões, backup ou auditoria contábil. Não publicar o servidor na rede com dados da empresa. Não há envio de lançamentos a OpenRouter/OpenAI ou qualquer IA externa; APIs de análise e modelos rodam localmente.

### Cadastro e importação

Cada documento guarda referência única, entrada/saída, natureza, categoria, descrição, valor positivo em reais, emissão, vencimento e liquidação opcional. Valores são armazenados como **centavos inteiros**, sem arredondar frações extras silenciosamente. A natureza distingue operacional, equipamento/ativo e financiamento/aporte. Financiamento e venda de ativo não contam como faturamento operacional.

A interface fornece cabeçalhos CSV em `/api/business/finance/template.csv`. Formato de importação:

```text
reference;type;nature;category;description;amount;documentDate;dueDate;settledDate
```

- `type`: income ou expense.
- `nature`: operating, equipment ou financing.
- Datas: AAAA-MM-DD. `settledDate` vazio mantém a conta em aberto.
- Valor: reais positivos, ponto ou vírgula decimal; até duas casas. Com vírgula decimal, use delimitador `;`.
- Limites: 500 KB e 1.000 linhas. Todas as linhas são validadas antes da gravação. Erro/duplicação recusa o lote inteiro; não há importação parcial oculta.
- Configure a data e o saldo inicial antes de importar documentos antigos; documentos anteriores ao início não são descartados silenciosamente, são recusados.

Liquidação é integral e não pode ser futura ou anterior ao documento. Liquidar duas vezes é recusado. Cancelamento só é permitido para documentos em aberto, com motivo e preservação do registro. Documentos já pagos/recebidos exigem conciliação/estorno específico, ainda não implementado. Não há exclusão destrutiva, pagamento bancário ou compra automática.

## Verde, amarelo e vermelho

O sinal representa **cobertura de caixa pelos registros**, não a saúde financeira completa ou lucro contábil:

- Vermelho: caixa, caixa menos pagamentos até 30 dias ou cenário de estresse negativo.
- Amarelo: histórico insuficiente, compromissos vencidos, reserva incompleta ou outras condições de bloqueio.
- Verde: cobertura dentro das regras configuradas e dos dados cadastrados. Não garante solvência nem ausência de passivos não registrados.

Saldo de caixa = saldo inicial + entradas liquidadas − saídas liquidadas a partir da data inicial. Recebíveis são apresentados separadamente e não viram caixa antes da liquidação. Faturamento documental operacional usa emissão, sem afirmar reconhecimento contábil/fiscal completo.

## Previsões de faturamento, recebimentos e gastos

O operador confirma um intervalo de meses completos. Meses sem lançamentos dentro desse intervalo são tratados como zero **somente porque houve confirmação explícita de completude**. Não inferir ausência de movimentos a partir de arquivo incompleto.

Com pelo menos 12 meses completos consecutivos até o mês anterior:

1. Agrega faturamento operacional por emissão e recebimentos/pagamentos operacionais por liquidação.
2. Compara último mês, média de 3 meses e tendência Ridge.
3. Seleciona por MAE em três meses de validação rolling; avalia em três meses posteriores reservados. Em cada passo, usa apenas meses anteriores. O ajuste final para projeção usa todo o histórico confirmado.
4. Projeta 1 a 6 meses. Testes reportados são de um passo; horizontes maiores têm incerteza adicional. Não modela sazonalidade automaticamente.
5. Compara o total operacional esperado com contas operacionais conhecidas por vencimento usando o maior dos dois, evitando somar o mesmo padrão duas vezes. Financiamentos/equipamentos futuros conhecidos são acrescentados separadamente; não são tratados como recorrência automática.

Com menos dados, informa insuficiência e exibe somente contas cadastradas, sem inventar previsão. No ambiente real ainda não há modelo validado nem histórico fornecido. A demonstração permite exercitar o pipeline, não provar desempenho empresarial.

A ponte do mês atual inclui vencidos e contas com vencimento até o fim do mês, supondo liquidação. A hipótese é explícita e recebimentos não são garantidos. Cenário de estresse reduz entradas e aumenta saídas pelo percentual configurado; **não é intervalo estatístico de confiança**. Previsões negativas de volume monetário dos métodos são limitadas a zero explicitamente; caixa pode ser negativo e é exibido assim.

A API identifica `cashflow-v1`, origem, data, hash dos dados/premissas, métodos selecionados e erros de validação/teste. Não há alegação de modelo financeiro treinado na UCI: os modelos financeiros usam apenas o histórico do ambiente selecionado.

## Reserva, equipamento e contingência

É uma **regra explicável de orçamento**, apoiada nos cenários, não ML que descobriu a alocação ótima:

```text
reserva-alvo = média das últimas 3 saídas operacionais mensais × meses de reserva configurados
excedente = máximo(0, caixa atual − contas a pagar até 30 dias − reserva-alvo)
base habilitada = mínimo(excedente, máximo(0, menor caixa no estresse − reserva-alvo))
equipamento = base habilitada × percentual configurado
contingência = base habilitada × percentual configurado
restante = excedente − equipamento − contingência
```

O sistema não considera recebíveis futuros como verba para compra imediata. Sugestão para equipamento é zerada se falta histórico, há despesas vencidas, falta caixa ou o cenário de estresse indica déficit. Percentuais não podem ultrapassar 100% em conjunto. Padrões de demonstração (3 meses, 20%, 10%, estresse 15%) são **hipóteses editáveis**, não recomendações aprovadas ou universais.

Os montantes não são transferidos a contas nem investidos. Para uma decisão real, verificar completude do caixa/passivos, retorno/custo total da máquina, manutenção, tributos e condições da empresa com responsáveis habilitados. Não há recomendação de ativos financeiros.

Referência conceitual consultada: [BDC — planejamento de fluxo de caixa](https://www.bdc.ca/en/articles-tools/money-finance/manage-finances/making-projection-coming-year). As fórmulas e limiares desta extensão são escolhas explícitas de implementação, não parâmetros prescritos pelo BDC.

## Treinamento com dados públicos: UCI 597

Fonte: [Productivity Prediction of Garment Employees](https://archive.ics.uci.edu/dataset/597/productivity). Atribuição: Productivity Prediction of Garment Employees [Dataset]. (2020). UCI Machine Learning Repository. DOI [10.24432/C51S6D](https://doi.org/10.24432/C51S6D). Licença CC BY 4.0. O download oficial de 20/10/2026 foi inventariado e preservado com SHA256.

1.197 linhas, 15 colunas, nenhuma duplicata exata. Foram encontrados **37 alvos acima de 1**, máximo 1,1204375; preservados e registrados, apesar da descrição genérica 0–1 da página. Normalizou-se espaço/capitalização do departamento, mantendo `sweing` da fonte. Código da equipe é categórico.

Atributos: equipe, departamento, efetivo, mudanças de estilo, meta, SMV e dia da semana derivado da data. São premissas de início do turno; essa disponibilidade deve ser confirmada antes de aplicar a outro ambiente. Excluídos horas extras realizadas, incentivo, ociosidade, WIP e outros campos com timing incerto. O alvo `actual_productivity` nunca entra como entrada.

Separação por datas inteiras ordenadas, sem dividir linhas do mesmo dia:

| Conjunto | Registros | Período |
|---|---:|---|
| Treino | 823 | 01/01/2015 a 17/02/2015 |
| Validação | 182 | 18/02/2015 a 01/03/2015 |
| Teste futuro | 192 | 02/03/2015 a 11/03/2015 |

Pré-processamento ajustado somente no treino: imputação numérica, padronização e one-hot de categorias. Seleção pelo menor MAE da validação, sem escolher pelo teste.

| Modelo | MAE validação | MAE teste | RMSE teste | R² teste |
|---|---:|---:|---:|---:|
| Mediana | 0,1541 | 0,1164 | 0,1725 | −0,2399 |
| Ridge | 0,1336 | 0,0925 | 0,1354 | 0,2367 |
| Random Forest | 0,1162 | 0,0951 | 0,1307 | 0,2889 |

Random Forest foi selecionada **na validação**, embora Ridge tenha menor MAE no teste. Não houve troca após olhar o teste. O artefato publicado mantém o modelo treinado no conjunto de treino, compatível com o protocolo reportado; não foi silenciosamente reajustado no teste. MAE 0,0951 não significa 90,49% de acurácia ou ganho de produtividade.

O simulador usa códigos da fonte pública e recusa categorias/intervalos desconhecidos. Mostra índice de produtividade, jamais converte automaticamente para peças/dia ou atraso. Não alimenta orçamento e não altera o modelo sintético anterior de atraso. Equipes reaparecem em datas futuras; o teste não mede generalização para uma fábrica/equipe nova. Ainda não há validação na Duas Marias.

Arquivos em `pontocerto/artifacts/productivity_public`: fonte original, CSV, partições, modelo, metadados e licença/atribuição. Para repetir:

```powershell
C:\Users\kamil\Documents\Codex\venvs\pc\Scripts\python.exe scripts\10_treinar_produtividade_publica.py
```

O script usa o CSV já presente; só baixa da UCI se estiver ausente. Não envia dados financeiros ou imagens da empresa. Retreine no próprio ambiente se a versão do scikit-learn diferir; só carregue artefatos locais confiáveis.

## APIs e fontes de código

- `/api/business/finance/{demo|real}/state` e `/report?horizon=3`.
- POST `/entries`, POST `/import`, POST `/entries/{id}/settle`, POST `/entries/{id}/cancel` sob o mesmo prefixo de ambiente.
- PATCH `/api/business/finance/{demo|real}/settings`.
- GET `/api/business/productivity/model`, POST `/api/business/productivity/predict`.
- Python novo: `pontocerto/src/pontocerto/business/`.
- React novo: `frontend/src/business/`.

Para recompilar a página adicional, na pasta frontend: `npx vite build --config vite.business.config.ts`. Não substituir as configurações anteriores. Os scripts de teste novos e antigos continuam disponíveis.

## Limites restantes

Protótipo local em JSON, sem autenticação ou armazenamento financeiro operacional. Ainda faltam PostgreSQL/SQLAlchemy/Alembic, autorização, conciliação bancária, pagamentos parciais, estorno de liquidações, integração fiscal/contábil, backup/restauração e validação com responsáveis da empresa. Não há execução autônoma de compras, banco ou investimentos. Não foi feito push ao GitHub.
