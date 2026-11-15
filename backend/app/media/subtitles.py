"""Legendas: segmentação em blocos curtos + geração ASS com estilo configurável (template)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Caption:
    start: float
    end: float
    text: str
    words: list[tuple[str, float, float]] | None = None


def chunk_segment(text: str, start: float, end: float, words_per_caption: int = 3,
                  word_timings: list[dict] | None = None) -> list[Caption]:
    """Divide uma fala em legendas curtas. Usa tempos por palavra quando disponíveis; senão distribui
    proporcionalmente ao número de caracteres."""
    words = text.split()
    if not words:
        return []
    if word_timings and len(word_timings) == len(words):
        timed = [(w, start + float(wt["start"] or 0), start + float(wt["end"] or 0)) for w, wt in zip(words, word_timings, strict=True)]
    else:
        total = sum(len(w) + 1 for w in words)
        dur = max(0.1, end - start)
        timed, t = [], start
        for w in words:
            d = dur * (len(w) + 1) / total
            timed.append((w, t, t + d))
            t += d
    caps = []
    for i in range(0, len(timed), words_per_caption):
        grp = timed[i:i + words_per_caption]
        # evita terminar bloco em palavra muito curta solta
        caps.append(Caption(grp[0][1], grp[-1][2], " ".join(w for w, _, _ in grp), grp))
    return caps


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _ass_color(hexstr: str, alpha: int = 0) -> str:
    h = hexstr.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _esc(s: str) -> str:
    return re.sub(r"[{}]", "", s).replace("\n", " ")


def build_ass(captions: list[Caption], path: Path, *, width: int, height: int, style: dict | None = None,
              watermark: dict | None = None) -> Path:
    st = {"font": "Inter", "size": 0.052, "color": "#FFFFFF", "highlight": "#FACC15", "outline": "#000000",
          "outline_width": 0.006, "position": "upper_middle", "uppercase": True, "karaoke": True, "bold": True, **(style or {})}
    fs = int(height * float(st["size"]))
    ow = max(2, int(height * float(st["outline_width"])))
    # "upper_middle" (padrão) fica acima dos personagens e fora das áreas de interface das plataformas
    align, margin_v = {"lower": (2, int(height * 0.2)), "middle": (5, 0), "upper": (8, int(height * 0.15)),
                       "upper_middle": (8, int(height * 0.27))}.get(st["position"], (8, int(height * 0.27)))
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{st['font']},{fs},{_ass_color(st['highlight'])},{_ass_color(st['color'])},{_ass_color(st['outline'])},"
        f"&H64000000,{-1 if st['bold'] else 0},0,0,0,100,100,0,0,1,{ow},2,{align},{int(width * 0.08)},{int(width * 0.08)},{margin_v},1",
    ]
    if watermark and watermark.get("text"):
        wfs = int(height * 0.022)
        wa = {"top_left": 7, "top_right": 9, "bottom_left": 1, "bottom_right": 3}.get(watermark.get("position", "top_right"), 9)
        alpha = int(255 * (1 - float(watermark.get("opacity", 0.6))))
        lines.append(f"Style: Mark,{st['font']},{wfs},{_ass_color('#FFFFFF', alpha)},{_ass_color('#FFFFFF', alpha)},"
                     f"{_ass_color('#000000', min(255, alpha + 60))},&H00000000,-1,0,0,0,100,100,0,0,1,2,0,{wa},40,40,60,1")
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for c in captions:
        if st["karaoke"] and c.words:
            # \k em centésimos: palavra destacada (SecondaryColour→PrimaryColour) conforme é falada
            parts = []
            for w, ws, we in c.words:
                parts.append(f"{{\\k{max(1, int(round((we - ws) * 100)))}}}{_esc(w.upper() if st['uppercase'] else w)}")
            text = " ".join(parts)
        else:
            text = _esc(c.text.upper() if st["uppercase"] else c.text)
        lines.append(f"Dialogue: 0,{_ts(c.start)},{_ts(c.end)},Cap,,0,0,0,,{text}")
    if watermark and watermark.get("text") and captions:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(max(c.end for c in captions) + 5)},Mark,,0,0,0,,{_esc(watermark['text'])}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
