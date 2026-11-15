"""Renderização de uma cena (animação 2D ou imagem com movimento de câmera) para MP4 (somente vídeo)."""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import skia

from app.media.animation.rig import CharacterRig, FaceState, pose_for
from app.media.animation.text import draw_text_block
from app.media.ffmpeg import MediaError, ffmpeg_bin

WORLD_MARGIN = 1.16  # mundo maior que o quadro para permitir pan/zoom


@dataclass
class CharacterTrack:
    spec: dict
    x: float = 0.5  # posição horizontal (fração da largura do mundo)
    action: str = "idle"
    expression: str = "neutral"
    facing: int = 1
    scale: float = 1.0
    walk_to: float | None = None  # se definido, desloca até esta posição durante a cena
    speaking: list[tuple[float, float, str]] = field(default_factory=list)  # (início, fim, emoção)
    envelope: np.ndarray | None = None  # amplitude (0..1) por quadro
    phase: float = 0.0


@dataclass
class SceneRenderSpec:
    width: int
    height: int
    fps: int
    duration_s: float
    background: skia.Image | None = None
    characters: list[CharacterTrack] = field(default_factory=list)
    camera: str = "static"
    overlay_text: str = ""
    text_style: dict = field(default_factory=dict)
    fade_in: float = 0.0
    fade_out: float = 0.0
    tint: str | None = None
    seed: int = 0


def _camera(cam: str, p: float, t: float, seed: int) -> tuple[float, float, float]:
    """Retorna (zoom, offset_x, offset_y) normalizados; p = progresso 0..1."""
    ease = p * p * (3 - 2 * p)
    if cam == "zoom_in":
        return 1.0 + 0.12 * ease, 0, 0
    if cam == "zoom_out":
        return 1.12 - 0.12 * ease, 0, 0
    if cam == "slow_zoom":
        return 1.0 + 0.06 * p, 0, 0
    if cam == "pan_left":
        return 1.04, 0.05 - 0.1 * ease, 0
    if cam == "pan_right":
        return 1.04, -0.05 + 0.1 * ease, 0
    if cam == "shake":
        amp = 0.012
        return 1.06, amp * math.sin(t * 41 + seed), amp * math.cos(t * 37 + seed)
    return 1.0, 0, 0


def render_scene(spec: SceneRenderSpec, out_path: Path, *, render_scale: float = 1.0, crf: int = 20,
                 progress_cb=None) -> Path:
    W, H = spec.width, spec.height
    rw, rh = max(2, int(W * render_scale) // 2 * 2), max(2, int(H * render_scale) // 2 * 2)
    frames = max(1, int(round(spec.duration_s * spec.fps)))
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra",
           "-s", f"{rw}x{rh}", "-r", str(spec.fps), "-i", "-", "-vf", f"scale={W}:{H}:flags=lanczos,format=yuv420p",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-r", str(spec.fps), str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    surface = skia.Surface(rw, rh)
    canvas = surface.getCanvas()
    rigs = [(tr, CharacterRig(tr.spec)) for tr in spec.characters]
    ww, wh = rw * WORLD_MARGIN, rh * WORLD_MARGIN
    bg = spec.background
    text_style = {"color": "#ffffff", "stroke": "#000000", "size": 0.06, "top": 0.1, **spec.text_style}
    try:
        for f in range(frames):
            t = f / spec.fps
            p = f / max(1, frames - 1)
            zoom, ox, oy = _camera(spec.camera, p, t, spec.seed)
            canvas.clear(skia.ColorBLACK)
            canvas.save()
            # câmera: centraliza o mundo, aplica zoom e deslocamento
            canvas.translate(rw / 2 + ox * rw, rh / 2 + oy * rh)
            canvas.scale(zoom, zoom)
            canvas.translate(-ww / 2, -wh / 2)
            if bg is not None:
                # "cover" do fundo no mundo
                s = max(ww / bg.width(), wh / bg.height())
                dw, dh = bg.width() * s, bg.height() * s
                canvas.drawImageRect(bg, skia.Rect.MakeXYWH((ww - dw) / 2, (wh - dh) / 2, dw, dh),
                                     skia.SamplingOptions(skia.FilterMode.kLinear))
            ground = wh * 0.83
            char_h = rh * 0.36
            for tr, rig in rigs:
                speaking_now = None
                for (a, b, emo) in tr.speaking:
                    if a <= t < b:
                        speaking_now = emo
                        break
                x = tr.x
                action = tr.action
                if tr.walk_to is not None:
                    x = tr.x + (tr.walk_to - tr.x) * min(1.0, p * 1.15)
                    if p * 1.15 >= 1.0 and action == "walk":
                        action = "idle"
                if speaking_now and action == "idle":
                    action = "talk"
                pose = pose_for(action, t, speaking=bool(speaking_now), phase=tr.phase)
                amp = 0.0
                if speaking_now and tr.envelope is not None and f < len(tr.envelope):
                    amp = float(tr.envelope[f])
                elif speaking_now:
                    amp = 0.5 + 0.5 * math.sin(t * 18)
                blink = ((t + tr.phase * 1.7) % 3.7) < 0.12
                expr = speaking_now if speaking_now and speaking_now not in ("neutral", None) else tr.expression
                face = FaceState(expression=expr or "neutral", mouth_open=amp, blink=blink)
                rig.draw(canvas, x * ww, ground, char_h * tr.scale, pose, face, tr.facing)
            canvas.restore()
            if spec.tint:
                canvas.drawRect(skia.Rect.MakeWH(rw, rh), skia.Paint(Color=skia.Color4f.FromColor(skia.Color(*_hex_rgb(spec.tint))).toColor()))
            if spec.overlay_text:
                appear = min(1.0, t / 0.35)
                size = rh * text_style["size"]
                canvas.save()
                canvas.translate(0, (1 - appear) * -20)
                draw_text_block(canvas, spec.overlay_text.upper(), rw / 2, rh * text_style["top"], rw * 0.86, size,
                                _argb(text_style["color"], int(255 * appear)), _argb(text_style["stroke"], int(255 * appear)),
                                size * 0.16, text_style.get("font"))
                canvas.restore()
            alpha = 1.0
            if spec.fade_in and t < spec.fade_in:
                alpha = t / spec.fade_in
            if spec.fade_out and t > spec.duration_s - spec.fade_out:
                alpha = min(alpha, max(0.0, (spec.duration_s - t) / spec.fade_out))
            if alpha < 1.0:
                canvas.drawRect(skia.Rect.MakeWH(rw, rh), skia.Paint(Color=skia.ColorSetARGB(int(255 * (1 - alpha)), 0, 0, 0)))
            proc.stdin.write(surface.toarray().tobytes())  # type: ignore[union-attr]
            if progress_cb and f % 30 == 0:
                progress_cb(f / frames)
        proc.stdin.close()  # type: ignore[union-attr]
        err = proc.stderr.read().decode(errors="replace")  # type: ignore[union-attr]
        if proc.wait(timeout=600) != 0:
            raise MediaError(f"ffmpeg (cena) falhou: {err[-800:]}")
    except BrokenPipeError as e:
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise MediaError(f"ffmpeg encerrou durante a renderização: {err[-800:]}") from e
    finally:
        if proc.poll() is None:
            proc.kill()
    return out_path


def _hex_rgb(h: str) -> tuple[int, int, int, int]:
    h = h.lstrip("#")
    a = int(h[6:8], 16) if len(h) == 8 else 80
    return a, int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _argb(h: str, a: int) -> int:
    h = h.lstrip("#")
    return skia.ColorSetARGB(a, int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def load_image(data: bytes) -> skia.Image:
    img = skia.Image.MakeFromEncoded(skia.Data.MakeWithCopy(data))
    if img is None:
        raise MediaError("imagem inválida ou corrompida")
    return img
