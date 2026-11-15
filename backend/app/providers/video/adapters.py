"""Geração de vídeo por IA via Replicate (modelos configuráveis: Kling, MiniMax/Hailuo, Wan, etc.)."""
from __future__ import annotations

import base64

from app.providers.base import Usage, VideoProvider, VideoResult
from app.providers.replicate import run_prediction


class ReplicateVideo(VideoProvider):
    adapter = "replicate_video"
    required_credentials = ("api_token",)
    default_model = "minimax/video-01"

    def generate(self, *, prompt, duration_s, image=None, aspect_ratio="9:16", model=None):
        self.require_credentials()
        m = self.model(model)
        # Mapeamento de campos por modelo é configurável em config.input_map
        imap = {"prompt": "prompt", "image": "first_frame_image", "duration": None, "aspect_ratio": None}
        imap.update((self.config.get("input_map") or {}).get(m, {}))
        inp: dict = {imap["prompt"]: prompt}
        if image is not None and imap.get("image"):
            inp[imap["image"]] = "data:image/png;base64," + base64.b64encode(image).decode()
        if imap.get("duration"):
            inp[imap["duration"]] = int(round(duration_s))
        if imap.get("aspect_ratio"):
            inp[imap["aspect_ratio"]] = aspect_ratio
        data, _ = run_prediction(self.credentials["api_token"], m, inp, timeout_s=1500)
        return VideoResult(data=data, mime="video/mp4", model=m, duration_s=duration_s,
                           usage=Usage(units={"seconds": duration_s},
                                       cost_usd=self.price(m, "per_video", 0.5) + self.price(m, "per_second") * duration_s))
