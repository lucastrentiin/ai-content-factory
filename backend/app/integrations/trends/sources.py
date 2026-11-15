"""Coletores de tendências. Cada coletor retorna itens normalizados; falhas são reportadas por fonte.

Fontes sem API oficial pública (TikTok Creative Center, tendências do Instagram) NÃO são raspadas:
use a importação manual/CSV (fonte `manual_import`), respeitando os termos de uso dessas plataformas.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any

from app.core.config import settings
from app.core.errors import MissingCredentials, ProviderError
from app.providers.http import request_with_retry

UA = {"User-Agent": "Mozilla/5.0 (compatible; ContentFactoryTrendBot/1.0)"}


@dataclass
class TrendItem:
    name: str
    description: str = ""
    url: str | None = None
    category: str | None = None
    popularity: float = 0.0
    rank: int | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    published_at: str | None = None


def _traffic(v: str | None) -> float:
    if not v:
        return 0.0
    m = re.match(r"([\d.,]+)\s*([KkMm]?)", v.replace("+", "").strip())
    if not m:
        return 0.0
    n = float(m.group(1).replace(",", "").replace(".", "")) if m.group(2) == "" else float(m.group(1).replace(",", "."))
    return n * {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1)


def parse_google_trends_rss(xml: str) -> list[TrendItem]:
    root = ET.fromstring(xml)
    ns = {"ht": "https://trends.google.com/trending/rss"}
    items = []
    for i, it in enumerate(root.iter("item")):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        news = [{"title": n.findtext("ht:news_item_title", namespaces=ns), "url": n.findtext("ht:news_item_url", namespaces=ns),
                 "source": n.findtext("ht:news_item_source", namespaces=ns)} for n in it.findall("ht:news_item", ns)]
        traffic = it.findtext("ht:approx_traffic", namespaces=ns)
        items.append(TrendItem(name=title, description="; ".join(n["title"] or "" for n in news[:2]),
                               url=news[0]["url"] if news else None, popularity=_traffic(traffic), rank=i + 1,
                               metrics={"approx_traffic": traffic, "news": news[:3]}, published_at=it.findtext("pubDate")))
    return items


def parse_news_rss(xml: str) -> list[TrendItem]:
    root = ET.fromstring(xml)
    out = []
    for i, it in enumerate(root.iter("item")):
        title = re.sub(r"\s+-\s+[^-]+$", "", (it.findtext("title") or "").strip())
        if title:
            out.append(TrendItem(name=title[:280], url=it.findtext("link"), rank=i + 1, popularity=max(0.0, 100 - i),
                                 category="notícias", metrics={"source": it.findtext("source")}, published_at=it.findtext("pubDate")))
    return out


def fetch(source_type: str, config: dict[str, Any]) -> list[TrendItem]:
    geo = config.get("geo", "BR")
    if source_type == "google_trends_rss":
        r = request_with_retry("GET", f"https://trends.google.com/trending/rss?geo={geo}", headers=UA, retries=2, timeout=30)
        return parse_google_trends_rss(r.text)
    if source_type == "google_news_rss":
        hl, ceid = config.get("hl", "pt-BR"), config.get("ceid", "BR:pt-419")
        topic = config.get("topic")
        url = (f"https://news.google.com/rss/headlines/section/topic/{topic}?hl={hl}&gl={geo}&ceid={ceid}" if topic
               else f"https://news.google.com/rss?hl={hl}&gl={geo}&ceid={ceid}")
        return parse_news_rss(request_with_retry("GET", url, headers=UA, retries=2, timeout=30).text)[: config.get("limit", 30)]
    if source_type == "youtube_most_popular":
        key = config.get("api_key") or settings.youtube_api_key
        if not key:
            raise MissingCredentials("YouTube Data API: defina YOUTUBE_API_KEY")
        params = f"part=snippet,statistics,contentDetails&chart=mostPopular&regionCode={geo}&maxResults=50&key={key}"
        if config.get("category_id"):
            params += f"&videoCategoryId={config['category_id']}"
        data = request_with_retry("GET", f"https://www.googleapis.com/youtube/v3/videos?{params}", retries=2).json()
        out = []
        for i, v in enumerate(data.get("items", [])):
            sn, st = v["snippet"], v.get("statistics", {})
            dur = v.get("contentDetails", {}).get("duration", "")
            views = int(st.get("viewCount", 0))
            out.append(TrendItem(name=sn["title"][:280], description=(sn.get("description") or "")[:300],
                                 url=f"https://www.youtube.com/watch?v={v['id']}", rank=i + 1, popularity=float(views),
                                 category=sn.get("categoryId"),
                                 metrics={"views": views, "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
                                          "tags": (sn.get("tags") or [])[:10], "channel": sn.get("channelTitle"), "duration": dur,
                                          "is_short": _iso_seconds(dur) <= 180},
                                 published_at=sn.get("publishedAt")))
        return out
    if source_type == "reddit":
        sub = config.get("subreddit", "brasil")
        data = request_with_retry("GET", f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={config.get('limit', 25)}",
                                  headers=UA, retries=1, timeout=30).json()
        return [TrendItem(name=p["data"]["title"][:280], url="https://www.reddit.com" + p["data"]["permalink"], rank=i + 1,
                          popularity=float(p["data"].get("score", 0)), category=f"r/{sub}",
                          metrics={"score": p["data"].get("score"), "comments": p["data"].get("num_comments")})
                for i, p in enumerate(data.get("data", {}).get("children", []))]
    if source_type in ("manual_import", "tiktok_creative_center", "instagram_trends"):
        return []  # alimentadas via importação manual (API /trends/import)
    raise ProviderError(f"Tipo de fonte desconhecido: {source_type}", retryable=False)


def _iso_seconds(d: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def published_dt(s: str | None):
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None


def popularity_norm(v: float) -> float:
    """Normaliza popularidade de escalas diferentes para 0..1 (log)."""
    return max(0.0, min(1.0, math.log10(1 + max(0.0, v)) / 7))
