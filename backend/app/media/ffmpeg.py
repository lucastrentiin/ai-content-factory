"""Wrappers de FFmpeg/FFprobe com timeout e erros claros."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import settings


class MediaError(Exception):
    pass


def ffmpeg_bin() -> str:
    b = shutil.which("ffmpeg")
    if not b:
        raise MediaError("ffmpeg não encontrado no PATH")
    return b


def run_ffmpeg(args: list[str], *, timeout: int | None = None, cwd: Path | None = None) -> str:
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout or settings.render_timeout_s, cwd=cwd)
    except subprocess.TimeoutExpired as e:
        raise MediaError(f"ffmpeg excedeu o tempo limite: {' '.join(args[:6])}…") from e
    if proc.returncode != 0:
        raise MediaError(f"ffmpeg falhou ({proc.returncode}): {proc.stderr.decode(errors='replace')[-1500:]}")
    return proc.stderr.decode(errors="replace")


def run_ffmpeg_analysis(args: list[str], timeout: int = 600) -> str:
    """Executa ffmpeg retornando stderr com nível info (para filtros de análise: ebur128, blackdetect...)."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostats", "-loglevel", "info", *args]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise MediaError(f"análise ffmpeg falhou: {proc.stderr.decode(errors='replace')[-800:]}")
    return proc.stderr.decode(errors="replace")


def probe(path: Path) -> dict[str, Any]:
    b = shutil.which("ffprobe")
    if not b:
        raise MediaError("ffprobe não encontrado")
    proc = subprocess.run([b, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                          capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise MediaError(f"ffprobe falhou: {proc.stderr.decode(errors='replace')[:500]}")
    return json.loads(proc.stdout)


def media_duration(path: Path) -> float:
    info = probe(path)
    d = info.get("format", {}).get("duration")
    if d is None:
        for s in info.get("streams", []):
            if s.get("duration"):
                return float(s["duration"])
        return 0.0
    return float(d)


def to_wav(src: Path, dest: Path, sr: int = 44100) -> Path:
    run_ffmpeg(["-i", str(src), "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dest)])
    return dest
