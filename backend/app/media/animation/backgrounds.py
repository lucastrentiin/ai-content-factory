"""Cenários procedurais (vetoriais) determinísticos: mesma location → mesmo fundo (consistência visual)."""
from __future__ import annotations

import hashlib
import math
import random

import numpy as np
import skia

from app.media.animation.rig import _color, _shade

SETTING_TYPES = ("room", "kitchen", "office", "school", "street", "city", "park", "forest", "beach",
                 "abandoned", "lab", "space", "abstract")

PALETTES = {
    "day": {"sky_top": "#7dd3fc", "sky_bottom": "#e0f2fe", "ground": "#86efac", "wall": "#fde68a", "floor": "#d6a77a", "dark": 1.0},
    "sunset": {"sky_top": "#f97316", "sky_bottom": "#fde68a", "ground": "#65a30d", "wall": "#fdba74", "floor": "#b45309", "dark": 0.9},
    "night": {"sky_top": "#020617", "sky_bottom": "#1e293b", "ground": "#14532d", "wall": "#334155", "floor": "#3f3f46", "dark": 0.55},
}


def _rng(key: str) -> random.Random:
    return random.Random(int(hashlib.md5(key.encode()).hexdigest()[:10], 16))


def _grad(canvas, rect: skia.Rect, top: str, bottom: str) -> None:
    shader = skia.GradientShader.MakeLinear([skia.Point(rect.left(), rect.top()), skia.Point(rect.left(), rect.bottom())],
                                            [_color(top), _color(bottom)])
    canvas.drawRect(rect, skia.Paint(Shader=shader))


def _p(c: str, dark: float = 1.0, a: int = 255) -> skia.Paint:
    return skia.Paint(AntiAlias=True, Color=_color(_shade(c, dark) if dark != 1.0 else c, a))


def render_background(setting_type: str, time_of_day: str, width: int, height: int, key: str,
                      palette: dict | None = None, mood: str | None = None) -> skia.Image:
    st = setting_type if setting_type in SETTING_TYPES else "room"
    tod = time_of_day if time_of_day in PALETTES else "day"
    pal = {**PALETTES[tod], **(palette or {})}
    rng = _rng(f"{key}|{st}|{tod}")
    surf = skia.Surface(width, height)
    c = surf.getCanvas()
    W, H = width, height
    horizon = H * 0.66
    d = pal["dark"]
    outdoor = st in ("street", "city", "park", "forest", "beach", "space")
    if outdoor:
        _grad(c, skia.Rect.MakeWH(W, horizon + 4), pal["sky_top"], pal["sky_bottom"])
        if tod == "night" or st == "space":
            for _ in range(140 if st == "space" else 70):
                c.drawCircle(rng.uniform(0, W), rng.uniform(0, horizon * (1 if st != "space" else 1.5)), rng.uniform(1, 3.2),
                             _p("#ffffff", a=rng.randint(120, 255)))
            c.drawCircle(W * 0.78, H * 0.12, W * 0.06, _p("#f8fafc"))
        else:
            c.drawCircle(W * 0.8, H * 0.11, W * 0.07, _p("#fde047"))
            for _ in range(3):
                cx, cy = rng.uniform(0, W), rng.uniform(H * 0.05, H * 0.3)
                for k in range(4):
                    c.drawCircle(cx + k * W * 0.05, cy + (k % 2) * 12, W * 0.05, _p("#ffffff", a=220))
    if st in ("street", "city"):
        for i in range(9):
            bw = rng.uniform(W * 0.13, W * 0.24)
            bx = i * W * 0.12 - W * 0.05 + rng.uniform(-20, 20)
            bh = rng.uniform(H * 0.22, H * 0.48)
            col = rng.choice(["#64748b", "#475569", "#94a3b8", "#78716c", "#a8a29e"])
            c.drawRect(skia.Rect.MakeXYWH(bx, horizon - bh, bw, bh), _p(col, d))
            for wy in np.arange(horizon - bh + 25, horizon - 30, 46):
                for wx in np.arange(bx + 14, bx + bw - 20, 34):
                    lit = tod == "night" and rng.random() < 0.45
                    c.drawRect(skia.Rect.MakeXYWH(wx, wy, 18, 26), _p("#fde68a" if lit else "#cbd5e1", 1.0 if lit else d, 255))
        c.drawRect(skia.Rect.MakeLTRB(0, horizon, W, H), _p("#9ca3af", d))
        c.drawRect(skia.Rect.MakeLTRB(0, horizon + H * 0.1, W, H), _p("#374151", d))
        for x in range(0, W, 140):
            c.drawRect(skia.Rect.MakeXYWH(x + 20, horizon + H * 0.22, 80, 12), _p("#f8fafc", d))
        for x in (W * 0.12, W * 0.88):
            c.drawRect(skia.Rect.MakeXYWH(x, horizon - H * 0.2, 10, H * 0.2), _p("#1f2937"))
            c.drawCircle(x + 5, horizon - H * 0.2, 18, _p("#fef08a" if tod == "night" else "#e5e7eb"))
    elif st in ("park", "forest"):
        c.drawRect(skia.Rect.MakeLTRB(0, horizon, W, H), _p(pal["ground"], d))
        n = 14 if st == "forest" else 6
        for _ in range(n):
            tx = rng.uniform(-W * 0.05, W * 1.05)
            ty = horizon + rng.uniform(-H * 0.02, H * 0.05)
            th = rng.uniform(H * 0.18, H * 0.36) * (1.3 if st == "forest" else 1)
            c.drawRect(skia.Rect.MakeXYWH(tx - 12, ty - th * 0.45, 24, th * 0.45), _p("#78350f", d))
            green = rng.choice(["#15803d", "#16a34a", "#166534", "#22c55e"])
            for k in range(3):
                c.drawCircle(tx + rng.uniform(-30, 30), ty - th * (0.5 + 0.15 * k), th * 0.22, _p(green, d * (0.8 if st == "forest" else 1)))
        if st == "park":
            path = skia.Path()
            path.moveTo(W * 0.42, horizon)
            path.lineTo(W * 0.58, horizon)
            path.lineTo(W * 0.85, H)
            path.lineTo(W * 0.15, H)
            path.close()
            c.drawPath(path, _p("#d6d3d1", d))
            c.drawRect(skia.Rect.MakeXYWH(W * 0.68, horizon + H * 0.06, W * 0.22, 16), _p("#92400e", d))
    elif st == "beach":
        c.drawRect(skia.Rect.MakeLTRB(0, horizon - H * 0.08, W, horizon + H * 0.04), _p("#0ea5e9", d))
        for i in range(6):
            y = horizon - H * 0.06 + i * 18
            c.drawLine(rng.uniform(0, W * 0.5), y, rng.uniform(W * 0.5, W), y, skia.Paint(AntiAlias=True, Color=_color("#e0f2fe", 160), StrokeWidth=3))
        c.drawRect(skia.Rect.MakeLTRB(0, horizon + H * 0.04, W, H), _p("#fde68a", d))
    elif st == "space":
        c.drawCircle(W * 0.25, H * 0.35, W * 0.2, _p("#7c3aed"))
        c.drawOval(skia.Rect.MakeXYWH(W * 0.0, H * 0.33, W * 0.5, H * 0.05), skia.Paint(AntiAlias=True, Color=_color("#c4b5fd"), StrokeWidth=6, Style=skia.Paint.kStroke_Style))
        c.drawRect(skia.Rect.MakeLTRB(0, horizon, W, H), _p("#57534e"))
        for _ in range(8):
            c.drawOval(skia.Rect.MakeXYWH(rng.uniform(0, W), rng.uniform(horizon + 20, H - 40), rng.uniform(40, 120), rng.uniform(12, 30)), _p("#44403c"))
    elif st == "abstract":
        _grad(c, skia.Rect.MakeWH(W, H), pal.get("abstract_top", "#312e81" if tod == "night" else "#6366f1"),
              pal.get("abstract_bottom", "#0f172a" if tod == "night" else "#c084fc"))
        for _ in range(10):
            c.drawCircle(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(W * 0.05, W * 0.25), _p("#ffffff", a=rng.randint(12, 40)))
        c.drawRect(skia.Rect.MakeLTRB(0, horizon, W, H), _p("#000000", a=60))
    else:  # interiores
        wall = {"kitchen": "#e0f2fe", "office": "#e2e8f0", "school": "#d9f99d", "abandoned": "#57534e", "lab": "#f1f5f9"}.get(st, pal["wall"])
        floor = {"kitchen": "#cbd5e1", "office": "#94a3b8", "abandoned": "#44403c", "lab": "#e2e8f0"}.get(st, pal["floor"])
        dd = d * (0.55 if st == "abandoned" else 1)
        c.drawRect(skia.Rect.MakeLTRB(0, 0, W, horizon), _p(wall, dd))
        c.drawRect(skia.Rect.MakeLTRB(0, horizon, W, H), _p(floor, dd))
        c.drawRect(skia.Rect.MakeLTRB(0, horizon - 10, W, horizon + 6), _p(_shade(floor, 0.7), dd))
        # janela
        wx, wy, ww, wh = W * 0.58, H * 0.14, W * 0.3, H * 0.2
        sky = PALETTES[tod]
        _grad(c, skia.Rect.MakeXYWH(wx, wy, ww, wh), sky["sky_top"], sky["sky_bottom"])
        frame = skia.Paint(AntiAlias=True, Color=_color("#f8fafc" if st != "abandoned" else "#292524"), StrokeWidth=12, Style=skia.Paint.kStroke_Style)
        c.drawRect(skia.Rect.MakeXYWH(wx, wy, ww, wh), frame)
        c.drawLine(wx + ww / 2, wy, wx + ww / 2, wy + wh, frame)
        if st == "abandoned":
            crack = skia.Paint(AntiAlias=True, Color=_color("#1c1917"), StrokeWidth=4, Style=skia.Paint.kStroke_Style)
            p = skia.Path()
            p.moveTo(wx + ww * 0.2, wy)
            p.lineTo(wx + ww * 0.35, wy + wh * 0.4)
            p.lineTo(wx + ww * 0.25, wy + wh * 0.7)
            c.drawPath(p, crack)
            for _ in range(3):
                x0 = rng.uniform(0, W)
                p = skia.Path()
                p.moveTo(x0, 0)
                for k in range(5):
                    p.lineTo(x0 + rng.uniform(-40, 40), k * 60 + 60)
                c.drawPath(p, crack)
            web = skia.Paint(AntiAlias=True, Color=_color("#d6d3d1", 120), StrokeWidth=2, Style=skia.Paint.kStroke_Style)
            for k in range(5):
                c.drawLine(0, 0, 220 * math.cos(k * 0.35), 220 * math.sin(k * 0.35), web)
                c.drawCircle(0, 0, 40 + k * 35, web)
        elif st == "kitchen":
            c.drawRect(skia.Rect.MakeXYWH(0, horizon - H * 0.12, W * 0.5, H * 0.12), _p("#f8fafc"))
            c.drawRect(skia.Rect.MakeXYWH(0, horizon - H * 0.135, W * 0.52, 16), _p("#64748b"))
            c.drawRoundRect(skia.Rect.MakeXYWH(W * 0.06, horizon - H * 0.36, W * 0.16, H * 0.24), 14, 14, _p("#e5e7eb"))
            for gx in range(0, W, 60):
                c.drawLine(gx, horizon - H * 0.3, gx, horizon - H * 0.135, skia.Paint(Color=_color("#bae6fd"), StrokeWidth=2))
        elif st == "office":
            c.drawRect(skia.Rect.MakeXYWH(W * 0.05, horizon - H * 0.07, W * 0.45, 18), _p("#78350f"))
            c.drawRoundRect(skia.Rect.MakeXYWH(W * 0.15, horizon - H * 0.17, W * 0.22, H * 0.1), 8, 8, _p("#0f172a"))
            c.drawRect(skia.Rect.MakeXYWH(W * 0.17, horizon - H * 0.16, W * 0.18, H * 0.08), _p("#38bdf8"))
            c.drawCircle(W * 0.9, horizon - H * 0.12, W * 0.06, _p("#16a34a"))
            c.drawRect(skia.Rect.MakeXYWH(W * 0.87, horizon - H * 0.07, W * 0.06, H * 0.07), _p("#b45309"))
        elif st == "school":
            c.drawRect(skia.Rect.MakeXYWH(W * 0.05, H * 0.12, W * 0.45, H * 0.2), _p("#14532d"))
            c.drawRect(skia.Rect.MakeXYWH(W * 0.05, H * 0.12, W * 0.45, H * 0.2), skia.Paint(AntiAlias=True, Color=_color("#78350f"), StrokeWidth=10, Style=skia.Paint.kStroke_Style))
            for k in range(3):
                c.drawLine(W * 0.1, H * (0.16 + k * 0.04), W * rng.uniform(0.25, 0.45), H * (0.16 + k * 0.04), skia.Paint(AntiAlias=True, Color=_color("#f8fafc", 200), StrokeWidth=4))
        elif st == "lab":
            for k in range(3):
                y = H * (0.2 + k * 0.12)
                c.drawRect(skia.Rect.MakeXYWH(W * 0.04, y, W * 0.4, 10), _p("#94a3b8"))
                for j in range(4):
                    col = rng.choice(["#22d3ee", "#a3e635", "#f472b6", "#facc15"])
                    c.drawRoundRect(skia.Rect.MakeXYWH(W * 0.06 + j * W * 0.09, y - 50, 30, 50), 10, 10, _p(col, a=200))
        else:  # quarto/sala
            c.drawRect(skia.Rect.MakeXYWH(W * 0.1, H * 0.16, W * 0.22, H * 0.14), _p("#a16207"))
            c.drawRect(skia.Rect.MakeXYWH(W * 0.12, H * 0.17, W * 0.18, H * 0.12), _p(rng.choice(["#60a5fa", "#f472b6", "#34d399"])))
            c.drawRoundRect(skia.Rect.MakeXYWH(W * 0.02, horizon - H * 0.09, W * 0.4, H * 0.09), 24, 24, _p(rng.choice(["#9333ea", "#2563eb", "#dc2626", "#0d9488"]), d))
            c.drawRect(skia.Rect.MakeXYWH(W * 0.83, horizon - H * 0.22, 8, H * 0.22), _p("#1f2937", d))
            c.drawCircle(W * 0.834, horizon - H * 0.23, 34, _p("#fde68a" if tod == "night" else "#f5f5f4"))
        if tod == "night" and st != "abandoned":
            c.drawRect(skia.Rect.MakeWH(W, H), _p("#0f172a", a=90))
    # vinheta para clima sombrio
    if mood in ("dark", "suspense", "dread", "fear") or st == "abandoned":
        shader = skia.GradientShader.MakeRadial(skia.Point(W / 2, H / 2), max(W, H) * 0.7,
                                                [_color("#000000", 0), _color("#000000", 200)], [0.45, 1.0])
        c.drawRect(skia.Rect.MakeWH(W, H), skia.Paint(Shader=shader))
    return surf.makeImageSnapshot()


def background_png(setting_type: str, time_of_day: str, width: int, height: int, key: str, palette=None, mood=None) -> bytes:
    img = render_background(setting_type, time_of_day, width, height, key, palette, mood)
    return bytes(img.encodeToData(skia.EncodedImageFormat.kPNG, 100))
