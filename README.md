# Urna Cidadã — site independente

Aplicação independente de ChatGPT Sites, com página pública `/` e administração `/admin`. Uma votação comunitária por instalação: o administrador cadastra os candidatos, salva, inicia e encerra. A configuração fica imutável após a abertura; o encerramento é definitivo. Não cria eleições públicas oficiais, não implementa distribuição proporcional de cadeiras nem comprova identidade.

## O que está implementado

- Senha do administrador configurada no servidor; sessão HttpOnly de uma hora e proteção de origem/CSRF.
- Cadastro de título, números de 2 a 5 dígitos, nome e grupo/partido opcional.
- Validação matemática de CPF e apenas um voto por CPF normalizado, inclusive sob requisições simultâneas.
- Tela de conferência, correção, branco, nulo, confirmação e FIM.
- Banco SQLite compartilhado entre todos os visitantes. Transação atômica para autorização e totalização.
- Resultados públicos somente após encerramento, com contagens, percentuais e indicação de empate.
- Somente totais agregados e HMACs de CPF; não grava cédulas individuais, CPF original, nome de eleitor, IP ou horário de voto no banco.

## Publicar na Railway ou em outra hospedagem Docker

1. Envie esta pasta a um repositório privado da SUA conta ou use a publicação de diretório da hospedagem. O Dockerfile usa Python sem dependências externas.
2. Crie um serviço a partir dessa fonte e configure **um único processo/réplica**.
3. Conecte um volume persistente em `/data`. Não use armazenamento efêmero: reinícios apagariam a votação e a trava de CPF. Consulte custos e disponibilidade no plano da hospedagem antes de contratar.
4. Configure `DATABASE_PATH=/data/urna.sqlite`, `PORT=8080`, `ADMIN_PASSWORD` com pelo menos 16 caracteres e `APP_SECRET` aleatório com pelo menos 32 caracteres. Gere segredos no gerenciador da hospedagem; não inclua segredos em código, Git ou conversa.
5. Gere o domínio público HTTPS do serviço e configure `PUBLIC_URL` com esse endereço exato, sem barra final. Depois reinicie o serviço. A verificação de origem bloqueia mutações se essa variável estiver incorreta.
6. Abra `/admin`, entre com a senha definida, cadastre e salve candidatos. Confira a página pública antes de iniciar. Faça ensaio em instalação separada: não há botão para apagar uma votação real.
7. Para domínio próprio, registre um domínio em sua conta e associe-o nas configurações da hospedagem. Atualize `PUBLIC_URL` para a origem principal HTTPS. Não é necessário usar domínio chatgpt.site ou login do ChatGPT.

Mantenha a mesma `APP_SECRET` durante a votação: trocá-la altera as assinaturas de CPF e permite duplicações. Proteja backups e o volume persistente. O usuário do container (UID 10001) deve ter escrita em `/data`. Restrinja acesso aos segredos e ao banco; use HTTPS e desative logs de corpo de requisições no proxy. Valide política e retenção de logs da hospedagem.

## Limites de privacidade e identidade

Não existe promessa de anonimato absoluto: a infraestrutura recebe CPF e escolha durante o processamento, e o operador que controla o código/servidor precisa ser confiável. Hospedagem e proxies podem registrar IPs e metadados técnicos. O aplicativo não mantém relação entre HMAC de CPF e candidato, mas isso não equivale a anonimato criptográfico verificável. Totais de grupos pequenos também podem permitir inferências.

CPF com dígitos verificadores corretos não prova titularidade nem elegibilidade. Uma pessoa pode informar CPF alheio; esta versão não integra identidade oficial, SMS, e-mail ou verificação documental. HMAC de CPF é dado pseudonimizado e deve ser protegido. Defina finalidade, aviso de privacidade, período de retenção e processo de atendimento adequado ao contexto antes de coletar CPFs reais.

## Executar e testar

Python 3.12 ou superior. Configure variáveis por um gerenciador de segredos ou shell local e execute `python server.py`. Para desenvolvimento, `PUBLIC_URL=http://localhost:8080`. Não há segredos padrão.

`python -m unittest discover -s tests -v`

Os testes cobrem validação de CPF, bloqueio concorrente de duplicações, rollback de votos inválidos, abertura/encerramento, persistência de resultado, autenticação, origem, CSRF e logout. A interface ainda precisa de verificação visual no navegador da hospedagem.
