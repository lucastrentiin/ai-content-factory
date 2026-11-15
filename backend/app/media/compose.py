"""Composição: normalização de clipes externos, concatenação de cenas e geração de capa."""
from __future__ import annotations

from pathlib import Path

import skia

from app.media.animation.scene_renderer import load_image
from app.media.animation.text import draw_text_block
from app.media.ffmpeg import media_duration, run_ffmpeg


def normalize_clip(src: Path, dest: Path, *, width: int, height: int, fps: int, duration: float, crf: int = 20) -> Path:
    """Ajusta clipe de vídeo de IA: cover-crop para WxH, fps, duração exata (loop se curto), sem áudio."""
    src_d = media_duration(src) or duration
    loops = max(0, int(duration // max(0.1, src_d)))
    run_ffmpeg(["-stream_loop", str(loops), "-i", str(src), "-t", f"{duration:.3f}", "-an",
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), str(dest)])
    return dest


def concat_clips(clips: list[Path], dest: Path) -> Path:
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(dest)])
    return dest


def extract_frame(video: Path, t: float, dest: Path) -> Path:
    run_ffmpeg(["-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(dest)])
    return dest


def make_thumbnail(frame_png: Path, title: str, dest: Path, *, accent: str = "#facc15", width: int = 1080, height: int = 1920) -> Path:
    img = load_image(frame_png.read_bytes())
    surf = skia.Surface(width, height)
    c = surf.getCanvas()
    s = max(width / img.width(), height / img.height())
    c.drawImageRect(img, skia.Rect.MakeXYWH((width - img.width() * s) / 2, (height - img.height() * s) / 2, img.width() * s, img.height() * s),
                    skia.SamplingOptions(skia.FilterMode.kLinear))
    shader = skia.GradientShader.MakeLinear([skia.Point(0, height * 0.45), skia.Point(0, height)],
                                            [skia.ColorSetARGB(0, 0, 0, 0), skia.ColorSetARGB(220, 0, 0, 0)])
    c.drawRect(skia.Rect.MakeWH(width, height), skia.Paint(Shader=shader))
    h = accent.lstrip("#")
    col = skia.ColorSetARGB(255, int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    draw_text_block(c, title.upper(), width / 2, height * 0.66, width * 0.86, height * 0.055, col, skia.ColorBLACK, height * 0.009)
    data = surf.makeImageSnapshot().encodeToData(skia.EncodedImageFormat.kJPEG, 90)
    dest.write_bytes(bytes(data))
    return dest
