"""Análise automática de tendências sem LLM: categoria, potencial, sensibilidade e formatos adaptáveis."""
from __future__ import annotations

import math
import re
import unicodedata

from app.models import Trend

CATEGORIES: dict[str, tuple[str, ...]] = {
    "esporte": ("futebol", "jogo", "gol", "campeonato", "copa", "brasileirao", "libertadores", "flamengo", "corinthians", "palmeiras",
                "sao paulo", "vasco", "gremio", "inter", "santos", "ufc", "f1", "formula 1", "volei", "basquete", "nba", "tenis", "seleção", "selecao"),
    "entretenimento": ("novela", "bbb", "reality", "filme", "serie", "netflix", "show", "cantor", "cantora", "musica", "album", "clipe",
                       "ator", "atriz", "festival", "streaming", "trailer", "anime"),
    "tecnologia": ("iphone", "android", "app", "inteligencia artificial", " ia ", "chatgpt", "google", "apple", "samsung", "celular",
                   "game", "games", "playstation", "xbox", "nintendo", "robo", "tecnologia", "internet"),
    "ciência": ("nasa", "espaco", "planeta", "eclipse", "cometa", "cientistas", "descoberta", "fossil", "dinossauro", "vulcao", "lua"),
    "humor": ("meme", "viral", "trend", "desafio", "pov", "zoeira", "piada"),
    "economia": ("dolar", "bolsa", "inflacao", "salario", "pix", "imposto", "economia", "preco"),
    "cotidiano": ("chuva", "calor", "frio", "feriado", "transito", "escola", "enem", "vestibular", "trabalho"),
    "mistério": ("misterio", "lenda", "assombrado", "fantasma", "ovni", "paranormal", "estranho", "desaparecimento"),
}
SENSITIVE = ("morre", "morreu", "morte", "morto", "mortos", "assassin", "homicidio", "estupro", "abuso", "tragedia", "acidente",
             "desastre", "ataque", "atentado", "tiroteio", "guerra", "bombardeio", "sequestro", "suicid", "velorio", "enterro",
             "eleicao", "eleicoes", "candidato", "deputado", "senador", "presidente", "stf", "partido", "lula", "bolsonaro",
             "cancer", "doenca", "hospital", "internado", "luto", "vitima", "preso", "prisao", "policia")
FORMATS = {
    "esporte": ["comedy", "storytelling", "curiosity"], "entretenimento": ["comedy", "experimental", "storytelling"],
    "tecnologia": ["curiosity", "comedy", "experimental"], "ciência": ["curiosity", "storytelling"], "humor": ["comedy", "experimental"],
    "economia": ["curiosity", "comedy"], "cotidiano": ["comedy", "storytelling", "series"], "mistério": ["horror", "storytelling", "series"],
    "geral": ["storytelling", "experimental", "comedy"],
}


def _norm(s: str) -> str:
    return " " + unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode() + " "


def analyze_trend(t: Trend) -> dict:
    text = _norm(f"{t.name} {t.description} {' '.join(n.get('title') or '' for n in (t.popularity or {}).get('news', []) if isinstance(n, dict))}")
    sensitive = any(re.search(rf"\b{re.escape(w)}", text) for w in SENSITIVE)
    scores = {cat: sum(1 for k in kws if k in text) for cat, kws in CATEGORIES.items()}
    cat = max(scores, key=scores.get) if max(scores.values()) > 0 else (t.category or "geral")
    if cat not in FORMATS:
        cat = "geral" if not t.category else t.category
    momentum = {"rising": 1.0, "active": 0.6, "declining": 0.25, "expired": 0.0}.get(t.status, 0.5)
    multi = min(1.0, len(t.sources_seen or []) / 3)
    potential = 0.45 * (t.popularity_value or 0) + 0.3 * momentum + 0.15 * multi + 0.1 * (1 / (1 + math.exp(-(t.times_seen or 1) + 2)))
    why = (f"Assunto de {cat} {'em alta' if t.status == 'rising' else 'em evidência'}"
           f"{', citado em várias fontes' if multi >= 0.66 else ''}. Adapte o tema (não a notícia) para uma história original.")
    return {"category": cat, "potential": round(0.0 if sensitive else min(1.0, potential), 3), "why": why,
            "adaptable_formats": FORMATS.get(cat, FORMATS["geral"]), "sensitive": sensitive, "method": "automatic_rules"}
