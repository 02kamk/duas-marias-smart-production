# Verificações — financeiro e produtividade pública

Execução em 20/10/2026.

## Resultados

- **19 testes do frontend aprovados**: os 12 anteriores e 7 novos. Verificam navegação, manutenção dos acessos à inspeção/gestão, origem demo versus dados locais, valor monetário sem perda de centavos, emissão versus liquidação, bloqueio de orçamento, ausência explícita de previsão e inferência pública.
- **16 testes novos Python/API aprovados**: centavos, ambiente real vazio, isolamento das origens, persistência, liquidação única, cancelamento somente em aberto, importação transacional e duplicação, datas/valores, política de orçamento, teste temporal, não confusão de aporte com faturamento, não duplicação de contas previstas e limite de alocação preservando reserva no estresse.
- **9 testes anteriores de gestão aprovados novamente**. Total: **44 testes aprovados**.
- `npx tsc --noEmit` aprovado; bundle adicional compilado com `vite.business.config.ts`.
- Experimento público realmente executado: fonte UCI baixada, CSV inventariado, modelo/partições/metadados gravados. Fonte, licença e métricas em FINANCEIRO_E_PRODUTIVIDADE_PUBLICA.md.
- Ensaio com a aplicação completa e lifespan real via TestClient: raiz, gestão, financeiro, produtividade, status, saúde, estado da gestão, relatório financeiro demo e real e metadados públicos retornaram HTTP 200. A inferência pública também retornou HTTP 200 e um índice calculado pelo artefato. A área real permaneceu vazia.
- Comparação do HTML confirmou conteúdo original preservado, com links adicionais. `git diff --exit-code` não apontou alteração em arquivos versionados originais.

TestClient emite aviso de depreciação do adaptador httpx na versão de Starlette instalada; não impediu os testes. O bundle contém Recharts e emite aviso de tamanho acima de 500 kB; carregamento sob demanda é melhoria futura. Não houve aquisição de câmera, envio de imagem, compra, transferência, upload financeiro externo ou push ao GitHub.

## Limites

Os testes das telas usam jsdom e substituem gráficos por mocks. Não foi concluída uma revisão visual do novo layout no navegador nem teste de decodificação/câmera. A integração HTTP foi verificada em processo, sem depender de acesso do navegador ao localhost isolado do sandbox.

Nenhum dado financeiro real da empresa foi recebido ou usado para treinar/validar projeções. As telas financeiras mostram fixtures no ambiente demo e começam vazias no ambiente real. As projeções demo provam execução do pipeline, não desempenho financeiro na Duas Marias.

## Repetir

Na pasta frontend:

```powershell
npm.cmd test
npx.cmd tsc --noEmit
npx.cmd vite build --config vite.business.config.ts
```

Na pasta pontocerto, com o ambiente existente:

```powershell
C:\Users\kamil\Documents\Codex\venvs\pc\Scripts\python.exe scripts\08_testar_gestao.py
C:\Users\kamil\Documents\Codex\venvs\pc\Scripts\python.exe scripts\12_testar_financeiro_produtividade.py
```

## Conferir manualmente

1. Iniciar o script 11 e visitar os quatro endereços da documentação.
2. Em financeiro DEMO, revisar saldo/compromissos, histórico, projeções e cenário de orçamento.
3. Mudar para dados locais e conferir que começa vazio e sem previsão fabricada.
4. Ajustar data/saldo inicial, cadastrar documentos fictícios e testar tipo/natureza, vencimento e liquidação.
5. Importar CSV de teste: uma linha inválida deve recusar todo o lote; reimportação da referência deve ser recusada.
6. Cancelar conta em aberto com motivo; conferir preservação e histórico. Confirmar que conta liquidada não aceita segundo pagamento ou cancelamento simples.
7. Confirmar um período completo apenas se o arquivo estiver completo; checar o mínimo de 12 meses até o mês anterior e os métodos/erros de previsão.
8. Em Produtividade UCI, consultar partições/métricas e executar cenário dentro da base pública, sem confundir o índice com peças ou atraso.
9. Repetir em desktop e tela pequena usando teclado; inspecionar console e gráficos.
