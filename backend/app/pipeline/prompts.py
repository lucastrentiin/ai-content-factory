"""Prompts dos agentes (português). Saídas sempre em JSON validado pelo código."""
from __future__ import annotations

import json

BASE = ("Você é parte de uma fábrica de conteúdo para vídeos curtos verticais (TikTok, Reels, Shorts) voltada ao público "
        "{language}/{region}. Produza conteúdo ORIGINAL: nunca copie vídeos, falas ou personagens existentes nem use "
        "marcas, celebridades ou pessoas reais de forma difamatória. Evite temas sensíveis tratados de forma sensacionalista.")

SCRIPT_SCHEMA = {
    "title": "string (<= 90 caracteres, chamativo, sem clickbait enganoso)",
    "synopsis": "string",
    "full_story": "string (história completa em prosa)",
    "hook": "string (frase dos primeiros 2 segundos)",
    "closing": "string (encerramento / CTA)",
    "music_mood": "emotional|suspense|dark|playful|curious|upbeat|neutral",
    "characters": [{"name": "string", "role": "main|secondary|temporary|narrator", "description": "string",
                    "personality": "string",
                    "appearance": {"gender": "male|female|neutral", "age_group": "child|teen|young|adult|elder",
                                   "hair": "short|long|spiky|bun|curly|bald|ponytail", "outfit_color": "#hex",
                                   "skin_tone": "#hex", "accessories": ["glasses|hat|scarf|backpack|bow"]}}],
    "locations": [{"name": "string", "setting_type": "room|kitchen|office|school|street|city|park|forest|beach|abandoned|lab|space|abstract",
                   "time_of_day": "day|sunset|night", "description": "string"}],
    "scenes": [{"index": 0, "title": "string", "location": "nome de uma location", "duration_s": 5.0,
                "narration": "texto do narrador (pode ser vazio)",
                "dialogue": [{"character": "nome", "text": "fala curta", "emotion": "neutral|happy|sad|angry|scared|surprised|thinking"}],
                "characters": [{"name": "nome", "action": "idle|talk|walk|run|wave|point|jump|shrug|cower|think|dance|sit",
                                "expression": "neutral|happy|sad|angry|scared|surprised|thinking", "position": "left|center|right"}],
                "visual_description": "descrição visual detalhada da cena (para gerador de imagem)",
                "emotion": "string", "camera": "static|zoom_in|zoom_out|slow_zoom|pan_left|pan_right|shake",
                "transition": "cut|fade", "sfx": ["whoosh|boom|knock|crash|boing|ding|pop"], "on_screen_text": "texto curto opcional"}],
    "fact_claims": [{"claim": "afirmação factual", "source": "fonte verificável (URL ou referência) ou null"}],
    "hashtags": ["string"],
    "next_episode_hook": "string (apenas séries)",
}


def system_for(agent: str, *, language: str = "pt-BR", region: str = "BR", engine: dict | None = None) -> str:
    rules = ""
    if engine:
        cfg = engine.get("config") or {}
        rules = (f"\nMotor de conteúdo: {engine.get('name')} ({engine.get('engine_type')}). {engine.get('description', '')}\n"
                 f"Regras editoriais: {cfg.get('editorial_rules', '')}\nTom: {cfg.get('tone', '')}")
    role = {
        "idea_generator": "Seu papel: Gerador de Ideias. Crie ideias originais com gancho forte, adequadas ao motor e ao canal.",
        "idea_evaluator": "Seu papel: Avaliador de Ideias. Avalie com rigor e honestidade, de 0 a 1, cada critério.",
        "trend_analyst": "Seu papel: Analista de Tendências. Explique por que um assunto chama atenção e como adaptá-lo de forma original.",
        "story_writer": "Seu papel: Roteirista. Escreva roteiros para vídeos curtos com gancho nos 2 primeiros segundos, ritmo rápido, "
                        "cenas curtas (3-8s), falas curtas e naturais em português brasileiro, e final com impacto.",
        "script_editor": "Seu papel: Editor de Roteiro. Revise ritmo, clareza, gancho, coerência, continuidade e segurança.",
        "fact_checker": "Seu papel: Verificador de Fatos. Para cada afirmação, diga se é verificável, sua confiança e fontes confiáveis. "
                        "Nunca invente fontes. Se não tiver certeza, marque como não verificada.",
        "publisher": "Seu papel: Publicador. Crie títulos, descrições e hashtags adequados a cada plataforma, sem clickbait enganoso.",
        "character_designer": "Seu papel: Designer de Personagens. Crie fichas consistentes e marcantes.",
        "series_planner": "Seu papel: Showrunner. Planeje o próximo episódio mantendo continuidade e permitindo que novos espectadores entendam.",
        "optimization": "Seu papel: Estrategista de crescimento. Interprete dados com cautela estatística.",
    }[agent]
    return BASE.format(language=language, region=region) + "\n" + role + rules


def ideas_prompt(*, channel: dict, engine: dict, trends: list[dict], count: int, history: dict, series: dict | None) -> str:
    return (
        f"Canal: {channel['name']} — nicho: {channel.get('niche')}; público: {channel.get('target_audience')}; "
        f"estilo visual: {channel.get('visual_style')}; duração alvo: {channel.get('default_duration_s')}s.\n"
        f"Tendências/sinais atuais (use como inspiração, não copie): {json.dumps(trends, ensure_ascii=False)}\n"
        f"Histórico de desempenho do canal (o que funcionou e o que não funcionou): {json.dumps(history, ensure_ascii=False)}\n"
        + (f"Série relacionada: {json.dumps(series, ensure_ascii=False)}\n" if series else "")
        + f"Gere {count} ideias distintas. Formato JSON: {{\"ideas\": [{{\"title\":\"\",\"description\":\"\",\"hook\":\"\","
        f"\"format\":\"narrated_story|dialogue_story|pov|sketch|episode|explainer|list|analog_horror|relato|trend_remix\","
        f"\"category\":\"\",\"target_audience\":\"\",\"duration_s\":45,\"visual_style\":\"stickman|cartoon|cinematic\","
        f"\"trend\":\"nome da tendência usada ou null\",\"continuation_potential\":0.0}}]}}"
    )


def evaluate_prompt(ideas: list[dict], channel: dict) -> str:
    return (f"Canal: {channel['name']} ({channel.get('niche')}). Avalie cada ideia:\n{json.dumps(ideas, ensure_ascii=False)}\n"
            "Critérios (0..1): attention (prende nos 2 primeiros segundos), retention (mantém até o fim), shareability "
            "(vontade de compartilhar/comentar), originality. Formato: {\"evaluations\":[{\"index\":0,\"attention\":0.0,"
            "\"retention\":0.0,\"shareability\":0.0,\"originality\":0.0,\"rationale\":\"\"}]}")


def script_prompt(*, idea: dict, channel: dict, engine: dict, target_s: int, platform_hint: str, characters: list[dict],
                  locations: list[dict], series_context: dict | None, variant: str | None) -> str:
    cfg = engine.get("config") or {}
    smin, smax = (cfg.get("scene_count") or [4, 8])[:2]
    parts = [
        f"Ideia: {json.dumps(idea, ensure_ascii=False)}",
        f"Canal: {channel['name']} — público: {channel.get('target_audience')}; idioma {channel.get('language')}.",
        f"Duração total alvo: {target_s}s ({platform_hint}). Use entre {smin} e {smax} cenas. Fala em PT-BR ≈ 2,6 palavras/segundo.",
        f"Estilo visual: {idea.get('visual_style') or channel.get('visual_style')}.",
    ]
    if characters:
        parts.append("Personagens existentes que DEVEM ser reutilizados quando fizer sentido (mantenha personalidade e jeito de falar): "
                     + json.dumps(characters, ensure_ascii=False))
    if locations:
        parts.append("Cenários existentes reutilizáveis: " + json.dumps(locations, ensure_ascii=False))
    if series_context:
        parts.append("Contexto da série (continuidade obrigatória, mas o episódio deve ser compreensível para novos espectadores): "
                     + json.dumps(series_context, ensure_ascii=False))
    if variant:
        parts.append(f"Variação de teste A/B: {variant}")
    if cfg.get("requires_fact_check"):
        parts.append("Este motor exige fatos verificáveis: liste cada afirmação factual em fact_claims com fonte. Não invente dados.")
    parts.append("Retorne JSON exatamente neste formato: " + json.dumps(SCRIPT_SCHEMA, ensure_ascii=False))
    return "\n".join(parts)


def review_prompt(script: dict, target_s: int) -> str:
    return (f"Revise o roteiro (duração alvo {target_s}s):\n{json.dumps(script, ensure_ascii=False)}\n"
            "Retorne {\"approved\": true|false, \"score\": 0.0, \"issues\": [\"\"], \"suggestions\": [\"\"], "
            "\"revised\": null ou o roteiro completo revisado no MESMO formato se houver problemas relevantes}")


def fact_check_prompt(claims: list[dict]) -> str:
    return (f"Verifique as afirmações:\n{json.dumps(claims, ensure_ascii=False)}\nRetorne {{\"claims\":[{{\"claim\":\"\","
            "\"verified\":true|false,\"confidence\":0.0,\"sources\":[\"\"],\"note\":\"\"}}]}}")


def metadata_prompt(*, title: str, synopsis: str, platform: str, max_title: int, max_hashtags: int, language: str,
                    hashtags: list[str]) -> str:
    return (f"Crie metadados para {platform}. Título original: {title}. Sinopse: {synopsis}. Hashtags sugeridas: {hashtags}. "
            f"Idioma {language}. Título <= {max_title} caracteres, no máximo {max_hashtags} hashtags. "
            "Retorne {\"title\":\"\",\"description\":\"\",\"hashtags\":[\"#...\"]}")
