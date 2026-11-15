"""Controle de qualidade técnico do vídeo final (resolução, proporção, duração, áudio, loudness, quadros pretos,
silêncios, legendas, tamanho) — retorna checagens com status e ação de correção sugerida."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.media.ffmpeg import MediaError, probe, run_ffmpeg_analysis


@dataclass
class Check:
    key: str
    status: str  # ok | warn | fail
    detail: str
    fix: str | None = None  # rerender_scene:<i> | regenerate_audio:<i> | rerender_final | manual


def technical_checks(video: Path, *, width: int, height: int, fps: int, target_duration: float,
                     min_duration: float, max_duration: float, max_file_mb: int, loudness_range: tuple[float, float],
                     max_black_ratio: float = 0.15, subtitles_expected: bool = True, subtitles_path: Path | None = None) -> list[Check]:
    checks: list[Check] = []
    try:
        info = probe(video)
    except MediaError as e:
        return [Check("file_readable", "fail", f"Arquivo ilegível/corrompido: {e}", "rerender_final")]
    vs = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    aus = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
    dur = float(info["format"].get("duration", 0))
    size_mb = int(info["format"].get("size", 0)) / 1e6
    if not vs:
        return [Check("video_stream", "fail", "Sem trilha de vídeo", "rerender_final")]
    w, h = int(vs["width"]), int(vs["height"])
    checks.append(Check("resolution", "ok" if (w, h) == (width, height) else "fail", f"{w}x{h} (esperado {width}x{height})",
                        None if (w, h) == (width, height) else "rerender_final"))
    ar_ok = abs(w / h - width / height) < 0.01
    checks.append(Check("aspect_ratio", "ok" if ar_ok else "fail", f"{w}:{h}", None if ar_ok else "rerender_final"))
    num, den = (vs.get("r_frame_rate") or "0/1").split("/")
    vfps = float(num) / float(den or 1)
    checks.append(Check("fps", "ok" if abs(vfps - fps) < 0.5 else "warn", f"{vfps:.2f} fps"))
    if dur < min_duration or dur > max_duration:
        checks.append(Check("duration", "fail", f"{dur:.1f}s fora do limite da plataforma ({min_duration}-{max_duration}s)", "manual"))
    else:
        dev = abs(dur - target_duration) / max(1, target_duration)
        checks.append(Check("duration", "ok" if dev < 0.35 else "warn", f"{dur:.1f}s (alvo {target_duration:.0f}s)"))
    checks.append(Check("file_size", "ok" if size_mb <= max_file_mb else "fail", f"{size_mb:.1f} MB (máx {max_file_mb} MB)"))
    if not aus:
        checks.append(Check("audio_stream", "fail", "Sem trilha de áudio", "rerender_final"))
    else:
        checks.append(Check("audio_stream", "ok", f"{aus.get('codec_name')} {aus.get('sample_rate')} Hz"))
        try:
            out = run_ffmpeg_analysis(["-i", str(video), "-map", "0:a:0", "-af", "ebur128=framelog=quiet", "-f", "null", "-"])
            m = re.findall(r"I:\s+(-?[\d.]+) LUFS", out)
            lufs = float(m[-1]) if m else None
            lo, hi = loudness_range
            if lufs is None:
                checks.append(Check("loudness", "warn", "Não foi possível medir loudness"))
            else:
                checks.append(Check("loudness", "ok" if lo <= lufs <= hi else "warn", f"{lufs:.1f} LUFS (faixa {lo}..{hi})",
                                    None if lo <= lufs <= hi else "rerender_final"))
            out = run_ffmpeg_analysis(["-i", str(video), "-map", "0:a:0", "-af", "silencedetect=noise=-45dB:d=2.5", "-f", "null", "-"])
            silences = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", out)]
            total_sil = sum(silences)
            checks.append(Check("silence", "ok" if total_sil < dur * 0.25 else "warn",
                                f"{len(silences)} trecho(s) de silêncio > 2.5s, total {total_sil:.1f}s"))
        except MediaError as e:
            checks.append(Check("audio_analysis", "warn", f"Análise de áudio falhou: {e}"))
    try:
        out = run_ffmpeg_analysis(["-i", str(video), "-vf", "blackdetect=d=0.5:pix_th=0.06", "-an", "-f", "null", "-"])
        blacks = [float(x) for x in re.findall(r"black_duration:([\d.]+)", out)]
        ratio = sum(blacks) / max(dur, 0.1)
        checks.append(Check("black_frames", "ok" if ratio <= max_black_ratio else "fail",
                            f"{ratio * 100:.1f}% do vídeo em quadros pretos", None if ratio <= max_black_ratio else "rerender_final"))
    except MediaError as e:
        checks.append(Check("black_frames", "warn", f"Análise de vídeo falhou: {e}"))
    if subtitles_expected:
        ok = bool(subtitles_path and subtitles_path.exists() and "Dialogue:" in subtitles_path.read_text(encoding="utf-8"))
        checks.append(Check("subtitles", "ok" if ok else "fail", "Legendas geradas e incorporadas" if ok else "Legendas ausentes", None if ok else "rerender_final"))
    return checks


def summarize(checks: list[Check]) -> dict[str, Any]:
    fails = [c for c in checks if c.status == "fail"]
    warns = [c for c in checks if c.status == "warn"]
    return {"passed": not fails, "fail_count": len(fails), "warn_count": len(warns), "checks": [asdict(c) for c in checks]}
