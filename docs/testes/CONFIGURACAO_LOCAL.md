# Configuração local e orientação de testes

## Entrada operacional atual

Abra `http://127.0.0.1:8000/login`. No primeiro acesso, crie sua conta local com email e senha de pelo menos 8 caracteres, incluindo maiúscula, minúscula, número e símbolo. Não use a senha do banco. As contas são armazenadas em SQLite com derivação de senha e sessões expirando após 8 horas; não há senha padrão. A criação de outras contas exige sessão autenticada via `/api/auth/register`. Recuperação de senha por email ainda não foi implementada.

A inspeção real está em `/`, com webcam do servidor, câmera do aparelho e arquivo na mesma tela. Cada análise de arquivo gera um evento com foto em SQLite e no diretório de capturas. O histórico possui calendário e filtro de defeitos; a conferência humana é persistida. A câmera do aparelho exige permissão e contexto seguro. A câmera do servidor não é ligada automaticamente.

A navegação operacional não inclui financeiro, treinamento, modelo e evidências nem auditoria. Os registros internos de decisões permanecem para rastrear alterações. 

O projeto está dentro de um caminho longo no OneDrive. A instalação do PyTorch no `.venv` interno falhou pelo limite de caminhos do Windows. Nesta máquina, o ambiente funcional foi criado em `$env:TEMP\duas-marias-venv`; ele é temporário e poderá precisar ser recriado se a pasta temporária for limpa.

Na raiz do repositório, iniciar com:

```powershell
$pythonProjeto = Join-Path $env:TEMP 'duas-marias-venv\Scripts\python.exe'
.\Iniciar.ps1   # encontra sozinho o ambiente do TEMP
```

Para recriar esse ambiente: `python -m venv "$env:TEMP\duas-marias-venv"` e depois `& $pythonProjeto -m pip install -r requirements.txt`. Para encerrar o servidor no terminal, usar Ctrl+C. Não iniciar dois servidores na mesma porta.

## Supabase: primeiro passo de configuração

1. Abrir o projeto correto no painel Supabase. Usar um projeto de testes para esta rodada.
2. No SQL Editor, revisar e executar `supabase/schema.sql`. Conferir as tabelas criadas antes de continuar.
3. Em Storage, criar um bucket **privado** chamado `Capturas`, respeitando maiúsculas.
4. Em Connect, copiar a URI do **Session pooler**, porta 5432. Esse modo atende conexões IPv4. Usar a senha do banco, que é diferente da senha de login do aplicativo. Caracteres especiais na senha precisam estar codificados na URI; não altere o restante do endereço copiado.
5. Copiar `.env.example` para `.env` se o arquivo ainda não existir. Substituir os exemplos pelas credenciais locais, sem publicar valores no chat, em screenshots ou no Git:

```dotenv
SUPABASE_DB_URL=postgresql://USUARIO:SENHA_CODIFICADA@HOST_DO_SESSION_POOLER:5432/postgres
SUPABASE_URL=https://ID_DO_PROJETO.supabase.co
SUPABASE_SECRET_KEY=CHAVE_SECRETA_DO_PROJETO
SUPABASE_BUCKET=Capturas
```

6. Reiniciar o servidor. Abrir `http://127.0.0.1:8000/api/saude` e verificar banco configurado. Conferir a conexão na área de lotes/status do banco; “configurado” sozinho não prova que as credenciais foram aceitas.
7. Criar lote de inspeção fictício, colocá-lo em inspeção e testar gravação e recuperação de uma foto de defeito. Conferir a persistência após reiniciar.

Se houver senha recusada, revisar somente a URI local; se houver host não encontrado, conferir host e rede; se o banco gravar mas a foto falhar, conferir URL, chave, bucket e privacidade. O `.env` já é ignorado pelo Git. A chave secreta pertence ao backend e não deve virar variável `VITE_*`.

A integração de inspeção utiliza schema.sql. A gestão remota utiliza gestao.sql e GESTAO_STORAGE=supabase, conforme as instruções abaixo. As contas continuam locais.

Referências oficiais: [conexão ao Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres), [chaves de API](https://supabase.com/docs/guides/api/api-keys), [buckets e acesso](https://supabase.com/docs/guides/storage/buckets/fundamentals).

## Diagnóstico externo com IA

O modelo local de classificação funciona sem OpenRouter. Para diagnóstico externo, criar chave na conta OpenRouter e preencher apenas localmente `OPENROUTER_API_KEY` no `.env`; reiniciar o servidor e conferir `llm.configurado` em `/api/saude`. Não usar a chave de exemplo. Só enviar imagens autorizadas; a decisão técnica precisa de revisão humana.

Referência: [documentação oficial do OpenRouter](https://openrouter.ai/developers).

## Gestão e recebimento no Supabase

O novo módulo de gestão também pode persistir no Supabase. Execute `supabase/gestao.sql` no SQL Editor do projeto de teste e depois configure `GESTAO_STORAGE=supabase` no `.env`, mantendo `SUPABASE_DB_URL` com a URI correta. Reinicie o servidor. A base remota começa vazia; os cadastros da demonstração local não são copiados nem sobrescritos. Para voltar aos dados locais, use `GESTAO_STORAGE=local` e reinicie. Se o modo Supabase estiver selecionado e indisponível, o app não faz fallback silencioso para outra base.

O script da gestão armazena lotes, colaboradores, produção, recebimentos e decisões em um estado JSONB transacional no PostgreSQL. Essa persistência não é o Supabase Auth: as contas de acesso continuam no SQLite local desta instalação.

## Outlook da empresa

1. Solicitar ao administrador Microsoft 365 um aplicativo no Microsoft Entra ID e definir a caixa remetente da empresa.
2. Configurar a permissão Microsoft Graph **Mail.Send**, tipo **Application**, com consentimento administrativo. Restringir o aplicativo à caixa necessária por política de acesso ou RBAC do Exchange, conforme a configuração do tenant.
3. Preencher localmente no `.env`: `OUTLOOK_TENANT_ID`, `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET` e `OUTLOOK_SENDER`. Reiniciar o servidor. Não incluir credenciais em variáveis `VITE_*` nem no Git.
4. Em Gestão > Recebimento, selecionar um lote, informar grade esperada e recebida e checar aviamentos. A soma da grade esperada deve coincidir com o lote.
5. Conferir as divergências e o texto do aviso, informar o destinatário e clicar em **Confirmar envio pelo Outlook**. Nenhum email é enviado ao apenas salvar o recebimento. O teste automatizado substitui o cliente de envio e não transmite mensagens.
6. Se houver erro de rede após confirmar, conferir a caixa de enviados antes de repetir. Uma resposta aceita pelo Graph não comprova entrega ao destinatário.

Referências oficiais: [sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0), [acesso de aplicativo](https://learn.microsoft.com/en-us/entra/identity-platform/app-only-access-primer).

## Mobile

A versão mobile é uma PWA com manifesto, ícones e service worker. Quando o navegador permitir, usar **Instalar aplicativo** ou **Adicionar à tela inicial**. Ela depende do servidor; não há inferência offline. Fotos, APIs e páginas autenticadas não são guardadas no cache do service worker. Para usar de outro dispositivo, é necessário publicar o servidor em HTTPS numa rede acessível, configurar a infraestrutura e validar permissões de câmera. O localhost de um celular aponta para o próprio celular, não para este PC. Não foi aberto acesso externo nesta rodada e nenhum app foi enviado a lojas.

## Ordem sugerida

## Foto da OP e exportação de relatórios

Para a leitura local de OP, instale `requirements-ocr.txt` no mesmo Python do servidor. A leitura não exige chave nem envia a foto a serviço externo. Em Recebimento, selecionar a foto, conferir o texto e preencher ou corrigir os campos. A leitura não cadastra o lote: o botão de cadastro exige a conferência dos dados. Tabelas e manuscritos podem não ser extraídos; neste caso, preencher manualmente a grade PP/P/M/G/GG ao lado da foto.

A tela Relatórios da inspeção oferece resumo por dia e download PDF de até 500 eventos recentes no período. A Gestão também oferece download de relatório de produção. Esses PDFs exigem sessão autenticada e são gerados no momento do download. O pacote reportlab faz parte de requirements.txt.

Para repetir a regressão Python, executar `python scripts/testar.py` após instalar as dependências de execução, OCR e documentação usadas nos testes. No frontend, executar `npm.cmd test -- --maxWorkers=1 --no-file-parallelism --testTimeout=20000` e `npx.cmd tsc --noEmit`.

Primeiro criar o acesso local e repetir inspeção, revisão humana, cadastro, recebimento e redistribuição. Depois configurar e testar Supabase e Outlook. Por fim, validar câmera, instalação e uso no celular real. A fotografia original de costura torta precisa de conferência humana, sem assumir acerto do modelo.
