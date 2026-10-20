# Verificação F0 — 19/10/2026

## Executado

- `npm install`: dependências instaladas e package-lock.json gerado. Auditoria npm reportou zero vulnerabilidades nesta execução.
- `npm run build`: TypeScript estrito e build Vite concluídos.
- `npm test`: quatro testes passaram em Vitest/jsdom.
  - Vínculos e somas de produção boa/retrabalho, série diária e limites de quantidade.
  - Login, filtro vazio, cadastro e navegação ao detalhe do novo lote.
  - Todas as telas do menu, alteração da meta refletida no dashboard e saída.
  - Upload inválido, prévia com API de imagem simulada no teste, carregamento mock, decisão humana e bloqueio de dupla confirmação.

Os gráficos são substituídos por mocks nos testes de componentes. A decodificação real do navegador, arrastar/soltar, layout responsivo, teclado e renderização dos gráficos ainda exigem conferência visual. Esses testes não equivalem a avaliação de usabilidade ou validação de IA.

## Limitações da verificação

O Vite informou inicialização na porta 5173, mas o navegador integrado e uma requisição HTTP independente não alcançaram o servidor local neste ambiente. Portanto, não foi concluído ensaio visual ou navegação ponta a ponta em navegador. Nenhuma captura de tela foi produzida.

O build emite avisos sobre diretivas `use client` da dependência React Router e tamanho do pacote principal (~681 kB minificado, ~206 kB gzip). Não impedem a compilação; divisão por rotas e carregamento sob demanda dos gráficos são melhorias futuras antes de publicação.

## Roteiro manual pendente

1. Iniciar `npm run dev` em frontend e abrir o endereço informado.
2. Entrar com dados fictícios, percorrer todos os links e usar voltar/avançar.
3. Buscar lote, combinar filtros, cadastrar código novo, verificar rejeição de código duplicado e abrir detalhes.
4. Em qualidade, selecionar lote e imagem autorizada, testar tipo inválido e tamanho maior que 5 MB. Analisar, confirmar, depois repetir com rejeição; verificar avisos MOCK próximos ao resultado.
5. Alterar meta e conferir produção/meta × 100. Recarregar e verificar reinicialização dos dados.
6. Repetir em largura de 390 px e em desktop, usando Tab e Enter; conferir prévia, gráficos, menus e tabelas com rolagem horizontal.
7. Inspecionar console do navegador; testar rota direta e página inexistente. Sem login demonstrativo, as rotas levam à entrada.

## Estado da integração

Nenhum backend, dataset, câmera, OpenRouter ou modelo foi executado por este frontend. O projeto Python anterior foi preservado. Arquivos novos estão no clone local e não foram enviados ao GitHub.

## Ampliação de produção

Oito testes passaram após acrescentar regras de quantidade, filtros e fluxo integrado de registro → dashboard → detalhe. Build de produção aprovado. A abertura do VS Code foi solicitada com a pasta raiz; o processo Code iniciou. A revisão visual do frontend segue pendente.
