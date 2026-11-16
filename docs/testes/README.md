# Testes e aceite

Use Markdown como registro principal: o Git mostra as alterações de cada rodada. O PDF é uma cópia para leitura e compartilhamento.

Os PDFs de origem em `fontes/` ficam somente nesta máquina e são ignorados pelo Git, pois podem conter fotos de OPs e dados internos. Os relatórios revisados em Markdown e PDF podem ser versionados sem anexar essas imagens.

- [Rodada de 14/11/2026](2026-11-14.md): relatos, diagnóstico, correções e próximos testes.
- [Segunda rodada de 14/11/2026](2026-11-14-rodada-2.md): revisão humana, histórico visual, recebimento com foto da OP e exportação PDF.
- `../../output/pdf/relatorio-testes-2026-11-14-rodada-2.pdf`: relatório ABNT da segunda rodada.
- [Configuração local](CONFIGURACAO_LOCAL.md): execução, Supabase e diagnóstico com IA.
- `fontes/2026-11-14-original.pdf`: documento recebido, preservado sem alterações.
- `../../output/pdf/relatorio-testes-2026-11-14.pdf`: versão revisada.

## Apresentação do PDF

O PDF usa as regras gerais de apresentação acadêmica da NBR 14724:2024: A4, Arial 12, texto preto justificado, entrelinhas de 1,5 e margens superior/esquerda de 3 cm e inferior/direita de 2 cm. O recuo de primeira linha adotado é 1,25 cm. A capa contém os três autores informados, Unisatc, Criciúma - SC e 2026. Folha de rosto e sumário são contados sem número impresso; a numeração aparece na parte textual, no alto à direita. A fonte de orientação é citada nas referências. É um documento de apoio, sem pretensão de substituir a estrutura de uma monografia completa.

Para regenerar, executar `python scripts/13_gerar_relatorio_testes.py` com `reportlab` instalado e as fontes Arial do Windows disponíveis. A publicação no GitHub está suspensa até o reteste local e nova autorização do usuário.

## Registrar uma ocorrência

Copie este bloco para uma nova rodada. Não marque como aprovado sem executar o caso.

```text
ID:
Data e hora:
Versão (git rev-parse --short HEAD):
Endereço completo e tela:
Pré-condições (banco, modelo, câmera e lote):
Passos numerados:
Resultado esperado:
Resultado observado / mensagem exata:
Evidência (imagem autorizada, sem dados pessoais ou segredos):
Status: relatado / reproduzido / corrigido / aguardando reteste / aprovado
Responsável pelo reteste:
```

Não inclua `.env`, senhas, chaves ou dados reais de colaboradores. Imagens de costura devem ter autorização para entrar no repositório. Os registros locais do sistema não fazem parte da documentação de teste.
