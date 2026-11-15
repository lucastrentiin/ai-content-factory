"""Tipografia (Skia) com quebra de linha."""
from __future__ import annotations

from functools import lru_cache

import skia

FONT_CANDIDATES = ("Inter", "Montserrat", "Poppins", "DejaVu Sans", "Liberation Sans", "FreeSans")


@lru_cache(maxsize=32)
def typeface(family: str | None = None, bold: bool = True) -> skia.Typeface:
    style = skia.FontStyle.Bold() if bold else skia.FontStyle.Normal()
    mgr = skia.FontMgr()
    for fam in ((family,) if family else ()) + FONT_CANDIDATES:
        tf = mgr.matchFamilyStyle(fam, style)
        if tf is not None:
            return tf
    return mgr.legacyMakeTypeface(None, style) or skia.Typeface()


def wrap(text: str, font: skia.Font, max_w: float) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if font.measureText(cand) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_text_block(canvas: skia.Canvas, text: str, cx: float, top: float, max_w: float, size: float,
                    color: int, stroke_color: int | None = None, stroke_w: float = 0, family: str | None = None,
                    bg: int | None = None, pad: float = 0) -> float:
    font = skia.Font(typeface(family, True), size)
    lines = wrap(text, font, max_w)
    lh = size * 1.18
    if bg is not None and lines:
        wmax = max(font.measureText(line) for line in lines)
        canvas.drawRoundRect(skia.Rect.MakeXYWH(cx - wmax / 2 - pad, top - pad * 0.6, wmax + pad * 2, lh * len(lines) + pad * 1.2),
                             pad, pad, skia.Paint(AntiAlias=True, Color=bg))
    y = top + size
    for line in lines:
        w = font.measureText(line)
        x = cx - w / 2
        if stroke_color is not None and stroke_w > 0:
            canvas.drawString(line, x, y, font, skia.Paint(AntiAlias=True, Color=stroke_color, Style=skia.Paint.kStroke_Style,
                                                             StrokeWidth=stroke_w, StrokeJoin=skia.Paint.kRound_Join))
        canvas.drawString(line, x, y, font, skia.Paint(AntiAlias=True, Color=color))
        y += lh
    return lh * len(lines)
