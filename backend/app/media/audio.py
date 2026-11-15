"""Processamento de áudio: normalização para WAV mono, remoção de silêncio, montagem de trilhas por cena,
envelope de amplitude (lip-sync), efeitos sonoros procedurais e mixagem final com ducking + loudnorm."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from app.media.ffmpeg import run_ffmpeg

SR = 44100


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError("WAV deve ser 16-bit")
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        idx = np.linspace(0, len(a) - 1, int(len(a) * SR / sr))
        a = np.interp(idx, np.arange(len(a)), a).astype(np.float32)
    return a


def write_wav(path: Path, a: np.ndarray, channels: int = 1) -> Path:
    a = np.clip(a, -1, 1)
    pcm = (a * 32767).astype(np.int16)
    if channels == 2:
        pcm = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def normalize_to_wav(src: Path, dest: Path) -> Path:
    run_ffmpeg(["-i", str(src), "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(dest)])
    return dest


def trim_silence(a: np.ndarray, threshold: float = 0.012, pad_s: float = 0.05) -> np.ndarray:
    if len(a) == 0:
        return a
    win = int(SR * 0.01)
    env = np.sqrt(np.convolve(a ** 2, np.ones(win) / win, mode="same"))
    idx = np.where(env > threshold)[0]
    if len(idx) == 0:
        return a
    pad = int(SR * pad_s)
    return a[max(0, idx[0] - pad): min(len(a), idx[-1] + pad)]


def peak_normalize(a: np.ndarray, peak: float = 0.89) -> np.ndarray:
    m = float(np.max(np.abs(a))) if len(a) else 0
    return a * (peak / m) if m > 1e-4 else a


def envelope(a: np.ndarray, fps: int, total_frames: int, offset_s: float = 0.0) -> np.ndarray:
    """Amplitude normalizada por quadro de vídeo (para abrir/fechar a boca)."""
    out = np.zeros(total_frames, dtype=np.float32)
    spf = SR / fps
    for f in range(total_frames):
        s = int((f / fps - offset_s) * SR)
        if s < 0 or s >= len(a):
            continue
        seg = a[s: s + int(spf)]
        out[f] = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0
    m = out.max()
    if m > 0:
        out = np.clip(out / (m * 0.7), 0, 1)
        out[out < 0.15] = 0
    return out


def place(track: np.ndarray, clip: np.ndarray, start_s: float, gain: float = 1.0) -> np.ndarray:
    s = int(start_s * SR)
    end = s + len(clip)
    if end > len(track):
        track = np.concatenate([track, np.zeros(end - len(track), dtype=np.float32)])
    track[s:end] += clip * gain
    return track


# ---------------------------------------------------------------- efeitos sonoros procedurais (licença: gerados internamente)
def sfx(name: str, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if name == "whoosh":
        n = int(SR * 0.6)
        noise = rng.standard_normal(n).astype(np.float32)
        t = np.linspace(0, 1, n)
        env = np.sin(np.pi * t) ** 2
        k = np.ones(40) / 40
        return np.convolve(noise, k, "same") * env * 0.6
    if name == "boom":
        n = int(SR * 1.2)
        t = np.arange(n) / SR
        return (np.sin(2 * np.pi * (60 * np.exp(-t * 3) + 30) * t) * np.exp(-t * 3.5) * 0.9).astype(np.float32)
    if name == "knock":
        out = np.zeros(int(SR * 1.3), dtype=np.float32)
        for i in range(3):
            n = int(SR * 0.08)
            t = np.arange(n) / SR
            hit = (np.sin(2 * np.pi * 180 * t) + 0.5 * rng.standard_normal(n)) * np.exp(-t * 60)
            out = place(out, hit.astype(np.float32), 0.05 + i * 0.38, 0.8)
        return out
    if name == "crash":
        n = int(SR * 0.9)
        t = np.arange(n) / SR
        return (rng.standard_normal(n) * np.exp(-t * 5) * 0.5).astype(np.float32)
    if name == "boing":
        n = int(SR * 0.5)
        t = np.arange(n) / SR
        return (np.sin(2 * np.pi * (300 + 200 * np.sin(t * 40)) * t) * np.exp(-t * 5) * 0.5).astype(np.float32)
    if name in ("ding", "pop"):
        n = int(SR * (0.6 if name == "ding" else 0.12))
        t = np.arange(n) / SR
        f = 1320 if name == "ding" else 520
        return (np.sin(2 * np.pi * f * t) * np.exp(-t * (6 if name == "ding" else 40)) * 0.5).astype(np.float32)
    return np.zeros(1, dtype=np.float32)


SFX_NAMES = ("whoosh", "boom", "knock", "crash", "boing", "ding", "pop")


def mix_final(video: Path, voice: Path, music: Path | None, effects: Path | None, out: Path, *, subtitles: Path | None,
              music_volume: float = 0.18, ducking: bool = True, loudness_lufs: float = -14.0, fps: int = 30,
              crf: int = 20) -> Path:
    """Combina vídeo, voz, música (com ducking), efeitos; normaliza loudness; queima legendas ASS."""
    inputs = ["-i", str(video), "-i", str(voice)]
    idx = 2
    filters = ["[1:a]aformat=sample_rates=44100:channel_layouts=stereo[voice]"]
    mix_inputs = ["[voice]"]
    if music:
        inputs += ["-i", str(music)]
        filters.append(f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={music_volume}[mus]")
        if ducking:
            filters[0] = "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[voice][vkey]"
            filters.append("[mus][vkey]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350[musd]")
            mix_inputs.append("[musd]")
        else:
            mix_inputs.append("[mus]")
        idx += 1
    if effects:
        inputs += ["-i", str(effects)]
        filters.append(f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[fx]")
        mix_inputs.append("[fx]")
        idx += 1
    filters.append("".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:normalize=0:duration=first,"
                   f"loudnorm=I={loudness_lufs}:TP=-1.5:LRA=11,aresample=44100[aout]")
    vf = "[0:v]null[vout]"
    if subtitles:
        sub = str(subtitles).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf = f"[0:v]ass='{sub}'[vout]"
    filters.append(vf)
    run_ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", str(fps),
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out)])
    return out
