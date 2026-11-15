"""Dados de configuração iniciais (idempotente). Não cria conteúdo fictício: apenas plataformas, motores, provedores,
vozes locais, templates, fontes de tendências, automações, limites e o primeiro administrador."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import (
    ContentEngine,
    CostLimit,
    ModelProvider,
    Platform,
    ProviderModel,
    Template,
    TrendSource,
    User,
    Voice,
    Workflow,
)

PLATFORMS = [
    dict(key="youtube", name="YouTube Shorts", min_duration_s=3, max_duration_s=180, ideal_duration_s=45, max_title_len=100,
         max_description_len=5000, max_hashtags=5, max_file_mb=2000, config={"api": "YouTube Data API v3"}),
    dict(key="tiktok", name="TikTok", min_duration_s=3, max_duration_s=600, ideal_duration_s=40, max_title_len=150,
         max_description_len=2200, max_hashtags=5, max_file_mb=4000, config={"api": "Content Posting API"}),
    dict(key="instagram", name="Instagram Reels", min_duration_s=3, max_duration_s=900, ideal_duration_s=35, max_title_len=100,
         max_description_len=2200, max_hashtags=5, max_file_mb=300, config={"api": "Instagram Graph API"}),
]

ENGINES = [
    dict(key="storytelling", name="Storytelling", engine_type="storytelling", color="#a78bfa",
         description="Histórias narradas surpreendentes, emocionantes, de superação e com finais inesperados.",
         config={"editorial_rules": "Gancho forte em 2s; reviravolta clara; final memorável; sem violência gráfica.",
                 "tone": "envolvente e emocional", "formats": ["narrated_story", "dialogue_story", "pov"],
                 "visual_styles": ["stickman", "cartoon", "cinematic"], "default_visual_mode": "animation_2d",
                 "durations": {"min": 30, "target": 45, "max": 60}, "scene_count": [4, 8], "requires_fact_check": False}),
    dict(key="series", name="Séries e Novelas", engine_type="series", color="#f472b6",
         description="Episódios com continuidade, personagens recorrentes e ganchos; cada episódio atrai novos espectadores.",
         config={"editorial_rules": "Recapitule em 1 frase; avance a trama; termine com gancho; personalidade consistente.",
                 "tone": "dramático com humor leve", "formats": ["episode", "dialogue_story"], "visual_styles": ["cartoon", "stickman"],
                 "default_visual_mode": "animation_2d", "durations": {"min": 40, "target": 55, "max": 75}, "scene_count": [5, 8]}),
    dict(key="comedy", name="Comédia e Entretenimento", engine_type="comedy", color="#fbbf24",
         description="Esquetes, POV, humor absurdo, situações cotidianas e personagens recorrentes.",
         config={"editorial_rules": "Setup rápido, escalada, punchline nos últimos 3s; humor sem ofender grupos.",
                 "tone": "leve e absurdo", "formats": ["sketch", "pov", "dialogue_story"], "visual_styles": ["stickman", "cartoon"],
                 "default_visual_mode": "animation_2d", "durations": {"min": 20, "target": 30, "max": 45}, "scene_count": [3, 6]}),
    dict(key="horror", name="Terror, Suspense e Mistério", engine_type="horror", color="#ef4444",
         description="Lendas fictícias, mistérios, suspense psicológico, analog horror e relatos narrados.",
         config={"editorial_rules": "Atmosfera > choque; sem gore; lendas sempre fictícias e identificadas como ficção.",
                 "tone": "sombrio e tenso", "formats": ["narrated_story", "analog_horror", "relato"], "visual_styles": ["stickman", "cartoon", "cinematic"],
                 "default_visual_mode": "animation_2d", "durations": {"min": 35, "target": 50, "max": 70}, "scene_count": [4, 7],
                 "speech_rate": 0.95}),
    dict(key="curiosity", name="Curiosidades e Documentários", engine_type="curiosity", color="#22d3ee",
         description="Fatos, história, ciência, tecnologia e explicações rápidas — com verificação de fontes.",
         config={"editorial_rules": "Somente fatos verificáveis com fonte; sem exageros; corrigir mitos.",
                 "tone": "curioso e didático", "formats": ["explainer", "list", "documentary"], "visual_styles": ["cartoon", "cinematic"],
                 "default_visual_mode": "animation_2d", "durations": {"min": 30, "target": 45, "max": 60}, "scene_count": [4, 7],
                 "requires_fact_check": True}),
    dict(key="experimental", name="Experimental e Tendências", engine_type="experimental", color="#34d399",
         description="Testa formatos novos detectados nas tendências e propõe novos motores.",
         config={"editorial_rules": "Adapte o que torna a tendência interessante, nunca copie; teste hipóteses claras.",
                 "tone": "atual e ousado", "formats": ["trend_remix", "pov", "sketch", "narrated_story"], "visual_styles": ["stickman", "cartoon", "cinematic"],
                 "default_visual_mode": "animation_2d", "durations": {"min": 20, "target": 35, "max": 50}, "scene_count": [3, 6]}),
]

# Preços em USD — ESTIMATIVAS editáveis na interface (verifique a tabela oficial de cada provedor).
PROVIDERS = [
    dict(key="anthropic", name="Anthropic Claude", kind="llm", adapter="anthropic", priority=10, docs_url="https://docs.claude.com",
         commercial_use_note="Saídas podem ser usadas comercialmente conforme os Termos Comerciais da Anthropic.",
         config={"effort": "medium", "server_fallbacks": True},
         models=[("claude-opus-5-5", "Claude Opus 5.5", {"input_per_1m_tokens": 4.0, "output_per_1m_tokens": 20.0}, 9.5, 6, True),
                 ("claude-sonnet-5-5", "Claude Sonnet 5.5", {"input_per_1m_tokens": 2.0, "output_per_1m_tokens": 10.0}, 8.8, 7.5, False),
                 ("claude-haiku-5-5", "Claude Haiku 5.5", {"input_per_1m_tokens": 0.1, "output_per_1m_tokens": 0.5}, 7.0, 9.5, False)]),
    dict(key="openai", name="OpenAI (Chat)", kind="llm", adapter="openai_compatible", priority=20, docs_url="https://platform.openai.com/docs",
         config={"base_url": "https://api.openai.com/v1"},
         models=[("gpt-4o-mini", "GPT-4o mini", {"input_per_1m_tokens": 0.15, "output_per_1m_tokens": 0.6}, 7.0, 9, True)]),
    dict(key="openrouter", name="OpenRouter", kind="llm", adapter="openai_compatible", priority=30, docs_url="https://openrouter.ai/docs",
         config={"base_url": "https://openrouter.ai/api/v1", "supports_json_mode": True},
         models=[("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B", {"input_per_1m_tokens": 0.13, "output_per_1m_tokens": 0.4}, 6.5, 7, True)]),
    dict(key="ollama", name="Ollama (local)", kind="llm", adapter="openai_compatible", priority=40, docs_url="https://ollama.com",
         commercial_use_note="Depende da licença do modelo local escolhido.",
         config={"base_url": "", "requires_api_key": False, "supports_json_mode": True, "timeout": 600},
         models=[("qwen2.5:7b", "Qwen 2.5 7B (local)", {}, 5.0, 4, True)]),
    dict(key="builtin-template", name="Gerador de modelos (SIMULADO)", kind="llm", adapter="builtin_template", priority=99, is_simulated=True,
         commercial_use_note="Não é IA: modelos narrativos internos para testes do fluxo sem credenciais.",
         models=[("template-v1", "Template v1", {}, 1.0, 10, True)]),
    dict(key="openai-image", name="OpenAI Images", kind="image", adapter="openai_image", priority=20, docs_url="https://platform.openai.com/docs/guides/images",
         config={"quality": "medium"}, models=[("gpt-image-1", "GPT Image 1", {"per_image": 0.063}, 8.5, 5, True)]),
    dict(key="stability", name="Stability AI", kind="image", adapter="stability", priority=25, docs_url="https://platform.stability.ai/docs",
         models=[("stable-image-core", "Stable Image Core", {"per_image": 0.03}, 7.0, 7, True),
                 ("stable-image-ultra", "Stable Image Ultra", {"per_image": 0.08}, 8.5, 5, False)]),
    dict(key="replicate-image", name="Replicate (FLUX)", kind="image", adapter="replicate_image", priority=15, docs_url="https://replicate.com/docs",
         models=[("black-forest-labs/flux-schnell", "FLUX.1 schnell", {"per_image": 0.003}, 7.0, 9, True),
                 ("black-forest-labs/flux-1.1-pro", "FLUX 1.1 pro", {"per_image": 0.04}, 9.0, 6, False)]),
    dict(key="replicate-video", name="Replicate (vídeo IA)", kind="video", adapter="replicate_video", priority=20, docs_url="https://replicate.com/collections/text-to-video",
         config={"input_map": {"minimax/video-01": {"prompt": "prompt", "image": "first_frame_image"},
                               "kwaivgi/kling-v2.1": {"prompt": "prompt", "image": "start_image", "duration": "duration", "aspect_ratio": "aspect_ratio"}}},
         models=[("minimax/video-01", "MiniMax Video-01 (6s)", {"per_video": 0.5}, 7.5, 3, True),
                 ("kwaivgi/kling-v2.1", "Kling 2.1", {"per_second": 0.05}, 8.5, 3, False)]),
    dict(key="elevenlabs", name="ElevenLabs", kind="tts", adapter="elevenlabs", priority=10, docs_url="https://elevenlabs.io/docs",
         commercial_use_note="Uso comercial em planos pagos; use somente vozes próprias, da biblioteca licenciada ou geradas.",
         config={"default_voices": {}}, models=[("eleven_multilingual_v2", "Multilingual v2", {"per_1k_chars": 0.2}, 9.5, 6, True)]),
    dict(key="openai-tts", name="OpenAI TTS", kind="tts", adapter="openai_tts", priority=20, docs_url="https://platform.openai.com/docs/guides/text-to-speech",
         commercial_use_note="Informe ao público que a voz é gerada por IA (políticas de uso da OpenAI).",
         config={"default_voices": {"male": "onyx", "female": "nova", "neutral": "alloy"}},
         models=[("gpt-4o-mini-tts", "GPT-4o mini TTS", {"per_1k_chars": 0.015}, 8.0, 8, True)]),
    dict(key="espeak", name="eSpeak NG (local)", kind="tts", adapter="espeak", priority=90, docs_url="https://github.com/espeak-ng/espeak-ng",
         commercial_use_note="Programa GPL; o áudio gerado pode ser usado livremente. Qualidade robótica.",
         config={"default_voices": {"male": "pt-br", "female": "pt-br+f2", "neutral": "pt-br+m3"}},
         models=[("espeak-ng", "eSpeak NG", {}, 2.0, 10, True)]),
    dict(key="procedural-music", name="Trilha procedural (local)", kind="music", adapter="procedural_music", priority=50,
         commercial_use_note="Música gerada internamente — sem direitos de terceiros.", models=[("procedural-v1", "Procedural v1", {}, 4.0, 10, True)]),
]

VOICES = [
    ("Narrador grave (local)", "espeak", "pt-br", "male", "Narrador padrão — síntese local"),
    ("Voz masculina 2 (local)", "espeak", "pt-br+m7", "male", ""),
    ("Voz masculina 3 (local)", "espeak", "pt-br+m3", "male", ""),
    ("Voz feminina 1 (local)", "espeak", "pt-br+f2", "female", ""),
    ("Voz feminina 2 (local)", "espeak", "pt-br+f4", "female", ""),
    ("Voz feminina 3 (local)", "espeak", "pt-br+f5", "female", ""),
    ("Narrador OpenAI Onyx", "openai-tts", "onyx", "male", "Requer chave OpenAI"),
    ("Narradora OpenAI Nova", "openai-tts", "nova", "female", "Requer chave OpenAI"),
    ("OpenAI Echo", "openai-tts", "echo", "male", "Requer chave OpenAI"),
    ("OpenAI Shimmer", "openai-tts", "shimmer", "female", "Requer chave OpenAI"),
]

TEMPLATES = [
    ("Padrão vertical", "Legendas grandes com destaque palavra a palavra, música com ducking.", {}, True),
    ("Suspense escuro", "Legendas brancas centrais, trilha baixa, sem destaque amarelo.",
     {"captions": {"position": "middle", "highlight": "#E2E8F0", "size": 0.048}, "music": {"volume": 0.12},
      "thumbnail": {"accent": "#ef4444"}}, False),
    ("Comédia vibrante", "Legendas superiores coloridas, efeitos sonoros mais altos.",
     {"captions": {"position": "upper", "highlight": "#34D399", "words_per_caption": 2}, "sfx": {"volume": 0.7},
      "thumbnail": {"accent": "#34d399"}}, False),
    ("Rascunho rápido (720p)", "Renderização mais rápida para testes (meia resolução interna).",
     {"render_scale": 0.5, "crf": 24}, False),
]

TREND_SOURCES = [
    ("google-trends-br", "Google Trends (Brasil)", "google_trends_rss", {"geo": "BR", "language": "pt-BR"}, False),
    ("google-news-br", "Google Notícias (Brasil)", "google_news_rss", {"geo": "BR", "hl": "pt-BR", "ceid": "BR:pt-419", "language": "pt-BR", "limit": 30}, False),
    ("google-news-entretenimento", "Google Notícias — Entretenimento", "google_news_rss",
     {"geo": "BR", "hl": "pt-BR", "ceid": "BR:pt-419", "topic": "ENTERTAINMENT", "language": "pt-BR", "limit": 25}, False),
    ("youtube-popular-br", "YouTube — em alta (BR)", "youtube_most_popular", {"geo": "BR", "language": "pt-BR"}, True),
    ("reddit-brasil", "Reddit r/brasil (top do dia)", "reddit", {"subreddit": "brasil", "geo": "BR", "language": "pt-BR"}, False),
    ("tiktok-creative-center", "TikTok Creative Center (importação manual)", "tiktok_creative_center", {"geo": "BR", "language": "pt-BR"}, False),
    ("instagram-trends", "Tendências do Instagram (importação manual)", "instagram_trends", {"geo": "BR", "language": "pt-BR"}, False),
]

WORKFLOWS = [
    ("trend_research", "Pesquisa de tendências", "Coleta e analisa tendências de todas as fontes ativas.", "0 */3 * * *"),
    ("idea_generation", "Geração de ideias", "Gera e pontua ideias para canais em modo assistido/automático.", "30 */6 * * *"),
    ("factory_tick", "Planejador da fábrica", "Inicia produções conforme cotas, pesos e orçamento.", "*/15 * * * *"),
    ("publish_due", "Publicador", "Publica conteúdos agendados vencidos e acompanha processamento.", "* * * * *"),
    ("metrics_collection", "Coleta de métricas", "Busca métricas das publicações via APIs oficiais.", "15 */6 * * *"),
    ("optimization", "Otimização", "Atualiza estatísticas, ajusta distribuição e avalia testes A/B.", "0 5 * * *"),
    ("token_refresh", "Renovação de tokens", "Renova tokens OAuth prestes a expirar.", "40 * * * *"),
    ("recover_stale", "Recuperação de tarefas órfãs", "Re-enfileira produções interrompidas.", "*/10 * * * *"),
    ("provider_health", "Saúde dos provedores", "Atualiza status de configuração dos provedores.", "*/30 * * * *"),
]


def seed(db: Session) -> dict:
    created: dict[str, int] = {}

    def add(kind: str):
        created[kind] = created.get(kind, 0) + 1

    for p in PLATFORMS:
        if not db.scalar(select(Platform).where(Platform.key == p["key"])):
            db.add(Platform(**p))
            add("platforms")
    for e in ENGINES:
        if not db.scalar(select(ContentEngine).where(ContentEngine.key == e["key"])):
            db.add(ContentEngine(**e, is_system=True))
            add("engines")
    db.flush()
    for p in PROVIDERS:
        p = dict(p)
        models = p.pop("models")
        rec = db.scalar(select(ModelProvider).where(ModelProvider.key == p["key"]))
        if not rec:
            rec = ModelProvider(**p)
            db.add(rec)
            db.flush()
            add("providers")
        for mk, name, pricing, q, sp, default in models:
            if not db.scalar(select(ProviderModel).where(ProviderModel.provider_id == rec.id, ProviderModel.model_key == mk)):
                db.add(ProviderModel(provider_id=rec.id, model_key=mk, display_name=name, kind=rec.kind, pricing=pricing,
                                     quality_score=q, speed_score=sp, is_default=default))
                add("models")
    for name, prov, vid, gender, desc in VOICES:
        if not db.scalar(select(Voice).where(Voice.provider_key == prov, Voice.provider_voice_id == vid)):
            db.add(Voice(name=name, provider_key=prov, provider_voice_id=vid, gender=gender, description=desc, language="pt-BR",
                         accent="brasileiro", settings={"speed": 1.0, "pitch": 0}, is_active=True,
                         license_note="Síntese local" if prov == "espeak" else "Voz de catálogo do provedor (não é clonagem)"))
            add("voices")
    for name, desc, cfg, default in TEMPLATES:
        if not db.scalar(select(Template).where(Template.name == name)):
            db.add(Template(name=name, description=desc, config=cfg, is_default=default))
            add("templates")
    for key, name, st, cfg, creds in TREND_SOURCES:
        if not db.scalar(select(TrendSource).where(TrendSource.key == key)):
            db.add(TrendSource(key=key, name=name, source_type=st, config=cfg, requires_credentials=creds,
                               status="manual" if st in ("tiktok_creative_center", "instagram_trends") else "idle"))
            add("trend_sources")
    for key, name, desc, cron in WORKFLOWS:
        if not db.scalar(select(Workflow).where(Workflow.key == key)):
            db.add(Workflow(key=key, name=name, description=desc, schedule=cron, trigger="cron"))
            add("workflows")
    if not db.scalar(select(CostLimit)):
        db.add(CostLimit(scope="global", period="daily", limit_usd=10.0, alert_threshold_pct=80, action="block"))
        db.add(CostLimit(scope="global", period="monthly", limit_usd=150.0, alert_threshold_pct=80, action="block"))
        db.add(CostLimit(scope="video", period="per_video", limit_usd=2.0, alert_threshold_pct=90, action="block"))
        add("cost_limits")
    if not db.scalar(select(User)):
        db.add(User(email=settings.first_admin_email.lower(), name="Administrador", role="admin",
                    password_hash=hash_password(settings.first_admin_password)))
        add("users")
    db.commit()
    return created
