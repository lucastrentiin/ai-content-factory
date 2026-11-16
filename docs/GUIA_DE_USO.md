# Guia de uso — do zero ao primeiro vídeo

Este guia assume que você vai usar o **Claude pela sua assinatura (copiar e colar)**, sem chave de API.

## Parte 1 — Instalar no servidor (uma vez)

Você precisa de um servidor Ubuntu 22.04 ou 24.04 (mínimo 4 vCPU, 8 GB de RAM, 60 GB de disco) e acesso SSH.

1. **Entre no servidor** pelo terminal: `ssh usuario@IP_DO_SERVIDOR`
2. **Instale o Docker e o Git** (copie o bloco inteiro):
   ```bash
   sudo apt-get update && sudo apt-get install -y ca-certificates curl git
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER && newgrp docker
   ```
3. **Baixe o projeto:**
   ```bash
   git clone -b claude/ai-content-factory-px0x0j https://github.com/lucastrentiin/ai-content-factory.git
   cd ai-content-factory
   ```
   (Depois que a branch for unida à principal, basta `git clone https://github.com/lucastrentiin/ai-content-factory.git`.)
   Se o repositório for privado, o Git vai pedir usuário e um *token* do GitHub como senha
   (GitHub → Settings → Developer settings → Personal access tokens).
4. **Crie a configuração com senhas aleatórias:**
   ```bash
   cp .env.example .env
   sed -i "s|^SECRET_KEY=$|SECRET_KEY=$(openssl rand -hex 32)|" .env
   sed -i "s|^SECRETS_ENCRYPTION_KEY=$|SECRETS_ENCRYPTION_KEY=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')|" .env
   sed -i "s|^POSTGRES_PASSWORD=$|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env
   sed -i "s|^S3_SECRET_KEY=$|S3_SECRET_KEY=$(openssl rand -hex 16)|" .env
   nano .env
   ```
   No `nano`, preencha `FIRST_ADMIN_EMAIL` (seu e-mail) e `FIRST_ADMIN_PASSWORD` (sua senha de acesso).
   Se tiver domínio, preencha também `SITE_ADDRESS`, `PUBLIC_BASE_URL`, `FRONTEND_URL` e `CORS_ORIGINS`
   (veja [DEPLOY_UBUNTU.md](DEPLOY_UBUNTU.md)). Salve com `Ctrl+O`, `Enter`, `Ctrl+X`.
5. **Libere o firewall e suba a fábrica** (a primeira vez leva alguns minutos):
   ```bash
   sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw --force enable
   docker compose up -d --build
   docker compose ps
   ```
   Todos os serviços devem aparecer como `Up` / `healthy`.
6. **Abra no navegador:** `http://IP_DO_SERVIDOR` e entre com o e-mail e a senha do passo 4.

## Parte 2 — Configurar (uma vez)

1. **Ative o Claude da sua assinatura:** na Visão geral, clique em **"Usar o Claude da minha assinatura"**.
   A partir daí, toda vez que a fábrica precisar do Claude ela mostra o prompt para você copiar.
2. **Crie um canal:** menu **Canais → Novo canal**.
   - *Nicho*: ex. "lendas urbanas brasileiras fictícias".
   - *Estilo visual*: Cartoon 2D (personagens coloridos) ou Stickman.
   - *Autonomia*: **Assistido** (a fábrica produz e espera você aprovar). Recomendado para começar.
   Depois, na página do canal, ajuste os **horários de publicação**, os **motores** que o canal pode usar
   (Storytelling, Terror, Comédia…) e salve.
3. **(Opcional) Vozes melhores:** a voz padrão é robótica (eSpeak). Com uma conta paga da ElevenLabs,
   cole a chave em **Configurações → Provedores → ElevenLabs → Configurar** e cadastre vozes em **Vozes**.
   Clique em **Testar** para ouvir.
4. **(Opcional) Limite de gastos:** em **Custos**, os limites já vêm configurados (US$ 10/dia, US$ 150/mês,
   US$ 2/vídeo). Ajuste quando usar serviços pagos.

## Parte 3 — Fazer um vídeo

**Caminho A — a partir de ideias**
1. **Ideias → Gerar ideias**, escolha o canal e clique em **Gerar**.
2. Aparecem 3 passos: **Copiar prompt** → **Abrir o Claude** (cole o prompt numa conversa nova e envie) →
   copie a resposta inteira do Claude (botão de copiar embaixo da resposta) → cole no campo → **Enviar resposta**.
3. As ideias aparecem com nota. Clique na melhor → **Produzir**.
4. A produção abre e pede o **roteiro**: repita os 3 passos (um único copiar e colar por vídeo).
5. Pronto: a fábrica cria os personagens, as vozes, anima, legenda e confere a qualidade (1 a 3 minutos).
   A **película** no topo mostra cada etapa ficando verde.

**Caminho B — direto:** **Produção → Nova produção**, escolha canal e motor, **Iniciar produção** e siga do passo 4.
Também dá para escrever o roteiro você mesmo no campo "Roteiro próprio".

Se o Claude responder com texto fora do formato, a plataforma avisa e reabre o pedido: peça
"responda só com o JSON" e cole de novo.

Colar é a **única** etapa manual. Análise de tendências, revisão do roteiro e verificação de fatos são automáticas.
Nas curiosidades, o Claude informa um link de fonte para cada fato e a plataforma abre cada link: se todos existirem,
o vídeo segue direto; se algum estiver quebrado ou faltar, o vídeo vai para revisão mostrando qual fato.

## Parte 4 — Revisar e publicar

1. Na página da produção, assista ao vídeo. Aba **Cenas**: **Editar cena** (muda falas/câmera e refaz só o
   que mudou), **Renderizar de novo** ou **Refazer áudio**.
2. Clique em **Aprovar e agendar**: as publicações entram nos próximos horários livres do canal.
3. Sem contas conectadas, a publicação é **assistida**: em **Publicações**, use **Baixar pacote**
   (vídeo, capa e legenda prontos), publique no app e depois **Marcar como publicado** colando o link.
4. Uns dias depois, **Registrar métricas** (views, curtidas…) para a fábrica aprender o que funciona —
   ou conecte as contas oficiais (veja [PROVIDERS.md](PROVIDERS.md)) para coletar sozinha.

## Rotina diária sugerida (10–15 min)

1. Abra a **Visão geral** → painel "Respostas do Claude esperando você" → responda os pedidos.
2. **Produção → filtro "Precisa de você"** → aprove ou ajuste os vídeos.
3. **Publicações** → publique os pacotes do dia e registre os links.
4. Uma vez por semana: **Analytics** para ver o que performa melhor.

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| Página não abre | `docker compose ps` e `docker compose logs -f api web` no servidor |
| Produção "Falhou" | Abra a produção → clique no quadro vermelho da película para ver o erro → **Retomar de onde parou** |
| Nada acontece após colar | Tela **Monitor**: confira se há um worker ativo; `docker compose restart worker` |
| Atualizar a plataforma | `git pull && docker compose up -d --build` |
| Esqueci a senha | `make admin EMAIL=seu@email PASSWORD=novasenha` |
