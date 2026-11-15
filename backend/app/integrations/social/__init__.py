from app.integrations.social.base import SocialPlatform
from app.integrations.social.instagram import Instagram
from app.integrations.social.tiktok import TikTok
from app.integrations.social.youtube import YouTube

PLATFORMS: dict[str, SocialPlatform] = {p.key: p for p in (YouTube(), TikTok(), Instagram())}


def get_platform(key: str) -> SocialPlatform:
    if key not in PLATFORMS:
        raise KeyError(f"Plataforma não suportada: {key}")
    return PLATFORMS[key]
