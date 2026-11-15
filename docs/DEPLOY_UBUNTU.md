# Implantação em servidor Ubuntu (22.04 / 24.04)

## Requisitos
- 4 vCPU, 8 GB RAM, 60 GB de disco (renderização usa CPU; mais núcleos = mais vídeos simultâneos).
- Portas 80 e 443 liberadas. Um domínio apontando para o servidor (recomendado, para HTTPS e OAuth).

## 1. Docker
```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER && newgrp docker
```

## 2. Código e configuração
```bash
git clone https://github.com/lucastrentiin/ai-content-factory.git && cd ai-content-factory
cp .env.example .env
# gere os segredos:
sed -i "s|^SECRET_KEY=$|SECRET_KEY=$(openssl rand -hex 32)|" .env
sed -i "s|^SECRETS_ENCRYPTION_KEY=$|SECRETS_ENCRYPTION_KEY=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')|" .env
sed -i "s|^POSTGRES_PASSWORD=$|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env
sed -i "s|^S3_SECRET_KEY=$|S3_SECRET_KEY=$(openssl rand -hex 16)|" .env
nano .env   # defina FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD e, se tiver domínio, as URLs abaixo
```
Com domínio (HTTPS automático via Let's Encrypt):
```
SITE_ADDRESS=fabrica.seudominio.com
PUBLIC_BASE_URL=https://fabrica.seudominio.com
FRONTEND_URL=https://fabrica.seudominio.com
CORS_ORIGINS=https://fabrica.seudominio.com
```
> Guarde `SECRETS_ENCRYPTION_KEY` com segurança: sem ela, as credenciais salvas no banco não podem ser lidas.

## 3. Subir
```bash
docker compose up -d --build
docker compose ps           # todos "healthy"/"Up"
curl -s localhost/api/health/ready
```
Acesse `https://fabrica.seudominio.com` (ou `http://IP`). A API documentada fica em `/api/docs`.

## 4. Firewall
```bash
sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw enable
```
PostgreSQL, Redis e o storage não são expostos. n8n (opcional) fica em `127.0.0.1:5678` — use túnel SSH.

## 5. Operação
| Tarefa | Comando |
|---|---|
| Logs (JSON) | `docker compose logs -f api worker beat` |
| Atualizar | `git pull && docker compose up -d --build` (migrations rodam sozinhas) |
| Mais render paralelo | `WORKER_CONCURRENCY=4` no `.env` ou `docker compose up -d --scale worker=2` |
| Backup manual | `make backup` (automático diário em `./backups`, retenção `BACKUP_RETENTION_DAYS`) |
| Restaurar | `make restore FILE=backups/factory_AAAAMMDD_HHMMSS.sql.gz` |
| Novo admin / senha | `make admin EMAIL=voce@x.com PASSWORD=...` |
| n8n | `docker compose --profile n8n up -d` |

Backup dos arquivos de mídia: o volume `objectdata` (SeaweedFS). Ex.:
`docker run --rm -v content-factory_objectdata:/d -v $PWD/backups:/b alpine tar czf /b/media_$(date +%F).tgz -C /d .`

Para usar S3 externo (AWS S3, Cloudflare R2, Backblaze), defina `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`,
`S3_SECRET_KEY`, `S3_BUCKET` no serviço `x-backend` do compose e remova o serviço `storage`.

## 6. Monitoramento
- `GET /api/health` (liveness) e `GET /api/health/ready` (banco, Redis, storage, FFmpeg) — use em Uptime Kuma,
  Healthchecks.io etc.
- Tela **Monitor**: workers ativos, filas, agentes em execução, falhas recentes, eventos ao vivo.
- Notificações na interface para orçamento, falhas, revisões e publicações.

## 7. Publicação real (OAuth)
Em cada app de desenvolvedor, cadastre o redirect `https://SEU_DOMINIO/api/oauth/<youtube|tiktok|instagram>/callback`,
preencha as chaves no `.env`, reinicie (`docker compose up -d`) e, na interface, **Canais → Contas conectadas →
Conectar**. Requisitos e limitações de cada plataforma em [PROVIDERS.md](PROVIDERS.md).
