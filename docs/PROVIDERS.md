# Provedores, credenciais e alternativas

Status de cada provedor aparece em **Configurações → Provedores**: *Configurado*, *Faltam credenciais*,
*Indisponível*, *Simulado*, *Pausado após falhas*. Chaves podem ser coladas na interface (criptografadas) ou
definidas no `.env`. Preços cadastrados são **estimativas editáveis** — confira a tabela oficial.

## Linguagem (ideias, roteiros, revisão, metadados, verificação de fatos)
| Provedor | O que é preciso | Observações |
|---|---|---|
| **Anthropic Claude** (padrão: `claude-opus-5-5`) | `ANTHROPIC_API_KEY` (console.anthropic.com) | SDK oficial; esforço `medium` configurável; *fallback* no servidor em caso de recusa. Para reduzir custo, selecione `claude-sonnet-5-5` ou `claude-haiku-5-5` como modelo padrão. |
| OpenAI | `OPENAI_API_KEY` | API Chat Completions |
| OpenRouter | `OPENROUTER_API_KEY` | Acesso a dezenas de modelos com uma chave |
| Ollama (local, grátis) | Rodar Ollama e definir `base_url` (ex.: `http://host.docker.internal:11434/v1`) | Qualidade depende do modelo; sem custo de API |
| **Claude pela assinatura (copiar e colar)** | sua conta claude.ai (Pro/Max) | Sem API: a plataforma mostra o prompt, você cola no claude.ai e traz a resposta — **é a única etapa manual**. Um colar por vídeo (o roteiro já traz título, legenda, hashtags e, em curiosidades, os fatos com links de fonte) e um por geração de ideias. Todo o resto é automático: análise de tendências por regras (categoria, potencial, temas sensíveis bloqueados), revisão do roteiro por checagens automáticas e verificação de fatos que abre cada link de fonte — o vídeo só para para revisão se algum fato ficar sem fonte acessível. |
| Gerador de modelos | nada | **SIMULADO** — não é IA; só para testar o fluxo |

## Imagens (cenas cinematográficas, fundos por IA)
| Provedor | Credencial | Notas |
|---|---|---|
| Replicate (FLUX schnell/pro) | `REPLICATE_API_TOKEN` | Mais barato; verifique a licença de cada modelo |
| OpenAI Images (`gpt-image-1`) | `OPENAI_API_KEY` | |
| Stability AI (Core/Ultra) | `STABILITY_API_KEY` | |
Sem provedor de imagem, cenas `ai_image` usam a animação 2D própria. Ative fundos por IA no motor com
`"ai_backgrounds": true`.

## Vídeo por IA
Replicate (`minimax/video-01`, `kwaivgi/kling-v2.1`, outros via `input_map` na configuração).
Ative por motor com `"ai_video_scenes": [0]` (ex.: só a cena de abertura, para controlar custo).

## Voz (TTS)
| Provedor | Credencial | Notas |
|---|---|---|
| ElevenLabs | `ELEVENLABS_API_KEY` | Melhor qualidade em PT-BR, tempos por palavra (legendas exatas). Uso comercial em planos pagos. Cadastre vozes do catálogo/biblioteca licenciada em **Vozes** (o catálogo da conta aparece automaticamente). |
| OpenAI TTS (`gpt-4o-mini-tts`) | `OPENAI_API_KEY` | Emoção via instruções. Informe ao público que a voz é sintética. |
| eSpeak NG | nada (incluso na imagem) | Gratuito, robótico; ótimo para testes |
**Não é permitido** clonar ou imitar vozes de pessoas reais sem autorização. Cada voz tem campo de licença.

## Música e efeitos
Gerados proceduralmente pela plataforma (licença: gerado internamente). Você pode enviar trilhas e efeitos
próprios ou licenciados pela **Biblioteca** — materiais com licença "desconhecida" são bloqueados no QC.

## Tendências
| Fonte | Credencial | Notas |
|---|---|---|
| Google Trends (RSS diário BR) | nenhuma | Feed público |
| Google Notícias (RSS) | nenhuma | Geral e por tópico |
| YouTube em alta | `YOUTUBE_API_KEY` | YouTube Data API v3 (cota gratuita diária) |
| Reddit r/brasil | nenhuma | JSON público; pode ser limitado pelo Reddit — considere OAuth (backlog) |
| TikTok Creative Center / Instagram | — | **Sem API pública oficial.** Não fazemos raspagem; use **Tendências → Importar** |

## Publicação
| Plataforma | Credenciais (`.env`) | Requisitos e limitações |
|---|---|---|
| YouTube Shorts | `GOOGLE_OAUTH_CLIENT_ID/SECRET` | Google Cloud: ative YouTube Data API v3 e YouTube Analytics API; tela de consentimento OAuth. **Projetos não verificados só enviam vídeos privados** até passar na auditoria do Google. Miniatura personalizada exige conta verificada. Marcamos `containsSyntheticMedia=true`. |
| TikTok | `TIKTOK_CLIENT_KEY/SECRET` | App no TikTok for Developers com *Content Posting API* (Direct Post) e escopos `video.publish`, `video.upload`, `video.list`, `user.info.basic`. **Antes da auditoria do app, só é possível publicar como privado (SELF_ONLY).** Após aprovação, marque "App auditado" na conta. Marcamos `is_aigc=true`. |
| Instagram Reels | `META_APP_ID/SECRET` | Conta Profissional ligada a uma Página do Facebook; app Meta com Instagram Graph API e permissões `instagram_content_publish`, `instagram_basic`, `instagram_manage_insights`, `pages_show_list` (App Review para produção). **O vídeo precisa estar em URL pública**: configure `FILES_ADDRESS` e `S3_PUBLIC_ENDPOINT_URL`. |
Sem conta conectada (ou se a plataforma recusar), a publicação vira **assistida**: notificação + pacote ZIP com
vídeo, capa e legenda; depois registre o link em **Publicações → Marcar como publicado**.
