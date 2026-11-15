"""Text-to-Speech: ElevenLabs, OpenAI e eSpeak NG (local, sem custo)."""
from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.errors import ProviderError
from app.providers.base import ProviderStatus, TTSProvider, TTSResult, Usage
from app.providers.http import request_with_retry

EMOTION_STYLE = {  # ajuste fino de estilo por emoção (ElevenLabs style 0..1 / instrução OpenAI)
    "happy": (0.45, "fale com alegria e energia"),
    "sad": (0.35, "fale de forma triste e lenta"),
    "angry": (0.6, "fale com raiva contida"),
    "scared": (0.5, "fale com medo, em tom baixo e tenso"),
    "fear": (0.5, "fale com medo, em tom baixo e tenso"),
    "surprised": (0.5, "fale surpreso"),
    "dread": (0.4, "narre com suspense sombrio"),
    "neutral": (0.15, "narre de forma natural e envolvente"),
}


class ElevenLabsTTS(TTSProvider):
    adapter = "elevenlabs"
    required_credentials = ("api_key",)
    default_model = "eleven_multilingual_v2"

    def synthesize(self, *, text, voice_id, language="pt-BR", speed=1.0, pitch=0.0, emotion=None, settings=None, model=None):
        self.require_credentials()
        m = self.model(model)
        s = settings or {}
        style = EMOTION_STYLE.get(emotion or "neutral", EMOTION_STYLE["neutral"])[0]
        body = {
            "text": text,
            "model_id": m,
            "voice_settings": {
                "stability": float(s.get("stability", 0.5)),
                "similarity_boost": float(s.get("similarity_boost", 0.75)),
                "style": float(s.get("style", style)),
                "use_speaker_boost": True,
                "speed": max(0.7, min(1.2, float(speed))),
            },
        }
        resp = request_with_retry(
            "POST", f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128",
            headers={"xi-api-key": self.credentials["api_key"]}, json=body, timeout=180,
        )
        data = resp.json()
        audio = base64.b64decode(data["audio_base64"])
        timings = _words_from_alignment(data.get("alignment") or {})
        return TTSResult(data=audio, mime="audio/mpeg", model=m, word_timings=timings,
                         usage=Usage(units={"chars": len(text)}, cost_usd=len(text) / 1000 * self.price(m, "per_1k_chars", 0.2)))

    def list_voices(self):
        self.require_credentials()
        resp = request_with_retry("GET", "https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": self.credentials["api_key"]}, timeout=30)
        return [{"voice_id": v["voice_id"], "name": v["name"], "labels": v.get("labels", {}), "category": v.get("category")}
                for v in resp.json().get("voices", [])]


def _words_from_alignment(al: dict) -> list[dict]:
    chars, starts, ends = al.get("characters") or [], al.get("character_start_times_seconds") or [], al.get("character_end_times_seconds") or []
    words, cur, ws = [], "", None
    for ch, st, en in zip(chars, starts, ends, strict=False):
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": ws, "end": prev_end})
            cur, ws = "", None
        else:
            if not cur:
                ws = st
            cur += ch
        prev_end = en
    if cur:
        words.append({"word": cur, "start": ws, "end": prev_end})
    return words


class OpenAITTS(TTSProvider):
    adapter = "openai_tts"
    required_credentials = ("api_key",)
    default_model = "gpt-4o-mini-tts"

    def synthesize(self, *, text, voice_id, language="pt-BR", speed=1.0, pitch=0.0, emotion=None, settings=None, model=None):
        self.require_credentials()
        m = self.model(model)
        base = self.config.get("base_url", "https://api.openai.com/v1").rstrip("/")
        body = {"model": m, "voice": voice_id or "alloy", "input": text, "response_format": "wav", "speed": max(0.25, min(4.0, speed))}
        if m.startswith("gpt-4o"):
            body["instructions"] = f"Idioma {language}. " + EMOTION_STYLE.get(emotion or "neutral", EMOTION_STYLE["neutral"])[1]
        resp = request_with_retry("POST", f"{base}/audio/speech", json=body, timeout=180,
                                  headers={"Authorization": f"Bearer {self.credentials['api_key']}"})
        return TTSResult(data=resp.content, mime="audio/wav", model=m,
                         usage=Usage(units={"chars": len(text)}, cost_usd=len(text) / 1000 * self.price(m, "per_1k_chars", 0.015)))


class EspeakTTS(TTSProvider):
    """Síntese local (eSpeak NG, GPL — o áudio gerado pode ser usado livremente). Qualidade robótica."""

    adapter = "espeak"
    default_model = "espeak-ng"

    def status(self) -> ProviderStatus:
        if not shutil.which("espeak-ng"):
            return ProviderStatus(False, "unavailable", "espeak-ng não instalado (apt install espeak-ng)")
        return ProviderStatus(True, "configured", "Síntese local gratuita (qualidade básica)")

    def synthesize(self, *, text, voice_id, language="pt-BR", speed=1.0, pitch=0.0, emotion=None, settings=None, model=None):
        if not shutil.which("espeak-ng"):
            raise ProviderError("espeak-ng não instalado", retryable=False)
        voice = voice_id or "pt-br"
        emo_speed = {"scared": 1.08, "fear": 1.05, "sad": 0.9, "angry": 1.05, "happy": 1.05, "dread": 0.88}.get(emotion or "", 1.0)
        emo_pitch = {"happy": 8, "surprised": 12, "sad": -8, "dread": -10, "angry": -4}.get(emotion or "", 0)
        wpm = int(165 * speed * emo_speed)
        p = int(max(0, min(99, 50 + pitch * 4 + emo_pitch)))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.wav"
            proc = subprocess.run(["espeak-ng", "-v", voice, "-s", str(wpm), "-p", str(p), "-g", "2", "-w", str(out), text],
                                  capture_output=True, timeout=120)
            if proc.returncode != 0 or not out.exists():
                raise ProviderError(f"espeak-ng falhou: {proc.stderr.decode()[:200]}", retryable=False)
            data = out.read_bytes()
        return TTSResult(data=data, mime="audio/wav", model="espeak-ng", usage=Usage(units={"chars": len(text)}, cost_usd=0.0))

    def list_voices(self):
        return [{"voice_id": v, "name": n} for v, n in [
            ("pt-br", "Narrador BR (m)"), ("pt-br+m3", "Masculina grave"), ("pt-br+m7", "Masculina 2"),
            ("pt-br+f2", "Feminina 1"), ("pt-br+f4", "Feminina 2"), ("pt-br+f5", "Feminina 3"), ("pt-br+klatt", "Robótica")]]
