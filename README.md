# AI Content Factory

Plataforma autônoma de criação, produção e publicação de vídeos curtos (TikTok, Instagram Reels, YouTube Shorts).
Ela pesquisa tendências, gera e pontua ideias, escreve roteiros em cenas, cria personagens persistentes, anima,
narra, renderiza, revisa a qualidade, publica e aprende com os resultados — com você no controle de cada etapa.

> **Status:** fundação + primeiro fluxo completo funcionando de ponta a ponta (tendência → ideia → roteiro →
> personagens → cenas → narração → vídeo 1080×1920 → controle de qualidade → aprovação → publicação/exportação),
> com interface administrativa, API, filas, agendador, custos, analytics e testes. Veja o [backlog](docs/BACKLOG.md).

## O que funciona sem nenhuma chave de API

| Parte | Sem credenciais | Com credenciais |
|---|---|---|
| Roteiros e ideias | Gerador de modelos interno — **SIMULADO**, marcado na interface | Claude, OpenAI, OpenRouter, Ollama local |
| Animação 2D (stickman/cartoon), cenários, câmera, lip-sync | Motor próprio (Skia + FFmpeg), sem custo | — |
| Imagens / vídeo por IA | Cenas caem para animação 2D | OpenAI Images, Stability, Replicate (FLUX, Kling, MiniMax) |
| Voz | eSpeak NG local (qualidade básica) | ElevenLabs, OpenAI TTS |
| Música e efeitos | Gerados proceduralmente (sem direitos de terceiros) | — |
| Tendências | Importação manual; Google Trends/Notícias e Reddit (RSS/JSON públicos) | YouTube Data API |
| Publicação | Assistida: pacote ZIP (vídeo, capa, legenda) + registro manual do link | APIs oficiais via OAuth |
| Métricas | Registro manual | YouTube Analytics, TikTok, Instagram Insights |

Conteúdo produzido por provedores simulados é sempre identificado e curiosidades sem fontes verificadas vão
obrigatoriamente para revisão humana.

## Início rápido (servidor Ubuntu com Docker)

```bash
git clone https://github.com/lucastrentiin/ai-content-factory.git && cd ai-content-factory
cp .env.example .env    # preencha os campos [OBRIGATÓRIO]
docker compose up -d --build
```

Abra `http://IP_DO_SERVIDOR` e entre com `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD`.
Guia completo (domínio, HTTPS, firewall, backups, atualização): **[docs/DEPLOY_UBUNTU.md](docs/DEPLOY_UBUNTU.md)**.

Primeiros passos na interface:
1. **Canais → Novo canal** (nicho, idioma, estilo, autonomia, vídeos/dia).
2. **Configurações → Provedores**: cole a chave de pelo menos um LLM (recomendado: Anthropic) — opcional.
3. **Ideias → Gerar ideias** e **Produzir** a melhor. Acompanhe em **Produção** (película das 12 etapas) e **Monitor**.
4. **Aprovar e agendar** o vídeo. Conecte as contas em **Canais → Contas conectadas** para publicar pela API.

## Arquitetura (resumo)

```
Caddy (HTTPS) ─┬─ Next.js (interface)
               └─ FastAPI (REST + WebSocket) ── PostgreSQL
                       │                    └── SeaweedFS (S3: vídeos, áudios, imagens)
                       └── Redis ── Celery worker (pipeline de agentes, render FFmpeg/Skia)
                                └── Celery beat (automações cron lidas do banco)
```

Detalhes, decisões e modelo de dados: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.
Provedores, credenciais e alternativas: **[docs/PROVIDERS.md](docs/PROVIDERS.md)**.

## Desenvolvimento local

Requisitos: Python 3.12+, Node 22, PostgreSQL 16, Redis 7, FFmpeg, espeak-ng, libegl1.

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cat > .env <<'X'
DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/factory
REDIS_URL=redis://localhost:6379/0
LOG_JSON=false
X
.venv/bin/alembic upgrade head && .venv/bin/python -m app.cli seed
.venv/bin/uvicorn app.main:app --reload --port 8000          # API em :8000/api/docs
.venv/bin/celery -A app.worker.celery_app worker -Q default,render   # outro terminal
.venv/bin/celery -A app.worker.celery_app beat                        # agendador (opcional)

# frontend
cd frontend && npm install && BACKEND_URL=http://localhost:8000 npm run dev   # :3000

# fluxo completo pela CLI, sem interface
.venv/bin/python -m app.cli example-channel && .venv/bin/python -m app.cli produce --engine horror
```

### Testes

```bash
createdb factory_test    # banco dedicado; os testes recriam o schema
cd backend && .venv/bin/pytest -q
```

28 testes cobrem: produção de ponta a ponta (vídeo real 1080×1920 com áudio), cache de cenas e
re-renderização de uma única cena, modo manual, revisão obrigatória de curiosidades, fallback entre provedores,
circuit breaker, bloqueio por orçamento, permissões, proteção de credenciais, agendamento, publicação assistida,
aprendizado com amostra mínima, teste A/B com significância e estatística.

## Estrutura

```
backend/   FastAPI, modelos, migrations (Alembic), agentes, provedores, motor de mídia, integrações, testes
frontend/  Next.js 15 (App Router, TypeScript, Tailwind 4)
deploy/    Caddyfile e script de backup
docs/      Arquitetura, implantação, provedores, backlog
```
