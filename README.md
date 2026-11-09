# Duas Marias Smart Production

Protótipo frontend F0 de Gestão Inteligente da Produção, orientado por [docs/CONTEXTO_PROJETO.md](docs/CONTEXTO_PROJETO.md). Dados fictícios, estado em memória, sem autenticação real, banco ou inferência integrada.

## Executar

Node.js 22.12+ ou 24 LTS e npm. No PowerShell, a partir desta pasta:

```powershell
cd frontend
npm ci
npm run dev
```

Abra http://127.0.0.1:5173. Informe um email e uma senha **fictícios**; qualquer preenchimento válido entra na demonstração. Para compilar: `npm run build`. Para testar: `npm test`. Para servir o build local: `npm run preview`.

## Implementado nesta etapa

- React, TypeScript, Vite, Tailwind, React Router, Recharts e Lucide.
- Login demo, dashboard, lotes com busca/status/prazo e cadastro, detalhe de lote, produção, colaboradores, operações, qualidade, inteligência IA e configurações.
- Upload local JPG/PNG/WebP até 5 MB com decodificação e prévia; análise fixa mock, carregamento, confirmação/rejeição humana e histórico da tela.
- Meta configurável; data-base fixa de 19/10/2026; oito lotes fictícios.
- Tipos, fixtures e serviços mock separados. Toda saída inteligente tem modo/origem mock e modelVersion nulo.

Dados de cadastro e configuração ficam no estado React e reiniciam no recarregamento. Inspeções ficam na tela de qualidade e reiniciam ao sair dela. Não há cadastro persistente, edição auditada, alocação ou envio de imagens. O upload não realiza análise real. Em hospedagem estática futura, configurar fallback de todas as rotas para index.html; o servidor Vite já atende rotas diretas.

## Indicadores

Produção diária: soma de boas na revisão final dos quatro registros mock = 1.248 peças. Meta inicial: 1.400; atingimento = boas/meta × 100 = 89,1%. Retrabalho: 44/(1.248+44) × 100 = 3,4%; são contagens separadas nesta fixture. Progresso de lote usa peças finais aprovadas, nunca soma operações. Os acumulados de lote incluem dias anteriores; registros da tela produção representam apenas o dia-base. Série de sete dias é fixture independente coerente com o total atual. Scores de risco são fixos; corte de 50% é parâmetro visual sem valor estatístico.

## Continuidade do repositório

O commit de origem é `739c2d8`. O repositório já continha `pontocerto/`, aplicação Python/FastAPI de inspeção de costura, incluindo pesos, histórico de treino e métricas. Esses arquivos foram preservados. Sua presença não comprova reprodutibilidade nem validação na empresa; não foram executados ou integrados nesta etapa. O frontend funciona sem instalar torch ou acessar câmera/OpenRouter.

O contexto não estava no Git: foi localizado na entrega local anterior e copiado integralmente para docs/CONTEXTO_PROJETO.md. Não foram alteradas as decisões desse documento nem tratados RF/RNF propostos como aprovação formal.

Consulte [próximas etapas e datasets](docs/CONTINUIDADE_E_DATASETS.md) e [verificação da entrega](docs/VERIFICACAO_F0.md). Esta branch reúne as extensões adicionais, preservando a aplicação original. Consulte docs/PUBLICACAO_BRANCH.md para o resumo e o comando de execução completo.

## Ampliação atual

A tela Produção agora permite registrar revisão final em memória, separando boas e retrabalho. Atualiza dashboard, gráfico e progresso/conclusão do lote; rejeita negativos, frações, excesso e lotes concluídos. Inclui filtros combinados. Consulte docs/ENTREGA_ATUAL.md para o resumo completo. Oito testes passaram.


## Executar todas as partes desta branch

Na pasta pontocerto, use o ambiente Python já preparado e execute:

    python scripts/11_rodar_completo.py

A raiz mantém câmeras/inspeção; /gestao abre lotes e produção; /financeiro abre o financeiro local; /produtividade abre o experimento UCI. Veja docs/FINANCEIRO_E_PRODUTIVIDADE_PUBLICA.md para configuração, comandos do Windows e limites. Os dados financeiros da empresa começam vazios; a demonstração fica separada.
