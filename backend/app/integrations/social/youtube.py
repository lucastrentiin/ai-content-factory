"""YouTube (Shorts) via YouTube Data API v3 + YouTube Analytics API (OAuth 2.0).

Observação: projetos do Google Cloud não verificados/auditados só conseguem enviar vídeos como privados.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from app.core.config import settings
from app.core.errors import IntegrationNotAuthorized, ProviderError
from app.integrations.social.base import Metrics, PublishRequest, PublishResult, SocialPlatform, caption
from app.providers.http import request_with_retry

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]


class YouTube(SocialPlatform):
    key, name = "youtube", "YouTube Shorts"
    docs = "https://developers.google.com/youtube/v3/guides/uploading_a_video"

    def app_configured(self):
        ok = bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)
        return ok, "" if ok else "Defina GOOGLE_OAUTH_CLIENT_ID e GOOGLE_OAUTH_CLIENT_SECRET"

    def auth_url(self, state, redirect_uri):
        q = {"client_id": settings.google_oauth_client_id, "redirect_uri": redirect_uri, "response_type": "code",
             "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state, "include_granted_scopes": "true"}
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(q)

    def exchange_code(self, code, redirect_uri):
        tok = request_with_retry("POST", "https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": settings.google_oauth_client_id, "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, retries=1).json()
        ch = request_with_retry("GET", "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                                headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
        item = (ch.get("items") or [{}])[0]
        return {"creds": {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token")},
                "account": {"id": item.get("id"), "name": (item.get("snippet") or {}).get("title")},
                "expires_in": tok.get("expires_in"), "scopes": tok.get("scope", "").split()}

    def refresh(self, creds):
        if not creds.get("refresh_token"):
            raise IntegrationNotAuthorized("YouTube: sem refresh_token; reconecte a conta")
        tok = request_with_retry("POST", "https://oauth2.googleapis.com/token", data={
            "client_id": settings.google_oauth_client_id, "client_secret": settings.google_oauth_client_secret,
            "refresh_token": creds["refresh_token"], "grant_type": "refresh_token"}, retries=2).json()
        return {"creds": {**creds, "access_token": tok["access_token"]}, "expires_in": tok.get("expires_in")}

    def publish(self, creds, config, req: PublishRequest):
        token = self.require(creds)
        tags = [h.lstrip("#") for h in req.hashtags]
        title = req.title if "#shorts" in req.title.lower() else req.title[:90]
        body = {"snippet": {"title": title[:100], "description": caption(req.description, req.hashtags, 4900), "tags": tags[:15],
                            "categoryId": str(config.get("category_id", "24")), "defaultLanguage": config.get("language", "pt-BR")},
                "status": {"privacyStatus": req.privacy if req.privacy in ("public", "private", "unlisted") else "private",
                           "selfDeclaredMadeForKids": bool(config.get("made_for_kids", False)),
                           "containsSyntheticMedia": req.ai_generated}}
        size = req.video_path.stat().st_size
        init = request_with_retry(
            "POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, json=body, retries=2)
        upload_url = init.headers.get("Location")
        if not upload_url:
            raise ProviderError("YouTube: URL de upload não retornada", retryable=True)
        with req.video_path.open("rb") as f:
            resp = request_with_retry("PUT", upload_url, content=f.read(), timeout=1800, retries=2,
                                      headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"})
        data = resp.json()
        vid = data["id"]
        if req.cover_path and config.get("upload_thumbnail", True):
            try:
                request_with_retry("POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
                                   headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
                                   content=req.cover_path.read_bytes(), retries=1)
            except ProviderError:
                pass  # miniaturas personalizadas exigem conta verificada
        return PublishResult(status="published", external_id=vid, url=f"https://www.youtube.com/shorts/{vid}",
                             raw={"privacy": data.get("status", {}).get("privacyStatus"), "upload_status": data.get("status", {}).get("uploadStatus")})

    def fetch_metrics(self, creds, config, external_id):
        token = self.require(creds)
        h = {"Authorization": f"Bearer {token}"}
        st = request_with_retry("GET", f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={external_id}", headers=h).json()
        s = ((st.get("items") or [{}])[0]).get("statistics", {})
        m = Metrics(views=int(s.get("viewCount", 0)), likes=int(s.get("likeCount", 0)), comments=int(s.get("commentCount", 0)), raw={"statistics": s})
        try:
            end = datetime.now(UTC).date()
            start = end - timedelta(days=365)
            q = urlencode({"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(),
                           "metrics": "views,averageViewDuration,averageViewPercentage,shares,subscribersGained",
                           "filters": f"video=={external_id}"})
            rep = request_with_retry("GET", f"https://youtubeanalytics.googleapis.com/v2/reports?{q}", headers=h, retries=1).json()
            row = (rep.get("rows") or [[None] * 5])[0]
            if row and row[0] is not None:
                m.avg_watch_time_s = float(row[1])
                m.completion_rate = float(row[2]) / 100.0
                m.shares = int(row[3])
                m.followers_gained = int(row[4])
                m.raw["analytics"] = rep
        except ProviderError as e:
            m.raw["analytics_error"] = e.message[:300]
        return m
