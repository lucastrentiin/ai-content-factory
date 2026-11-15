"""Provedor LLM SIMULADO (offline, sem custo).

NÃO é inteligência artificial: gera ideias e roteiros a partir de modelos narrativos parametrizados.
Existe para que o fluxo completo funcione sem credenciais. Todo conteúdo produzido por ele é marcado com
`is_simulated=True` e exibido com selo "SIMULADO" na interface. Curiosidades geradas por ele NUNCA são
consideradas verificadas (vão obrigatoriamente para revisão humana).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from typing import Any

from app.providers.base import LLMProvider, LLMResult, Usage

NAMES_M = ["Lucas", "Rafael", "Pedro", "Thiago", "Bruno", "Caio", "Davi", "Igor", "Mateus", "Otávio"]
NAMES_F = ["Ana", "Júlia", "Marina", "Bia", "Larissa", "Clara", "Sofia", "Helena", "Lívia", "Duda"]
COLORS = ["#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#ec4899", "#14b8a6", "#f97316", "#64748b", "#eab308"]
HAIR = ["short", "long", "spiky", "bun", "curly", "bald", "ponytail"]

ENGINE_BLUEPRINTS: dict[str, dict[str, Any]] = {
    "storytelling": {
        "formats": ["narrated_story", "dialogue_story", "pov"],
        "titles": [
            "Ele achou {obj} no {place} e não imaginava o que viria depois",
            "O dia em que {topic} mudou a vida de {hero}",
            "Ninguém acreditou em {hero}… até o final",
            "{hero} fez uma escolha sobre {topic} que ninguém esperava",
        ],
        "hooks": [
            "Ninguém naquela rua sabia que {hero} guardava um segredo.",
            "Era só mais um dia comum… até {hero} encontrar {obj}.",
            "Se você acha que já viu de tudo, espera até ouvir o que aconteceu com {hero}.",
        ],
        "mood": "emotional",
        "locations": [("Rua do bairro", "street", "day"), ("Casa de {hero}", "room", "day"), ("Praça central", "park", "day")],
    },
    "series": {
        "formats": ["episode", "dialogue_story"],
        "titles": ["{series}: o segredo de {hero}", "{series} — a escolha de {hero}", "{series}: ninguém esperava {topic}"],
        "hooks": ["No episódio de hoje, {hero} finalmente descobre a verdade.", "Tudo mudou desde aquela noite com {obj}."],
        "mood": "suspense",
        "locations": [("Escola", "school", "day"), ("Quarto de {hero}", "room", "night"), ("Rua escura", "street", "night")],
    },
    "comedy": {
        "formats": ["sketch", "pov", "dialogue_story"],
        "titles": ["POV: {hero} tentando lidar com {topic}", "Quando {topic} vira o assunto do grupo", "{hero} vs {topic}: quem venceu?"],
        "hooks": ["POV: você é {hero} e acabou de descobrir {topic}.", "Todo mundo tem aquele amigo que leva {topic} a sério demais."],
        "mood": "playful",
        "locations": [("Escritório", "office", "day"), ("Sala de estar", "room", "day"), ("Cozinha", "kitchen", "day")],
    },
    "horror": {
        "formats": ["narrated_story", "analog_horror", "relato"],
        "titles": ["Nunca abra {obj} depois da meia-noite", "O que {hero} viu na {place} às 3h da manhã", "A lenda de {obj} que ninguém conta"],
        "hooks": ["Essa história aconteceu numa noite em que tudo estava silencioso demais.",
                  "Se você ouvir três batidas na porta, não abra."],
        "mood": "dark",
        "locations": [("Casa abandonada", "abandoned", "night"), ("Estrada deserta", "street", "night"), ("Floresta", "forest", "night")],
    },
    "curiosity": {
        "formats": ["explainer", "list", "documentary"],
        "titles": ["O que quase ninguém sabe sobre {topic}", "3 fatos sobre {topic} que vão te surpreender", "Por que {topic} é assim?"],
        "hooks": ["Você provavelmente nunca parou para pensar nisso sobre {topic}.", "Existe um detalhe sobre {topic} que muda tudo."],
        "mood": "curious",
        "locations": [("Laboratório", "lab", "day"), ("Espaço", "space", "night"), ("Estúdio", "abstract", "day")],
    },
    "experimental": {
        "formats": ["trend_remix", "pov", "sketch", "narrated_story"],
        "titles": ["E se {topic} acontecesse com {hero}?", "Testamos: {topic} em versão animada", "{topic}, mas contado por {hero}"],
        "hooks": ["E se {topic} fosse real e acontecesse amanhã?", "Pegaram {topic} e transformaram nisso."],
        "mood": "upbeat",
        "locations": [("Cidade", "city", "day"), ("Praia", "beach", "day"), ("Estúdio", "abstract", "night")],
    },
}
OBJECTS = ["uma carta antiga", "uma chave enferrujada", "um celular desconhecido", "uma caixa lacrada", "um diário",
           "uma fotografia rasgada", "um mapa estranho", "um bilhete premiado"]
PLACES = ["sótão", "porão", "metrô", "escola", "parque", "elevador", "padaria"]


def _rng(*parts: Any) -> random.Random:
    seed = int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def _fmt(s: str, ctx: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: ctx.get(m.group(1), m.group(0)), s)


def make_character(rng: random.Random, name: str | None = None, role: str = "main", style: str = "stickman") -> dict:
    female = rng.random() < 0.5
    name = name or rng.choice(NAMES_F if female else NAMES_M)
    return {
        "name": name,
        "role": role,
        "description": f"{name}, personagem {'principal' if role == 'main' else 'secundário'}",
        "personality": rng.choice(["curioso e corajoso", "desconfiado e engraçado", "tímido mas determinado",
                                   "impulsivo e leal", "calmo e observador"]),
        "appearance": {
            "gender": "female" if female else "male",
            "age_group": rng.choice(["young", "adult", "adult", "teen"]),
            "hair": rng.choice(HAIR),
            "outfit_color": rng.choice(COLORS),
            "skin_tone": rng.choice(["#f1c27d", "#e0ac69", "#c68642", "#8d5524", "#ffdbac"]),
            "accessories": rng.sample(["glasses", "hat", "scarf", "backpack"], k=rng.choice([0, 0, 1])),
            "style": style,
        },
        "voice_hint": "female" if female else "male",
    }


class TemplateLLM(LLMProvider):
    adapter = "builtin_template"
    simulated = True
    default_model = "template-v1"

    def generate(self, *, system, prompt, model=None, max_tokens=4000, json_mode=True, effort=None, task=None):
        task = task or {}
        handler = getattr(self, f"_task_{task.get('type', 'none')}", None)
        out = handler(task) if handler else {"text": "Provedor simulado: tarefa não suportada", "simulated": True}
        text = json.dumps(out, ensure_ascii=False)
        return LLMResult(text=text, model=self.model(model), simulated=True,
                         usage=Usage(units={"input_tokens": len(prompt) // 4, "output_tokens": len(text) // 4}, cost_usd=0.0))

    # ------------------------------------------------------------------ ideias
    def _task_ideas(self, t: dict) -> dict:
        etype = t.get("engine_type", "storytelling")
        bp = ENGINE_BLUEPRINTS.get(etype, ENGINE_BLUEPRINTS["experimental"])
        trends = t.get("trends") or [{"name": t.get("niche") or "o cotidiano", "category": None}]
        count = int(t.get("count", 5))
        ideas = []
        for i in range(count):
            rng = _rng("idea", etype, t.get("seed", ""), i, trends[i % len(trends)]["name"])
            tr = trends[i % len(trends)]
            hero = rng.choice(NAMES_F + NAMES_M)
            ctx = {"hero": hero, "topic": tr["name"], "obj": rng.choice(OBJECTS), "place": rng.choice(PLACES),
                   "series": t.get("series_title") or "A Rua 13"}
            fmt = rng.choice(bp["formats"])
            dur = int(t.get("target_duration_s") or rng.choice([30, 40, 45, 55]))
            ideas.append({
                "title": _fmt(rng.choice(bp["titles"]), ctx)[:180],
                "description": f"História original em formato {fmt} inspirada no interesse do público por '{tr['name']}'. "
                               f"Protagonista: {hero}. Tom: {bp['mood']}.",
                "hook": _fmt(rng.choice(bp["hooks"]), ctx),
                "format": fmt,
                "category": tr.get("category") or etype,
                "target_audience": t.get("audience") or "jovens e adultos brasileiros, 16-35",
                "duration_s": dur,
                "visual_style": t.get("visual_style") or "stickman",
                "protagonist": hero,
                "trend": tr["name"],
                "continuation_potential": round(rng.uniform(0.3, 0.9), 2),
            })
        return {"ideas": ideas, "simulated": True}

    # ------------------------------------------------------------------ avaliação de ideias
    def _task_evaluate_ideas(self, t: dict) -> dict:
        evals = []
        for i, idea in enumerate(t.get("ideas", [])):
            rng = _rng("eval", idea.get("title"))
            title = idea.get("title", "")
            evals.append({
                "index": i,
                "attention": round(min(1, 0.45 + 0.1 * ("?" in title) + 0.15 * any(w in title.lower() for w in ["ninguém", "nunca", "segredo", "pov"]) + rng.uniform(0, 0.2)), 2),
                "retention": round(rng.uniform(0.4, 0.8), 2),
                "shareability": round(rng.uniform(0.3, 0.8), 2),
                "originality": round(rng.uniform(0.3, 0.75), 2),
                "rationale": "Avaliação heurística simulada (sem LLM real).",
            })
        return {"evaluations": evals, "simulated": True}

    # ------------------------------------------------------------------ análise de tendências
    def _task_trend_analysis(self, t: dict) -> dict:
        out = []
        for tr in t.get("trends", []):
            rng = _rng("trend", tr.get("name"))
            out.append({
                "name": tr.get("name"),
                "category": tr.get("category") or rng.choice(["entretenimento", "cotidiano", "tecnologia", "esporte", "cultura"]),
                "potential": round(rng.uniform(0.3, 0.85), 2),
                "why": "Análise simulada: assunto com volume de buscas/menções; avaliar manualmente o contexto.",
                "adaptable_formats": rng.sample(["storytelling", "comedy", "curiosity", "horror", "experimental"], k=2),
                "sensitive": False,
            })
        return {"analyses": out, "simulated": True}

    # ------------------------------------------------------------------ roteiro
    def _task_script(self, t: dict) -> dict:
        idea = t.get("idea", {})
        etype = t.get("engine_type", "storytelling")
        bp = ENGINE_BLUEPRINTS.get(etype, ENGINE_BLUEPRINTS["storytelling"])
        rng = _rng("script", idea.get("title"), t.get("variant", ""))
        style = idea.get("visual_style") or "stickman"
        existing = t.get("characters") or []
        hero_name = idea.get("protagonist") or (existing[0]["name"] if existing else rng.choice(NAMES_F + NAMES_M))
        hero = next((c for c in existing if c.get("name") == hero_name), None) or make_character(rng, hero_name, "main", style)
        side = next((c for c in existing if c.get("name") != hero_name), None) or make_character(rng, None, "secondary", style)
        if side["name"] == hero["name"]:
            side = make_character(rng, rng.choice([n for n in NAMES_F + NAMES_M if n != hero["name"]]), "secondary", style)
        topic = idea.get("trend") or idea.get("title", "o inesperado")
        obj = rng.choice(OBJECTS)
        ctx = {"hero": hero["name"], "side": side["name"], "topic": topic, "obj": obj}
        locs = [{"name": _fmt(n, ctx), "setting_type": st, "time_of_day": tod, "description": f"{_fmt(n, ctx)} ({tod})"}
                for n, st, tod in bp["locations"]]
        beats = self._beats(etype, ctx, rng)
        target = int(t.get("target_duration_s") or idea.get("duration_s") or 45)
        scenes = []
        for i, b in enumerate(beats):
            loc = locs[min(i * len(locs) // len(beats), len(locs) - 1)]
            chars = [{"name": hero["name"], "action": b.get("hero_action", "idle"), "expression": b.get("hero_expr", "neutral"), "position": "left" if b.get("dialogue") else "center"}]
            if b.get("side"):
                chars.append({"name": side["name"], "action": b.get("side_action", "talk"), "expression": b.get("side_expr", "neutral"), "position": "right"})
            scenes.append({
                "index": i,
                "title": b["title"],
                "location": loc["name"],
                "duration_s": round(target / len(beats), 1),
                "narration": _fmt(b.get("narration", ""), ctx),
                "dialogue": [{"character": _fmt(d[0], ctx), "text": _fmt(d[1], ctx), "emotion": d[2]} for d in b.get("dialogue", [])],
                "characters": chars,
                "visual_description": _fmt(b.get("visual", "") or b["title"], ctx),
                "emotion": b.get("emotion", "neutral"),
                "camera": b.get("camera", "static"),
                "transition": "fade" if i in (0, len(beats) - 1) else "cut",
                "sfx": b.get("sfx", []),
                "on_screen_text": _fmt(b.get("text", ""), ctx),
            })
        hook = scenes[0]["narration"] or idea.get("hook", "")
        closing = scenes[-1]["narration"]
        claims = []
        if etype == "curiosity":
            claims = [{"claim": s["narration"], "source": None} for s in scenes[1:-1] if s["narration"]]
        return {
            "title": idea.get("title") or f"A história de {hero['name']}",
            "synopsis": f"{hero['name']} vive uma situação envolvendo {topic}. Tom {bp['mood']}.",
            "full_story": " ".join(s["narration"] or " ".join(d["text"] for d in s["dialogue"]) for s in scenes),
            "hook": hook,
            "closing": closing,
            "music_mood": bp["mood"],
            "characters": [hero, side],
            "locations": locs,
            "scenes": scenes,
            "fact_claims": claims,
            "hashtags": ["historias", etype, re.sub(r"\W+", "", topic.lower())[:20] or "viral"],
            "next_episode_hook": f"Mas o que {hero['name']} ainda não sabia sobre {obj}…" if etype == "series" else "",
            "simulated": True,
        }

    def _beats(self, etype: str, c: dict, rng: random.Random) -> list[dict]:
        if etype == "comedy":
            return [
                {"title": "Abertura", "narration": "POV: {hero} descobriu {topic}.", "hero_action": "wave", "hero_expr": "happy", "camera": "zoom_in", "text": "POV"},
                {"title": "Setup", "side": True, "dialogue": [("{side}", "Você viu isso de {topic}?", "surprised"), ("{hero}", "Vi. E já tenho um plano.", "happy")], "hero_action": "talk", "side_expr": "surprised"},
                {"title": "Escalada", "side": True, "dialogue": [("{hero}", "Confia em mim, vai dar tudo certo.", "happy"), ("{side}", "Da última vez você disse isso e a gente foi parar na delegacia.", "angry")], "hero_action": "point", "side_action": "shrug", "side_expr": "angry", "camera": "pan_right", "sfx": ["boing"]},
                {"title": "Virada", "narration": "Cinco minutos depois…", "hero_action": "jump", "hero_expr": "scared", "camera": "shake", "sfx": ["crash"], "text": "5 minutos depois"},
                {"title": "Punchline", "side": True, "dialogue": [("{side}", "Eu avisei.", "neutral"), ("{hero}", "Tecnicamente… deu certo.", "happy")], "hero_action": "shrug", "hero_expr": "happy", "camera": "zoom_out"},
            ]
        if etype == "horror":
            return [
                {"title": "Gancho", "narration": "Se você ouvir três batidas na porta depois da meia-noite, não abra. {hero} abriu.", "hero_expr": "scared", "camera": "zoom_in", "emotion": "fear", "sfx": ["knock"]},
                {"title": "Contexto", "narration": "Tudo começou quando {hero} encontrou {obj} perto da casa abandonada.", "hero_action": "walk", "hero_expr": "neutral", "camera": "pan_left"},
                {"title": "Tensão", "narration": "Naquela noite, o silêncio era tão grande que dava para ouvir a própria respiração.", "hero_expr": "scared", "camera": "slow_zoom", "emotion": "fear"},
                {"title": "Aparição", "narration": "Então veio a primeira batida. Depois a segunda. E {hero} percebeu que vinha de dentro do quarto.", "hero_action": "cower", "hero_expr": "scared", "camera": "shake", "sfx": ["knock", "boom"], "emotion": "fear"},
                {"title": "Final", "narration": "No dia seguinte, a casa estava vazia. Só {obj} continuava lá… esperando o próximo.", "hero_expr": "neutral", "camera": "zoom_out", "emotion": "dread", "text": "Você abriria?"},
            ]
        if etype == "curiosity":
            return [
                {"title": "Gancho", "narration": "Você provavelmente nunca parou para pensar nisso sobre {topic}.", "hero_action": "point", "hero_expr": "surprised", "camera": "zoom_in", "text": "{topic}"},
                {"title": "Fato 1", "narration": "[A VERIFICAR] Primeiro ponto: descreva aqui um fato verificável sobre {topic}, com fonte.", "hero_action": "talk", "hero_expr": "thinking"},
                {"title": "Fato 2", "narration": "[A VERIFICAR] Segundo ponto: um dado surpreendente sobre {topic}, com fonte.", "hero_action": "talk", "hero_expr": "surprised", "camera": "pan_right"},
                {"title": "Fato 3", "narration": "[A VERIFICAR] Terceiro ponto: uma consequência curiosa de {topic}.", "hero_action": "point", "hero_expr": "happy"},
                {"title": "Encerramento", "narration": "Qual desses você não sabia? Comenta aí.", "hero_action": "wave", "hero_expr": "happy", "camera": "zoom_out", "text": "Comenta!"},
            ]
        if etype == "series":
            return [
                {"title": "Recap-gancho", "narration": "Desde aquela noite, {hero} não conseguia parar de pensar em {obj}.", "hero_expr": "thinking", "camera": "zoom_in"},
                {"title": "Encontro", "side": True, "dialogue": [("{side}", "Você precisa me contar o que viu.", "worried"), ("{hero}", "Se eu contar, você não vai acreditar.", "sad")], "side_expr": "sad"},
                {"title": "Revelação", "side": True, "dialogue": [("{hero}", "{obj} tinha o seu nome escrito.", "scared"), ("{side}", "Isso é impossível.", "surprised")], "hero_action": "point", "side_expr": "surprised", "camera": "shake", "sfx": ["boom"]},
                {"title": "Decisão", "narration": "Os dois decidiram voltar lá. Juntos.", "hero_action": "walk", "hero_expr": "neutral", "camera": "pan_right"},
                {"title": "Cliffhanger", "narration": "Mas quando abriram a porta, alguém já estava esperando por eles.", "hero_expr": "scared", "camera": "zoom_in", "text": "Continua…", "sfx": ["boom"]},
            ]
        return [  # storytelling / experimental
            {"title": "Gancho", "narration": "Ninguém imaginava o que {hero} ia encontrar naquele dia.", "hero_action": "walk", "hero_expr": "neutral", "camera": "zoom_in"},
            {"title": "Descoberta", "narration": "No meio do caminho, {hero} achou {obj}, com um recado: 'confie em quem ninguém confia'.", "hero_action": "idle", "hero_expr": "surprised", "sfx": ["whoosh"]},
            {"title": "Conflito", "side": True, "dialogue": [("{side}", "Joga isso fora, {hero}. Isso só vai te dar problema.", "angry"), ("{hero}", "E se for a única chance de fazer a coisa certa?", "sad")], "side_expr": "angry", "camera": "pan_right"},
            {"title": "Reviravolta", "narration": "O recado levava até {side}. Era {side} quem precisava de ajuda o tempo todo.", "hero_action": "point", "hero_expr": "surprised", "camera": "shake", "sfx": ["boom"]},
            {"title": "Desfecho", "side": True, "dialogue": [("{side}", "Por que você fez isso por mim?", "sad"), ("{hero}", "Porque alguém um dia fez por mim.", "happy")], "hero_action": "wave", "hero_expr": "happy", "camera": "zoom_out", "text": "Compartilhe com alguém"},
        ]

    # ------------------------------------------------------------------ revisão
    def _task_script_review(self, t: dict) -> dict:
        return {"approved": True, "score": 0.6, "issues": [], "suggestions": ["Revisão simulada: revise manualmente o ritmo e o gancho."], "simulated": True}

    def _task_metadata(self, t: dict) -> dict:
        title = t.get("title", "")
        tags = t.get("hashtags") or []
        base = ["#" + re.sub(r"\W+", "", x.lower()) for x in tags if x][:4]
        return {"title": title[:95], "description": (t.get("synopsis") or title)[:400] + "\n\nConteúdo original.",
                "hashtags": base + ["#shorts" if t.get("platform") == "youtube" else "#fyp"], "simulated": True}

    def _task_fact_check(self, t: dict) -> dict:
        return {"claims": [{"claim": c.get("claim"), "verified": False, "confidence": 0.0, "sources": [],
                            "note": "Verificação simulada — requer revisão humana com fontes."} for c in t.get("claims", [])],
                "simulated": True}

    def _task_character(self, t: dict) -> dict:
        rng = _rng("char", t.get("name"), t.get("context"))
        return make_character(rng, t.get("name"), t.get("role", "secondary"), t.get("style", "stickman"))

    def _task_series_plan(self, t: dict) -> dict:
        n = int(t.get("number", 1))
        return {"title": f"Episódio {n}", "synopsis": f"Continuação de {t.get('series_title', 'a série')}: novos mistérios.",
                "standalone_hook": "Uma porta que nunca deveria ter sido aberta.", "simulated": True}

    def _task_episode_summary(self, t: dict) -> dict:
        return {"summary": (t.get("full_story") or "")[:500], "facts": [], "open_threads": [t.get("next_episode_hook", "")], "simulated": True}

    def _task_optimization_notes(self, t: dict) -> dict:
        return {"notes": "Recomendações simuladas: aumente o volume amostral antes de conclusões.", "simulated": True}
