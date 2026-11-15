"""Rig 2D articulado (stickman e cartoon) desenhado com Skia.

A aparência é 100% determinada por `visual_spec` do personagem → consistência entre vídeos/episódios.
Poses são ângulos de articulações; ações animam as poses ao longo do tempo; expressões alteram olhos,
sobrancelhas e boca; a abertura da boca acompanha a amplitude da fala (lip-sync aproximado).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import skia


def _color(hexstr: str, alpha: int = 255) -> int:
    h = (hexstr or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return skia.ColorSetARGB(alpha, r, g, b)


def _shade(hexstr: str, f: float) -> str:
    h = (hexstr or "#888888").lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    if f < 1:
        r, g, b = (int(c * f) for c in (r, g, b))
    else:
        r, g, b = (int(c + (255 - c) * (f - 1)) for c in (r, g, b))
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


DEFAULT_SPEC: dict[str, Any] = {
    "style": "stickman",  # stickman | cartoon
    "line_color": "#111827",
    "skin_tone": "#f1c27d",
    "outfit_color": "#3b82f6",
    "pants_color": "#1f2937",
    "hair": "short",  # short|long|spiky|bun|curly|bald|ponytail
    "hair_color": "#3f2a1d",
    "accessories": [],  # glasses|hat|scarf|backpack|bow
    "height": 1.0,
    "build": 1.0,  # largura
    "head_fill": "#ffffff",
    "eye_color": "#111827",
}


@dataclass
class Pose:
    lean: float = 0.0  # inclinação do tronco (rad)
    head_tilt: float = 0.0
    l_shoulder: float = 0.35  # ângulo do braço a partir da vertical para baixo (rad), positivo = para frente
    l_elbow: float = 0.15
    r_shoulder: float = -0.35
    r_elbow: float = -0.15
    l_hip: float = 0.08
    l_knee: float = 0.0
    r_hip: float = -0.08
    r_knee: float = 0.0
    dy: float = 0.0  # deslocamento vertical (fração da altura)
    dx: float = 0.0  # deslocamento horizontal (fração da altura)
    crouch: float = 0.0  # 0..1
    tremble: float = 0.0


@dataclass
class FaceState:
    expression: str = "neutral"
    mouth_open: float = 0.0  # 0..1
    blink: bool = False
    look: float = 0.0  # -1 esquerda .. 1 direita


@dataclass
class CharacterRig:
    spec: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.spec = {**DEFAULT_SPEC, **(self.spec or {})}

    # ------------------------------------------------------------------ desenho
    def draw(self, canvas: skia.Canvas, x: float, ground_y: float, height_px: float, pose: Pose, face: FaceState,
             facing: int = 1) -> None:
        s = self.spec
        H = height_px * float(s.get("height", 1.0))
        cartoon = s.get("style") == "cartoon"
        canvas.save()
        canvas.translate(x + pose.dx * H, ground_y - pose.dy * H)
        if pose.tremble:
            canvas.translate(math.sin(pose.tremble * 97) * H * 0.006, 0)
        if facing < 0:
            canvas.scale(-1, 1)
        # proporções
        head_r = H * (0.13 if cartoon else 0.11)
        leg_len = H * 0.42 * (1 - 0.35 * pose.crouch)
        torso_len = H * (0.30 if cartoon else 0.32)
        arm_len = H * 0.30
        hip = (0.0, -leg_len)
        neck = (hip[0] + math.sin(pose.lean) * torso_len, hip[1] - math.cos(pose.lean) * torso_len)
        head_c = (neck[0] + math.sin(pose.lean + pose.head_tilt) * head_r * 1.05,
                  neck[1] - math.cos(pose.lean + pose.head_tilt) * head_r * 1.05)
        shoulder = (hip[0] + (neck[0] - hip[0]) * 0.86, hip[1] + (neck[1] - hip[1]) * 0.86)
        lw = H * (0.032 if not cartoon else 0.05)
        line = s["line_color"]

        def limb(origin, a1, a2, length, color, width):
            l1 = length * 0.5
            p1 = (origin[0] + math.sin(a1) * l1, origin[1] + math.cos(a1) * l1)
            p2 = (p1[0] + math.sin(a1 + a2) * l1, p1[1] + math.cos(a1 + a2) * l1)
            paint = skia.Paint(AntiAlias=True, Color=_color(color), StrokeWidth=width, Style=skia.Paint.kStroke_Style,
                               StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)
            path = skia.Path()
            path.moveTo(*origin)
            path.lineTo(*p1)
            path.lineTo(*p2)
            canvas.drawPath(path, paint)
            return p2

        knee_bend = pose.crouch * 1.2
        if cartoon:
            leg_w, arm_w = H * 0.07 * s["build"], H * 0.055 * s["build"]
            # pernas atrás
            limb(hip, pose.r_hip - knee_bend * 0.5, pose.r_knee + knee_bend, leg_len, s["pants_color"], leg_w)
            limb(hip, pose.l_hip - knee_bend * 0.5, pose.l_knee + knee_bend, leg_len, s["pants_color"], leg_w)
            # braço de trás
            limb(shoulder, pose.r_shoulder, pose.r_elbow, arm_len, s["skin_tone"], arm_w)
            # tronco
            torso = skia.Path()
            tw = H * 0.12 * s["build"]
            canvas.save()
            canvas.translate(*hip)
            canvas.rotate(math.degrees(pose.lean))
            rect = skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(-tw, -torso_len * 1.02, tw, H * 0.03), tw * 0.8, tw * 0.6)
            torso.addRRect(rect)
            canvas.drawPath(torso, skia.Paint(AntiAlias=True, Color=_color(s["outfit_color"])))
            canvas.drawPath(torso, skia.Paint(AntiAlias=True, Color=_color(_shade(s["outfit_color"], 0.6)), StrokeWidth=lw * 0.35, Style=skia.Paint.kStroke_Style))
            if "scarf" in s["accessories"]:
                canvas.drawRect(skia.Rect.MakeLTRB(-tw * 1.05, -torso_len * 1.02, tw * 1.05, -torso_len * 0.86), skia.Paint(AntiAlias=True, Color=_color("#dc2626")))
            canvas.restore()
            if "backpack" in s["accessories"]:
                canvas.drawRoundRect(skia.Rect.MakeXYWH(hip[0] - tw * 1.9, hip[1] - torso_len * 0.85, tw * 0.9, torso_len * 0.6), 8, 8, skia.Paint(AntiAlias=True, Color=_color("#7c2d12")))
            limb(shoulder, pose.l_shoulder, pose.l_elbow, arm_len, s["skin_tone"], arm_w)
        else:
            limb(hip, pose.r_hip - knee_bend * 0.5, pose.r_knee + knee_bend, leg_len, line, lw)
            limb(hip, pose.l_hip - knee_bend * 0.5, pose.l_knee + knee_bend, leg_len, line, lw)
            body = skia.Paint(AntiAlias=True, Color=_color(line), StrokeWidth=lw, Style=skia.Paint.kStroke_Style, StrokeCap=skia.Paint.kRound_Cap)
            canvas.drawLine(*hip, *neck, body)
            # detalhe de cor do personagem (camiseta) para diferenciá-los
            shirt = skia.Paint(AntiAlias=True, Color=_color(s["outfit_color"]), StrokeWidth=lw * 2.2, Style=skia.Paint.kStroke_Style, StrokeCap=skia.Paint.kRound_Cap)
            canvas.drawLine(hip[0] + (neck[0] - hip[0]) * 0.25, hip[1] + (neck[1] - hip[1]) * 0.25,
                            hip[0] + (neck[0] - hip[0]) * 0.85, hip[1] + (neck[1] - hip[1]) * 0.85, shirt)
            limb(shoulder, pose.r_shoulder, pose.r_elbow, arm_len, line, lw)
            limb(shoulder, pose.l_shoulder, pose.l_elbow, arm_len, line, lw)
            if "scarf" in s["accessories"]:
                canvas.drawCircle(neck[0], neck[1] + lw, lw * 1.3, skia.Paint(AntiAlias=True, Color=_color("#dc2626")))
        self._draw_head(canvas, head_c, head_r, pose.lean + pose.head_tilt, face, lw, cartoon)
        canvas.restore()

    def _draw_head(self, canvas, c, r, angle, face: FaceState, lw, cartoon) -> None:
        s = self.spec
        canvas.save()
        canvas.translate(*c)
        canvas.rotate(math.degrees(angle))
        hair_paint = skia.Paint(AntiAlias=True, Color=_color(s["hair_color"]))
        hair = s.get("hair", "short")
        # cabelo de trás
        if hair in ("long", "ponytail"):
            if hair == "long":
                canvas.drawRoundRect(skia.Rect.MakeLTRB(-r * 1.08, -r * 0.6, r * 1.08, r * 1.25), r * 0.5, r * 0.5, hair_paint)
            else:
                canvas.drawOval(skia.Rect.MakeLTRB(-r * 1.55, -r * 0.6, -r * 0.75, r * 0.9), hair_paint)
        if hair == "bun":
            canvas.drawCircle(0, -r * 1.05, r * 0.42, hair_paint)
        fill = s["skin_tone"] if cartoon else s.get("head_fill", "#ffffff")
        canvas.drawCircle(0, 0, r, skia.Paint(AntiAlias=True, Color=_color(fill)))
        canvas.drawCircle(0, 0, r, skia.Paint(AntiAlias=True, Color=_color(s["line_color"]), StrokeWidth=lw * (0.9 if not cartoon else 0.45),
                                              Style=skia.Paint.kStroke_Style))
        # cabelo de frente
        if hair in ("short", "long", "ponytail", "bun"):
            p = skia.Path()
            p.addArc(skia.Rect.MakeLTRB(-r * 1.04, -r * 1.06, r * 1.04, r * 1.0), 180, 180)
            p.close()
            canvas.save()
            canvas.clipRect(skia.Rect.MakeLTRB(-r * 1.2, -r * 1.2, r * 1.2, -r * 0.38))
            canvas.drawPath(p, hair_paint)
            canvas.restore()
        elif hair == "spiky":
            p = skia.Path()
            p.moveTo(-r, -r * 0.3)
            for i in range(7):
                ang = math.pi + i * math.pi / 6
                tip = 1.45 if i % 2 else 1.02
                p.lineTo(math.cos(ang + 0.2) * r * tip, math.sin(ang + 0.2) * r * tip)
            p.lineTo(r, -r * 0.3)
            p.close()
            canvas.drawPath(p, hair_paint)
        elif hair == "curly":
            for i in range(9):
                ang = math.pi + i * math.pi / 8
                canvas.drawCircle(math.cos(ang) * r * 0.95, math.sin(ang) * r * 0.95, r * 0.3, hair_paint)
        self._draw_face(canvas, r, face, lw, cartoon)
        acc = s.get("accessories", [])
        if "glasses" in acc:
            gp = skia.Paint(AntiAlias=True, Color=_color("#111827"), StrokeWidth=lw * 0.35, Style=skia.Paint.kStroke_Style)
            canvas.drawCircle(r * 0.08, -r * 0.08, r * 0.24, gp)
            canvas.drawCircle(r * 0.62, -r * 0.08, r * 0.24, gp)
            canvas.drawLine(r * 0.32, -r * 0.08, r * 0.38, -r * 0.08, gp)
        if "hat" in acc:
            hp = skia.Paint(AntiAlias=True, Color=_color(_shade(s["outfit_color"], 0.55)))
            canvas.drawRect(skia.Rect.MakeLTRB(-r * 1.25, -r * 0.82, r * 1.25, -r * 0.66), hp)
            canvas.drawRoundRect(skia.Rect.MakeLTRB(-r * 0.78, -r * 1.55, r * 0.78, -r * 0.72), r * 0.2, r * 0.2, hp)
        if "bow" in acc:
            bp = skia.Paint(AntiAlias=True, Color=_color("#ec4899"))
            canvas.drawCircle(-r * 0.55, -r * 0.95, r * 0.22, bp)
            canvas.drawCircle(-r * 0.2, -r * 1.02, r * 0.22, bp)
        canvas.restore()

    def _draw_face(self, canvas, r, face: FaceState, lw, cartoon) -> None:
        s = self.spec
        e = face.expression
        ink = skia.Paint(AntiAlias=True, Color=_color(s["eye_color"]))
        stroke = skia.Paint(AntiAlias=True, Color=_color(s["line_color"]), StrokeWidth=max(2.0, lw * 0.4),
                            Style=skia.Paint.kStroke_Style, StrokeCap=skia.Paint.kRound_Cap)
        ex = [r * 0.08, r * 0.62]  # rosto voltado para a direita (frente)
        ey = -r * 0.08
        eye_r = r * (0.16 if cartoon else 0.11)
        look = face.look * r * 0.05
        for x in ex:
            if face.blink:
                canvas.drawLine(x - eye_r, ey, x + eye_r, ey, stroke)
            elif e == "happy":
                p = skia.Path()
                p.addArc(skia.Rect.MakeLTRB(x - eye_r, ey - eye_r * 0.6, x + eye_r, ey + eye_r * 1.2), 200, 140)
                canvas.drawPath(p, stroke)
            else:
                scale = 1.35 if e in ("surprised", "scared", "fear") else (0.75 if e in ("angry", "thinking") else 1.0)
                if cartoon:
                    canvas.drawCircle(x, ey, eye_r * scale, skia.Paint(AntiAlias=True, Color=_color("#ffffff")))
                    canvas.drawCircle(x, ey, eye_r * scale, stroke)
                    canvas.drawCircle(x + look + eye_r * 0.15, ey, eye_r * 0.5 * min(scale, 1.1), ink)
                else:
                    canvas.drawCircle(x + look, ey, eye_r * scale * 0.75, ink)
        # sobrancelhas
        by = ey - eye_r * 2.0
        brow = {"angry": (0.35, -0.35), "sad": (-0.3, 0.3), "scared": (-0.35, 0.35), "fear": (-0.35, 0.35),
                "surprised": (0.0, 0.0), "thinking": (0.25, -0.05)}.get(e)
        if brow is not None or cartoon:
            a, b = brow or (0.0, 0.0)
            lift = -eye_r * 0.6 if e == "surprised" else 0
            canvas.drawLine(ex[0] - eye_r, by + lift - a * eye_r * 1.5, ex[0] + eye_r, by + lift + a * eye_r * 1.5, stroke)
            canvas.drawLine(ex[1] - eye_r, by + lift + b * eye_r * 1.5, ex[1] + eye_r, by + lift - b * eye_r * 1.5, stroke)
        # boca
        mx, my, mw = r * 0.38, r * 0.45, r * 0.42
        if face.mouth_open > 0.08:
            h = mw * (0.25 + face.mouth_open * 0.75)
            canvas.drawOval(skia.Rect.MakeLTRB(mx - mw * 0.55, my - h * 0.5, mx + mw * 0.55, my + h * 0.5),
                            skia.Paint(AntiAlias=True, Color=_color("#7f1d1d")))
            canvas.drawOval(skia.Rect.MakeLTRB(mx - mw * 0.55, my - h * 0.5, mx + mw * 0.55, my + h * 0.5), stroke)
            return
        p = skia.Path()
        if e == "happy":
            p.addArc(skia.Rect.MakeLTRB(mx - mw, my - mw * 0.9, mx + mw, my + mw * 0.6), 20, 140)
        elif e in ("sad", "dread"):
            p.addArc(skia.Rect.MakeLTRB(mx - mw * 0.8, my, mx + mw * 0.8, my + mw * 1.1), 200, 140)
        elif e in ("surprised",):
            canvas.drawCircle(mx, my, mw * 0.32, stroke)
            return
        elif e in ("scared", "fear"):
            p.moveTo(mx - mw, my)
            for i in range(1, 7):
                p.lineTo(mx - mw + i * mw / 3, my + (mw * 0.14 if i % 2 else -mw * 0.14))
        elif e == "angry":
            p.moveTo(mx - mw * 0.8, my + mw * 0.15)
            p.lineTo(mx + mw * 0.8, my - mw * 0.05)
        elif e == "thinking":
            p.moveTo(mx - mw * 0.5, my + mw * 0.1)
            p.quadTo(mx, my - mw * 0.1, mx + mw * 0.6, my + mw * 0.05)
        else:
            p.moveTo(mx - mw * 0.7, my)
            p.quadTo(mx, my + mw * 0.22, mx + mw * 0.7, my)
        canvas.drawPath(p, stroke)


# ---------------------------------------------------------------------- ações (animação procedural)
ACTIONS = ("idle", "talk", "walk", "run", "wave", "point", "jump", "shrug", "cower", "think", "dance", "sit")


def pose_for(action: str, t: float, speaking: bool = False, phase: float = 0.0) -> Pose:
    """Retorna a pose da ação no instante t (segundos)."""
    tt = t + phase
    breathe = math.sin(tt * 2.2) * 0.012
    p = Pose(dy=breathe * 0.3, head_tilt=math.sin(tt * 1.3) * 0.03)
    if action in ("walk", "run"):
        sp = 9.0 if action == "run" else 6.0
        sw = math.sin(tt * sp)
        amp = 0.65 if action == "run" else 0.45
        p.l_hip, p.r_hip = sw * amp, -sw * amp
        p.l_knee, p.r_knee = max(0, -sw) * 0.6, max(0, sw) * 0.6
        p.l_shoulder, p.r_shoulder = -sw * amp * 0.9, sw * amp * 0.9
        p.l_elbow, p.r_elbow = -0.4, -0.4
        p.dy = abs(math.sin(tt * sp)) * 0.02
        p.lean = 0.12 if action == "run" else 0.04
    elif action == "wave":
        p.l_shoulder = math.pi * 0.85
        p.l_elbow = 0.5 + math.sin(tt * 9) * 0.45
    elif action == "point":
        p.l_shoulder = math.pi * 0.5
        p.l_elbow = 0.05
        p.lean = 0.04
    elif action == "jump":
        ph = (tt * 1.6) % 1.0
        h = max(0.0, math.sin(ph * math.pi))
        p.dy = h * 0.22
        p.crouch = 0.4 * (1 - h) if ph < 0.15 or ph > 0.85 else 0
        p.l_shoulder, p.r_shoulder = math.pi * 0.8 * h + 0.3, -math.pi * 0.8 * h - 0.3
    elif action == "shrug":
        k = (math.sin(tt * 3) + 1) / 2
        p.l_shoulder, p.r_shoulder = 0.9 + 0.4 * k, -0.9 - 0.4 * k
        p.l_elbow, p.r_elbow = 1.9, -1.9
        p.head_tilt = 0.15 * k
    elif action == "cower":
        p.crouch = 0.55
        p.l_shoulder, p.r_shoulder = math.pi * 0.9, math.pi * 0.75
        p.l_elbow, p.r_elbow = 1.7, 1.9
        p.lean = 0.25
        p.tremble = tt
    elif action == "think":
        p.l_shoulder = 0.9
        p.l_elbow = 2.3
        p.head_tilt = 0.12
    elif action == "dance":
        sw = math.sin(tt * 7)
        p.l_shoulder, p.r_shoulder = math.pi * 0.7 + sw * 0.5, -math.pi * 0.7 + sw * 0.5
        p.l_hip, p.r_hip = 0.2 + sw * 0.25, -0.2 + sw * 0.25
        p.lean = sw * 0.1
        p.dy = abs(sw) * 0.04
    elif action == "sit":
        p.crouch = 0.75
        p.l_hip = p.r_hip = 1.2
        p.l_knee = p.r_knee = -1.3
    if speaking and action in ("idle", "talk", "point", "think"):
        g = math.sin(tt * 4.2)
        p.r_shoulder = -0.45 - max(0.0, g) * 0.8
        p.r_elbow = -0.9 - max(0.0, g) * 0.5
        p.head_tilt += math.sin(tt * 5.5) * 0.05
    return p
