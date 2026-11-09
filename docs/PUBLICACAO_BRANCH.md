# Branch de evolução do Duas Marias Smart Production

Branch: `codex/gestao-financeiro-produtividade`. Base: `739c2d8` da main. Esta entrega não altera a main e não edita os arquivos originais de inspeção/câmeras.

## Conteúdo

- Frontend React demonstrativo com lotes, dashboard, produção e qualidade mock.
- Extensão aditiva do Ponto Certo: gestão de lotes/produção, análise sintética de atrasos, planejamento e balanceamento com revisão humana.
- Financeiro local: receitas/despesas, CSV, contas, cenário de caixa e orçamento explicável. Separação entre demonstração e dados locais da empresa.
- Experimento treinado com dados públicos UCI 597: produtividade de equipes, com partições temporais, baselines, artefato, métricas e atribuição CC BY 4.0.
- Testes, bundles adicionais já compilados e documentação dos limites.

Nenhum dado financeiro local, arquivo .env, ambiente Python ou node_modules faz parte desta entrega. Artefatos novos são sintéticos ou derivados do dataset público identificado. Os modelos não são declarados validados na Duas Marias. Autenticação real e PostgreSQL/SQLAlchemy/Alembic permanecem na etapa operacional futura.

## Executar

Use as dependências Python de pontocerto/requirements.txt no ambiente preparado. Na pasta pontocerto:

```powershell
python scripts/11_rodar_completo.py
```

No ambiente Windows usado no desenvolvimento:

```powershell
C:\Users\kamil\Documents\Codex\venvs\pc\Scripts\python.exe -u scripts\11_rodar_completo.py
```

Inspeção: http://127.0.0.1:8000/ ; gestão: /gestao ; financeiro: /financeiro ; produtividade: /produtividade.

Os scripts 05 e 07 continuam disponíveis com seus comportamentos anteriores. Para comparar, revisar ou propor merge, use esta branch; não é necessário substituir a main para testar.

## Evidência de validação

44 testes aprovados: 19 do frontend, 9 da gestão e 16 de financeiro/produtividade. TypeScript e bundles adicionais compilados. Rotas da aplicação completa e inferência pública conferidas via TestClient. Revisão visual final, câmera física e validação empresarial não foram concluídas nesta entrega. Detalhes em VERIFICACAO_FINANCEIRO_PUBLICO.md e documentos relacionados.
