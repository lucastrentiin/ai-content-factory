"""Gerador procedural de trilhas (local). Música criada pela própria plataforma — sem problemas de direitos."""
from __future__ import annotations

import io
import random
import wave

import numpy as np

from app.providers.base import MusicProvider, MusicResult, ProviderStatus, Usage

SR = 44100
MOODS = {
    #           root(Hz)  bpm  progression (semitons sobre a tônica, acordes menores=m)
    "emotional": (220.0, 72, [(0, "M"), (9, "m"), (5, "M"), (7, "M")]),
    "suspense": (196.0, 64, [(0, "m"), (8, "M"), (3, "M"), (10, "M")]),
    "dark": (146.8, 56, [(0, "m"), (1, "M"), (0, "m"), (6, "dim")]),
    "playful": (261.6, 112, [(0, "M"), (5, "M"), (7, "M"), (0, "M")]),
    "curious": (233.1, 92, [(0, "M"), (4, "m"), (9, "m"), (5, "M")]),
    "upbeat": (246.9, 120, [(0, "M"), (7, "M"), (9, "m"), (5, "M")]),
    "neutral": (220.0, 90, [(0, "M"), (5, "M"), (9, "m"), (7, "M")]),
}
CHORD = {"M": [0, 4, 7], "m": [0, 3, 7], "dim": [0, 3, 6]}


def _env(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n)
    a, r = min(n // 2, int(SR * attack)), min(n // 2, int(SR * release))  # trechos curtos (último compasso)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def render_music(mood: str, duration_s: float, seed: int = 0) -> bytes:
    root, bpm, prog = MOODS.get(mood, MOODS["neutral"])
    rng = random.Random(seed)
    total = int(SR * (duration_s + 1))
    out = np.zeros(total)
    beat = 60.0 / bpm
    bar = beat * 4
    t_bar = np.arange(int(SR * bar)) / SR
    pos, i = 0, 0
    percussive = mood in ("playful", "upbeat", "curious")
    while pos < total:
        semis, q = prog[i % len(prog)]
        n = min(len(t_bar), total - pos)
        t = t_bar[:n]
        pad = np.zeros(n)
        for iv in CHORD[q]:
            f = root * 2 ** ((semis + iv) / 12)
            pad += 0.10 * np.sin(2 * np.pi * f * t) + 0.04 * np.sin(2 * np.pi * f * 2 * t + 0.3)
            pad += 0.03 * np.sin(2 * np.pi * (f / 2) * t)
        pad *= _env(n, 0.4, 0.4)
        out[pos:pos + n] += pad
        # arpejo
        step = beat / (2 if percussive else 1)
        notes = CHORD[q] + [12]
        for k in range(int(bar / step)):
            st = pos + int(k * step * SR)
            ln = int(step * SR * 0.9)
            if st + ln >= total:
                break
            f = root * 2 ** ((semis + rng.choice(notes) + 12) / 12)
            tt = np.arange(ln) / SR
            out[st:st + ln] += 0.05 * np.sin(2 * np.pi * f * tt) * np.exp(-tt * 5)
        if percussive:
            for k in range(4):
                st = pos + int(k * beat * SR)
                ln = int(0.15 * SR)
                if st + ln >= total:
                    break
                tt = np.arange(ln) / SR
                out[st:st + ln] += 0.25 * np.sin(2 * np.pi * (110 * np.exp(-tt * 25) + 45) * tt) * np.exp(-tt * 18)
        pos += n
        i += 1
    out = out[: int(SR * duration_s)]
    out *= _env(len(out), 1.0, 2.0)
    peak = np.max(np.abs(out)) or 1
    pcm = (out / peak * 0.6 * 32767).astype(np.int16)
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    return buf.getvalue()


class ProceduralMusic(MusicProvider):
    adapter = "procedural_music"
    default_model = "procedural-v1"

    def status(self) -> ProviderStatus:
        return ProviderStatus(True, "configured", "Trilha procedural local (royalty-free, gerada internamente)")

    def generate(self, *, mood, duration_s, bpm=None, seed=None, model=None):
        data = render_music(mood, duration_s, seed or 0)
        return MusicResult(data=data, mime="audio/wav", model="procedural-v1", usage=Usage(units={"seconds": duration_s}),
                           license="internal_generated")
