"""Instagram Reels via Instagram Graph API (conta Profissional vinculada a uma Página do Facebook).

A API exige que o vídeo esteja numa URL pública (video_url). Configure S3_PUBLIC_ENDPOINT_URL (MinIO exposto
via HTTPS) para gerar URLs assinadas acessíveis pela Meta. Sem isso, use publicação assistida.
"""
from __future__ import annotations

import time
from urllib.parse import urlencode

from app.core.config import settings
from app.core.errors import IntegrationNotAuthorized, ProviderError
from app.integrations.social.base import Metrics, PublishRequest, PublishResult, SocialPlatform, caption
from app.providers.http import request_with_retry

GRAPH = "https://graph.facebook.com/v21.0"
SCOPES = "instagram_basic,instagram_content_publish,instagram_manage_insights,pages_show_list,pages_read_engagement,business_management"


class Instagram(SocialPlatform):
    key, name = "instagram", "Instagram Reels"
    docs = "https://developers.facebook.com/docs/instagram-platform/content-publishing"

    def app_configured(self):
        ok = bool(settings.meta_app_id and settings.meta_app_secret)
        return ok, "" if ok else "Defina META_APP_ID e META_APP_SECRET"

    def auth_url(self, state, redirect_uri):
        return "https://www.facebook.com/v21.0/dialog/oauth?" + urlencode({
            "client_id": settings.meta_app_id, "redirect_uri": redirect_uri, "scope": SCOPES, "state": state, "response_type": "code"})

    def exchange_code(self, code, redirect_uri):
        short = request_with_retry("GET", f"{GRAPH}/oauth/access_token?" + urlencode({
            "client_id": settings.meta_app_id, "client_secret": settings.meta_app_secret, "redirect_uri": redirect_uri, "code": code})).json()
        long = request_with_retry("GET", f"{GRAPH}/oauth/access_token?" + urlencode({
            "grant_type": "fb_exchange_token", "client_id": settings.meta_app_id, "client_secret": settings.meta_app_secret,
            "fb_exchange_token": short["access_token"]})).json()
        token = long["access_token"]
        pages = request_with_retry("GET", f"{GRAPH}/me/accounts?fields=name,instagram_business_account{{id,username}}&access_token={token}").json()
        ig = next((p["instagram_business_account"] for p in pages.get("data", []) if p.get("instagram_business_account")), None)
        if not ig:
            raise IntegrationNotAuthorized("Nenhuma conta Instagram Profissional vinculada às Páginas autorizadas")
        return {"creds": {"access_token": token, "ig_user_id": ig["id"]}, "account": {"id": ig["id"], "name": ig.get("username")},
                "expires_in": long.get("expires_in", 60 * 24 * 3600), "scopes": SCOPES.split(",")}

    def refresh(self, creds):
        long = request_with_retry("GET", f"{GRAPH}/oauth/access_token?" + urlencode({
            "grant_type": "fb_exchange_token", "client_id": settings.meta_app_id, "client_secret": settings.meta_app_secret,
            "fb_exchange_token": creds["access_token"]})).json()
        return {"creds": {**creds, "access_token": long["access_token"]}, "expires_in": long.get("expires_in")}

    def publish(self, creds, config, req: PublishRequest):
        token = self.require(creds)
        ig = creds.get("ig_user_id")
        if not req.public_video_url:
            raise IntegrationNotAuthorized("Instagram exige URL pública do vídeo (configure S3_PUBLIC_ENDPOINT_URL) — use publicação assistida")
        params = {"media_type": "REELS", "video_url": req.public_video_url, "caption": caption(req.description or req.title, req.hashtags, 2200),
                  "share_to_feed": "true", "access_token": token}
        if req.public_cover_url:
            params["cover_url"] = req.public_cover_url
        cont = request_with_retry("POST", f"{GRAPH}/{ig}/media", data=params).json()
        cid = cont.get("id")
        if not cid:
            raise ProviderError(f"Instagram: falha ao criar container {cont}", retryable=False)
        deadline = time.time() + 600
        while True:
            st = request_with_retry("GET", f"{GRAPH}/{cid}?fields=status_code,status&access_token={token}").json()
            if st.get("status_code") == "FINISHED":
                break
            if st.get("status_code") in ("ERROR", "EXPIRED"):
                return PublishResult(status="failed", external_id=cid, error=str(st), raw=st)
            if time.time() > deadline:
                return PublishResult(status="processing", external_id=cid, raw={"container_id": cid, **st})
            time.sleep(8)
        return self._publish_container(token, ig, cid)

    def _publish_container(self, token: str, ig: str, cid: str) -> PublishResult:
        pub = request_with_retry("POST", f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": token}).json()
        mid = pub.get("id")
        link = request_with_retry("GET", f"{GRAPH}/{mid}?fields=permalink&access_token={token}").json().get("permalink")
        return PublishResult(status="published", external_id=mid, url=link, raw={"container_id": cid})

    def check_status(self, creds, config, external_ref):
        token = self.require(creds)
        st = request_with_retry("GET", f"{GRAPH}/{external_ref}?fields=status_code,status&access_token={token}").json()
        if st.get("status_code") == "FINISHED":
            return self._publish_container(token, creds["ig_user_id"], external_ref)
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            return PublishResult(status="failed", external_id=external_ref, error=str(st))
        return PublishResult(status="processing", external_id=external_ref, raw=st)

    def fetch_metrics(self, creds, config, external_id):
        token = self.require(creds)
        metrics = config.get("insight_metrics", "views,likes,comments,shares,saved,reach,ig_reels_avg_watch_time")
        r = request_with_retry("GET", f"{GRAPH}/{external_id}/insights?metric={metrics}&access_token={token}").json()
        vals = {d["name"]: (d.get("values") or [{}])[0].get("value", 0) for d in r.get("data", [])}
        avg = vals.get("ig_reels_avg_watch_time")
        return Metrics(views=int(vals.get("views", 0) or 0), likes=int(vals.get("likes", 0) or 0), comments=int(vals.get("comments", 0) or 0),
                       shares=int(vals.get("shares", 0) or 0), saves=int(vals.get("saved", 0) or 0),
                       avg_watch_time_s=float(avg) / 1000 if avg else None, raw=vals)
