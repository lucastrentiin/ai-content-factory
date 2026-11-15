# Arquitetura

## Princípios
- **Monólito modular**: um backend Python com módulos bem separados (API, agentes, provedores, mídia,
  integrações) e processos distintos apenas onde há necessidade real (API, worker de produção, agendador).
  Pode ser dividido em serviços depois sem reescrita: as fronteiras já são os módulos.
- **Agentes como etapas rastreáveis**, não conversas livres entre IAs: cada agente é uma função com entrada,
  saída, status, erro, tentativas, custo e eventos persistidos em `agent_runs`.
- **Sem dependência de fornecedor**: toda chamada de IA passa pelo `ProviderRouter`.
- **Custo zero possível**: animação 2D própria, TTS local, música procedural.

## Serviços (docker-compose)
| Serviço | Papel |
|---|---|
| `proxy` (Caddy) | HTTPS automático; `/api/*` → API (inclui WebSocket); resto → web |
| `web` (Next.js) | Interface administrativa |
| `api` (FastAPI) | REST, WebSocket `/api/ws`, OAuth callbacks; roda migrations + seeds ao iniciar |
| `worker` (Celery) | Filas `render` (pipeline de produção) e `default` (pesquisa, ideias, publicação, métricas) |
| `beat` (Celery) | A cada minuto lê a tabela `workflows` (cron editável na interface) e dispara automações |
| `db` (PostgreSQL 16) | Dados; arquivos grandes nunca vão para o banco |
| `redis` | Broker, locks distribuídos, rate limit, eventos em tempo real (Pub/Sub) |
| `storage` (SeaweedFS) | Objetos S3: `channels/<id>/series/<id>/productions/<id>/<tipo>/…`, `characters/<id>/…` |
| `backup` | `pg_dump` diário com retenção |
| `n8n` (perfil opcional) | Orquestração visual chamando a API com token |

## Pipeline de produção (12 agentes)
```
story_writer → script_editor → fact_checker → character_designer → art_director → scene_planner
→ voice_director → audio_generator → visual_generator → video_editor → quality_controller → publisher
```
- **Orquestrador** (`app/pipeline/orchestrator.py`): lock Redis por produção (sem execução duplicada),
  retentativa com backoff exponencial para erros transitórios, `BudgetExceeded` → produção bloqueada com
  notificação, `RedoSteps` → o controle de qualidade reabre etapas (autocorreção, até 2 vezes) antes de mandar
  para revisão humana. Produções órfãs (worker reiniciado) são recuperadas pela automação `recover_stale`.
- **Modos**: manual (pausa após cada etapa), assistido (produz e aguarda aprovação), automático (publica
  conforme regras se não exigir aprovação).
- **Reprocessamento**: a partir de qualquer etapa; editar uma cena cria nova versão do roteiro e reprocessa.
  Cada clipe de cena tem um *hash* da especificação (plano, personagens, áudio, fundo, template): cenas
  inalteradas vêm do cache — trocar uma cena não re-renderiza o vídeo inteiro. Falas de TTS também são cacheadas.

## Motor de mídia
- **Rig 2D** (`media/animation/rig.py`): esqueleto articulado (stickman/cartoon) desenhado com Skia, 12 ações
  procedurais (andar, acenar, apontar, pular, encolher-se…), 7 expressões, piscar, boca guiada pela amplitude do
  áudio da própria fala (lip-sync aproximado).
- **Consistência visual**: a aparência do personagem é 100% derivada de `visual_spec` (persistido) — o mesmo
  personagem é idêntico em todos os vídeos. O QC compara o *hash* da ficha usada no render com a ficha atual.
  Para imagens por IA, a ficha gera uma âncora de prompt + seed.
- **Cenários** procedurais determinísticos (13 tipos × dia/pôr do sol/noite), gravados como asset e reutilizados;
  podem ser substituídos por fundos gerados por IA (`ai_backgrounds` no motor).
- **Render**: quadros Skia → FFmpeg (H.264) por cena; montagem com concat, voz, efeitos, música com *ducking*
  (sidechain), `loudnorm` −14 LUFS, legendas ASS com destaque palavra a palavra (tempos reais do ElevenLabs ou
  proporcionais), marca d'água e capa. Tudo parametrizado por **templates** (JSON) sem mudar código.
- **QC técnico e de conteúdo**: resolução, proporção, fps, duração × limites da plataforma, tamanho, áudio,
  loudness (EBU R128), silêncios, quadros pretos, legendas, cenas completas, sincronia de falas, coerência com o
  roteiro, continuidade de personagens, licenças de todos os materiais, integridade de imagens.

## Provedores e custos
- `ProviderRouter.call(kind, operation, fn, estimate)` → ordena candidatos pela estratégia do canal
  (qualidade/custo/velocidade/equilíbrio) e prioridade; simulados por último; verifica **limites de custo**
  (global/canal/motor/vídeo, diário/mensal) antes de cada operação paga — se estourar, tenta provedores
  gratuitos e, se não houver, bloqueia com motivo; **circuit breaker** (3 falhas → pausa 5 min); registra cada
  chamada em `api_usage` (unidades, custo estimado/efetivo, latência, sucesso).
- Credenciais criptografadas (Fernet) no banco; nunca retornam ao navegador (apenas mascaradas).

## Aprendizado
- Métrica composta por publicação: `log10(1+views) × (1 + 4·engajamento ponderado) × retenção`.
- `strategy_arms`: média, variância (Welford) e IC (t de Student) por dimensão (motor, estilo, formato, duração,
  plataforma, horário), só com publicações > 48 h. Braço só é **confiável** com amostra mínima.
- Otimização de pesos por canal: P(melhor) via amostragem da posterior normal, piso de exploração, variação
  máxima por rodada, `min_share`/`max_share`; registrada em `optimization_decisions` (aplicação automática ou
  manual).
- Testes A/B: variantes atribuídas em rodízio pela fábrica; vencedora só com teste t de Welch significativo.
- O histórico alimenta a pontuação de novas ideias (critério "histórico do canal").

## Modelo de dados (45 tabelas)
`users, api_tokens, audit_logs, notifications, system_logs, system_settings, platforms, content_engines,
content_categories, channels, channel_engines, social_accounts, trend_sources, trends, trend_snapshots, ideas,
idea_trends, universes, series, episodes, characters, character_assets, character_relationships,
character_appearances, locations, voices, assets, templates, scripts, script_versions, production_jobs,
agent_runs, scenes, render_jobs, publications, publication_metrics, strategy_arms, optimization_decisions,
experiments, experiment_variants, model_providers, provider_models, api_usage, cost_limits, workflows`.
`assets` unifica imagens/vídeos/áudios/música/efeitos/capas/legendas (com origem, licença, provedor e prompt);
"stories" é representado por `scripts`/`script_versions` (história completa + estrutura em cenas).

## Segurança
JWT em cookie httpOnly (SameSite=Lax) ou Bearer; tokens de API (apenas hash armazenado); papéis
admin/editor/leitura; Argon2; rate limit por IP (login mais restrito); validação Pydantic em todas as entradas;
idempotência (produções, publicações); locks distribuídos; auditoria de ações; `state` OAuth assinado (HMAC);
contêineres sem root; headers de segurança no Caddy; console de storage não exposto.
