# Verificação da extensão — 20/10/2026

## Executado

- Treino sintético: 2.400 lotes, dois modelos Random Forest, baseline de capacidade e regressão logística; artefatos, dataset, partições e metadados salvos em pontocerto/artifacts/gestao_ml.
- TypeScript: `npx tsc --noEmit` aprovado.
- Bundle adicional: `npx vite build --config vite.gestao.config.ts` aprovado; JS ~248 kB, gzip ~77 kB.
- Vitest: **12 testes passaram**, incluindo os oito anteriores e quatro da nova gestão. Conferem navegação, acesso à inspeção, apresentação de ML sintético, indisponibilidade explícita, envio do apontamento e exclusões de elegibilidade.
- Python/API: **9 testes passaram**, incluindo persistência, produção final versus intermediária, validações e atomicidade, conclusão do lote, código duplicado, planejamento auditado, disponibilidade, rejeição humana, ausência de modelo, partições por lote e inferência com o artefato treinado.
- `git diff --exit-code`: nenhum arquivo original versionado foi alterado. Todas as mudanças são arquivos adicionados. Não houve push ou PR.

Os testes usam Starlette TestClient; a versão instalada emite aviso de depreciação do adaptador httpx. O aviso não impediu os testes. No sandbox do Windows, foi necessário liberar conexões internas para socketpair e usar diretório temporário dentro do workspace (`PC_TEST_TMP`); as falhas de permissão iniciais não foram ocultadas como resultados aprovados.

## Verificação visual e hardware

O servidor estendido chegou à mensagem `Application startup complete` e `Uvicorn running` numa porta de teste separada. O navegador integrado não conseguiu acessar o localhost desse processo (timeout), portanto não foi concluída inspeção visual de layout ou ensaio ponta a ponta em navegador. Não foi acionada câmera, feita captura, enviado arquivo ao OpenRouter ou retreinada a CNN.

O teste de integração básico preserva o HTML e rotas existentes usando uma aplicação mínima. O novo script 09 permite conferir também a aplicação completa e suas rotas, sem ligar câmera ou alterar produção.

## Roteiro de aceite local

1. Iniciar o script 07 e abrir a raiz; conferir câmera/dispositivos, foto, arquivo, histórico, relatórios, treino e ajustes originais.
2. Abrir o link de gestão; conferir todas as abas em desktop e tela pequena, teclado e console.
3. Cadastrar lote fictício; testar código repetido e filtros.
4. Registrar Gola e confirmar que não aumenta peças finais; registrar Revisão final e conferir o progresso, total do dia e histórico.
5. Tentar excesso, negativo, fração, produção futura e colaborador sem habilitação; confirmar rejeição sem gravação parcial.
6. Analisar um lote e comparar baseline com o score sintético. Replanejar com motivo e executar nova análise. Conferir versão/origem junto ao resultado.
7. Consultar balanceamento, rejeitar uma sugestão, aceitar outra e tentar ultrapassar os minutos disponíveis na mesma data.
8. Reiniciar o servidor e conferir a persistência apenas da demonstração. Abrir Auditoria para consultar os motivos.

Autenticação real, PostgreSQL/SQLAlchemy/Alembic, correções auditadas de produção, cadastro completo de colaboradores/operações e vínculo de inspeção com lote continuam pendentes, conforme docs/GESTAO_ADITIVA.md. Esta entrega não é declarada como MVP operacional completo.

## Ensaio completo confirmado

Após os testes, o app original com a extensão foi exercitado via TestClient com o lifespan real: raiz, gestão, status, saúde, taxonomia, estado de gestão, metadados e análise retornaram HTTP 200. A análise executou os dois modelos salvos; o ensaio também confirmou preservação integral do HTML original, normalizando apenas finais de linha do Windows para comparar. Nenhuma câmera foi ligada. O script 09 permite repetir essa verificação.
