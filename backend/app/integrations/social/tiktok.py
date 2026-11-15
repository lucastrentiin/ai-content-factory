"""TikTok via Content Posting API (Direct Post) + Display API (métricas).

Apps não auditados pelo TikTok só podem publicar com privacidade SELF_ONLY (somente o autor vê).
Configure `app_audited: true` na conta social somente após a auditoria aprovada.
"""
from __future__ import annotations

import time
from urllib.parse import urlencode

from app.core.config import settings
from app.core.errors import ProviderError
from app.integrations.social.base import Metrics, PublishRequest, PublishResult, SocialPlatform
from app.providers.http import request_with_retry

API = "https://open.tiktokapis.com/v2"
SCOPES = "user.info.basic,video.publish,video.upload,video.list"


class TikTok(SocialPlatform):
    key, name = "tiktok", "TikTok"
    docs = "https://developers.tiktok.com/doc/content-posting-api-get-started"

    def app_configured(self):
        ok = bool(settings.tiktok_client_key and settings.tiktok_client_secret)
        return ok, "" if ok else "Defina TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET"

    def auth_url(self, state, redirect_uri):
        return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
            "client_key": settings.tiktok_client_key, "scope": SCOPES, "response_type": "code", "redirect_uri": redirect_uri, "state": state})

    def _token(self, data: dict) -> dict:
        return request_with_retry("POST", f"{API}/oauth/token/", data={"client_key": settings.tiktok_client_key,
                                  "client_secret": settings.tiktok_client_secret, **data},
                                  headers={"Content-Type": "application/x-www-form-urlencoded"}, retries=1).json()

    def exchange_code(self, code, redirect_uri):
        tok = self._token({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri})
        if "access_token" not in tok:
            raise ProviderError(f"TikTok OAuth: {tok}", retryable=False)
        info = request_with_retry("GET", f"{API}/user/info/?fields=open_id,display_name",
                                  headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
        user = (info.get("data") or {}).get("user", {})
        return {"creds": {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"), "open_id": tok.get("open_id")},
                "account": {"id": tok.get("open_id"), "name": user.get("display_name")}, "expires_in": tok.get("expires_in"),
                "scopes": (tok.get("scope") or "").split(",")}

    def refresh(self, creds):
        tok = self._token({"grant_type": "refresh_token", "refresh_token": creds.get("refresh_token", "")})
        if "access_token" not in tok:
            raise ProviderError(f"TikTok refresh: {tok}", retryable=False)
        return {"creds": {**creds, "access_token": tok["access_token"], "refresh_token": tok.get("refresh_token", creds.get("refresh_token"))},
                "expires_in": tok.get("expires_in")}

    def _h(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}

    def publish(self, creds, config, req: PublishRequest):
        token = self.require(creds)
        info = request_with_retry("POST", f"{API}/post/publish/creator_info/query/", headers=self._h(token), json={}).json()
        options = (info.get("data") or {}).get("privacy_level_options") or ["SELF_ONLY"]
        wanted = {"public": "PUBLIC_TO_EVERYONE", "private": "SELF_ONLY", "friends": "MUTUAL_FOLLOW_FRIENDS"}.get(req.privacy, "SELF_ONLY")
        if not config.get("app_audited"):
            wanted = "SELF_ONLY"
        privacy = wanted if wanted in options else "SELF_ONLY"
        size = req.video_path.stat().st_size
        title = (req.title + " " + " ".join(h if h.startswith("#") else f"#{h}" for h in req.hashtags))[:2200]
        init = request_with_retry("POST", f"{API}/post/publish/video/init/", headers=self._h(token), json={
            "post_info": {"title": title, "privacy_level": privacy, "disable_comment": False, "disable_duet": False,
                          "disable_stitch": False, "video_cover_timestamp_ms": int(config.get("cover_ms", 1000)), "is_aigc": req.ai_generated},
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}}).json()
        data = init.get("data") or {}
        if not data.get("upload_url"):
            raise ProviderError(f"TikTok init falhou: {init.get('error')}", retryable=False)
        with req.video_path.open("rb") as f:
            request_with_retry("PUT", data["upload_url"], content=f.read(), timeout=1800, retries=2,
                               headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{size - 1}/{size}"})
        return self.check_status(creds, config, data["publish_id"], wait_s=60, privacy=privacy)

    def check_status(self, creds, config, external_ref, wait_s: int = 0, privacy: str | None = None):
        token = self.require(creds)
        deadline = time.time() + wait_s
        while True:
            st = request_with_retry("POST", f"{API}/post/publish/status/fetch/", headers=self._h(token), json={"publish_id": external_ref}).json()
            d = st.get("data") or {}
            status = d.get("status")
            if status == "PUBLISH_COMPLETE":
                ids = d.get("publicaly_available_post_id") or d.get("publicly_available_post_id") or []
                vid = str(ids[0]) if ids else None
                url = f"https://www.tiktok.com/@{config.get('username', '')}/video/{vid}" if vid and config.get("username") else None
                return PublishResult(status="published", external_id=vid or external_ref, url=url, raw={"publish_id": external_ref, "privacy": privacy, **d})
            if status == "FAILED":
                return PublishResult(status="failed", external_id=external_ref, error=str(d.get("fail_reason")), raw=d)
            if time.time() >= deadline:
                return PublishResult(status="processing", external_id=external_ref, raw={"publish_id": external_ref, "privacy": privacy, **d})
            time.sleep(5)

    def fetch_metrics(self, creds, config, external_id):
        token = self.require(creds)
        r = request_with_retry("POST", f"{API}/video/query/?fields=id,view_count,like_count,comment_count,share_count",
                               headers=self._h(token), json={"filters": {"video_ids": [external_id]}}).json()
        v = ((r.get("data") or {}).get("videos") or [{}])[0]
        return Metrics(views=int(v.get("view_count", 0)), likes=int(v.get("like_count", 0)), comments=int(v.get("comment_count", 0)),
                       shares=int(v.get("share_count", 0)), raw=v)
