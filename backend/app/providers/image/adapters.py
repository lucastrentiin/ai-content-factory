"""Geração de imagens: OpenAI Images, Stability AI e Replicate (FLUX e outros)."""
from __future__ import annotations

import base64

from app.core.errors import ProviderError
from app.providers.base import ImageProvider, ImageResult, Usage
from app.providers.http import request_with_retry
from app.providers.replicate import run_prediction


def _aspect(width: int, height: int) -> str:
    r = width / height
    options = {"9:16": 9 / 16, "2:3": 2 / 3, "1:1": 1.0, "3:2": 1.5, "16:9": 16 / 9}
    return min(options, key=lambda k: abs(options[k] - r))


class OpenAIImage(ImageProvider):
    adapter = "openai_image"
    required_credentials = ("api_key",)
    default_model = "gpt-image-1"

    def generate(self, *, prompt, width, height, seed=None, negative_prompt=None, reference_images=None, model=None):
        self.require_credentials()
        m = self.model(model)
        size = "1024x1536" if height > width else ("1536x1024" if width > height else "1024x1024")
        base = self.config.get("base_url", "https://api.openai.com/v1").rstrip("/")
        body = {"model": m, "prompt": prompt, "size": size, "n": 1}
        if self.config.get("quality"):
            body["quality"] = self.config["quality"]
        resp = request_with_retry("POST", f"{base}/images/generations", json=body, timeout=180,
                                  headers={"Authorization": f"Bearer {self.credentials['api_key']}"})
        item = resp.json()["data"][0]
        if item.get("b64_json"):
            data = base64.b64decode(item["b64_json"])
        else:
            data = request_with_retry("GET", item["url"], timeout=120).content
        return ImageResult(data=data, mime="image/png", model=m, usage=Usage(units={"images": 1}, cost_usd=self.price(m, "per_image", 0.06)))


class StabilityImage(ImageProvider):
    adapter = "stability"
    required_credentials = ("api_key",)
    default_model = "stable-image-core"

    def generate(self, *, prompt, width, height, seed=None, negative_prompt=None, reference_images=None, model=None):
        self.require_credentials()
        m = self.model(model)
        endpoint = {"stable-image-core": "core", "stable-image-ultra": "ultra", "sd3.5-large": "sd3"}.get(m, "core")
        form = {"prompt": prompt, "aspect_ratio": _aspect(width, height), "output_format": "png"}
        if seed is not None:
            form["seed"] = str(seed % 4294967294)
        if negative_prompt:
            form["negative_prompt"] = negative_prompt
        if endpoint == "sd3":
            form["model"] = m
        resp = request_with_retry(
            "POST", f"https://api.stability.ai/v2beta/stable-image/generate/{endpoint}",
            headers={"Authorization": f"Bearer {self.credentials['api_key']}", "Accept": "image/*"},
            files={"none": ("", b"")}, data=form, timeout=180,
        )
        if not resp.headers.get("content-type", "").startswith("image/"):
            raise ProviderError(f"Stability: resposta inesperada {resp.text[:200]}", retryable=False)
        return ImageResult(data=resp.content, mime="image/png", model=m, seed=seed,
                           usage=Usage(units={"images": 1}, cost_usd=self.price(m, "per_image", 0.03)))


class ReplicateImage(ImageProvider):
    adapter = "replicate_image"
    required_credentials = ("api_token",)
    default_model = "black-forest-labs/flux-schnell"

    def generate(self, *, prompt, width, height, seed=None, negative_prompt=None, reference_images=None, model=None):
        self.require_credentials()
        m = self.model(model)
        inp = {"prompt": prompt, "aspect_ratio": _aspect(width, height), "output_format": "png", "num_outputs": 1}
        if seed is not None:
            inp["seed"] = seed
        inp.update(self.config.get("extra_input", {}))
        data, _ = run_prediction(self.credentials["api_token"], m, inp)
        return ImageResult(data=data, mime="image/png", model=m, seed=seed,
                           usage=Usage(units={"images": 1}, cost_usd=self.price(m, "per_image", 0.003)))
