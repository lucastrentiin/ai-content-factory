# Backlog

Itens conhecidos, em ordem aproximada de prioridade. Nada foi descartado silenciosamente.

## Validações pendentes com credenciais reais
As integrações abaixo foram implementadas seguindo a documentação oficial, mas **não puderam ser executadas
contra os serviços reais** neste ambiente (sem chaves). Validar ao configurar:
- [ ] Anthropic, OpenAI, OpenRouter, Ollama (geração JSON de roteiros longos; ajustar `max_tokens`/esforço).
- [ ] ElevenLabs (`/with-timestamps`), OpenAI TTS; Replicate (imagem e vídeo), Stability, OpenAI Images.
- [ ] YouTube upload resumível + Analytics; TikTok Direct Post + status; Instagram container/publish + insights.
- [ ] Google Trends RSS / Google News RSS / Reddit: os *parsers* têm testes com amostras, mas a rede deste
      ambiente bloqueia essas fontes; validar formato atual dos feeds em produção.

## Produção audiovisual
- [ ] Remotion como renderizador alternativo (templates React para layouts complexos/motion graphics).
- [ ] Transições cruzadas (xfade) entre cenas; hoje: corte ou *fade* pelo preto.
- [ ] Alinhamento forçado de legendas (Whisper/WhisperX) para provedores TTS sem tempos por palavra.
- [ ] Sincronização labial por fonemas (visemas) em vez de amplitude.
- [ ] Rig 2D: mais ações (correr pelo cenário, sentar em objetos, interações entre personagens), props/objetos
      animados, roupas por episódio, múltiplos ângulos de câmera.
- [ ] Consistência de personagem em imagens por IA usando imagens de referência (IP-Adapter/FLUX Redux/
      ferramentas de "character reference" dos provedores) — hoje: âncora textual + seed.
- [ ] Biblioteca de músicas/efeitos licenciados com busca por clima; *stems* e mixagem por cena.
- [ ] Geração de múltiplos formatos (16:9, 1:1) a partir da mesma produção.
- [ ] Piper TTS local (neural, gratuito) como alternativa ao eSpeak.

## Conteúdo e inteligência
- [ ] Verificação de fatos com busca na web (ferramenta de busca do provedor LLM) e citação obrigatória.
- [ ] Moderação automática de roteiros (temas sensíveis, marcas, pessoas reais) antes da produção.
- [ ] Análise de vídeos de referência (transcrição/estrutura de vídeos em alta) para extrair padrões de gancho.
- [ ] Proposta automática de novos motores pelo motor Experimental (hoje: criação manual na interface).
- [ ] Planejamento de temporadas de séries (arcos) e bíblia da série gerada/atualizada por LLM.
- [ ] Geração de variantes A/B de capa e título publicadas como testes nativos das plataformas (quando houver API).

## Plataforma
- [ ] Reddit via OAuth; X/Twitter e Kwai como fontes/destinos (avaliar APIs oficiais).
- [ ] Prometheus/Grafana (métricas de filas, tempo de render, custo) e alertas por e-mail/Telegram.
- [ ] Multi-tenant (vários clientes/organizações) e permissões por canal.
- [ ] Rotação da `SECRETS_ENCRYPTION_KEY` com re-criptografia.
- [ ] Testes end-to-end da interface (Playwright) no CI; pipeline de CI no GitHub Actions.
- [ ] Fila com prioridades e cotas por canal; workers de render em máquinas separadas (GPU para IA local).
- [ ] Backup automático do storage de mídia para destino externo (S3/B2).
