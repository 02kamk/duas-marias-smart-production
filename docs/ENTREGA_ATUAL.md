# O que foi feito

O GitHub informado é a origem deste clone. O código inicial em pontocerto/ foi preservado. As novas entregas estão em frontend/ e docs/. Alterações ainda locais, sem envio ao GitHub.

## Primeira etapa

Frontend React/TypeScript com Vite, Tailwind, Router, Recharts e Lucide. Login demonstrativo e oito telas de gestão, detalhe de lote, cadastro em memória, gráficos, filtros, upload local com resposta mock e revisão humana. Contexto principal copiado integralmente da entrega local anterior. Fontes de datasets e próximos marcos em CONTINUIDADE_E_DATASETS.md.

## Ampliação desta etapa

- Produção deixou de ser apenas consulta: agora registra revisão final por lote, colaboradora e horário.
- Boas e retrabalho permanecem separados; somente boas aumentam progresso e produção do dashboard.
- Cadastro atualiza total diário, gráfico do dia-base, indicadores e detalhe do lote. Atingir exatamente a quantidade do lote marca conclusão; registro parcial marca andamento.
- Validação recusa lote concluído, negativos, frações, registro zerado e excesso sobre o restante. Excesso exige revisão do registro; não é truncado.
- Consulta combina filtros de lote e colaboradora e mostra totais filtrados.
- Serviço de regras separado em frontend/src/services/productionService.ts e testes específicos.

Todos esses registros são demonstrações em memória. Recarregar reinicia a sessão. Os mesmos registros não podem ser usados como dados reais da empresa. Correção auditada, persistência e permissões exigem a próxima fase com API/banco.

## Abrir e executar no VS Code

Abra esta pasta raiz no VS Code. Os arquivos de entrada são README.md, frontend/src/pages/App.tsx, frontend/src/pages/Production.tsx e docs/CONTEXTO_PROJETO.md.

No terminal integrado:

```powershell
cd frontend
npm ci
npm run dev
```

Abra o endereço exibido. Para verificar: `npm test` e `npm run build`.

## Próxima entrega sugerida

Manter a etapa frontend até completar revisão de inspeções entre telas e edição de lotes com motivo. Depois implementar os contratos FastAPI/PostgreSQL do contexto, com migrações e integridade. Auditar os artefatos do Ponto Certo antes de expor inferência no novo frontend. Conferir licença do StitchingNet antes de qualquer integração operacional.
