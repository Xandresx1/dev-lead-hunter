"""Reddit - JSON publico (puede estar bloqueado desde IPs cloud: en ese caso se omite sin romper nada).
Si algun dia consigues credenciales (REDDIT_CLIENT_ID/SECRET) usa OAuth automaticamente."""
from __future__ import annotations

import logging
import time

import httpx

from config import settings
from sources.base import Post, Source, parse_dt

log = logging.getLogger("source.reddit")
UA = "linux:dev-lead-hunter:1.0 (by /u/devleadhunter)"

QUERIES = [
    '"looking for a developer" OR "need a developer" OR "looking for someone to build" OR "need an app"',
    '"busco programador" OR "necesito un programador" OR "busco desarrollador" OR "necesito una app" OR "necesito un sistema"',
]


class RedditSource(Source):
    name = "reddit"

    def __init__(self):
        self.interval_minutes = settings.reddit_interval_minutes
        self._token: str | None = None
        self._token_exp = 0.0
        self._blocked_until = 0.0

    def _auth_headers(self, client: httpx.Client) -> dict:
        if not (settings.reddit_client_id and settings.reddit_client_secret):
            return {}
        if self._token and time.time() < self._token_exp:
            return {"Authorization": f"bearer {self._token}"}
        r = client.post("https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"},
                        auth=(settings.reddit_client_id, settings.reddit_client_secret))
        r.raise_for_status()
        d = r.json()
        self._token = d["access_token"]
        self._token_exp = time.time() + int(d.get("expires_in", 3600)) - 60
        return {"Authorization": f"bearer {self._token}"}

    def fetch(self) -> list[Post]:
        if time.time() < self._blocked_until:
            log.info("Reddit bloqueado temporalmente, omito.")
            return []
        posts: dict[str, Post] = {}
        with httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True) as client:
            auth = self._auth_headers(client)
            base = "https://oauth.reddit.com" if auth else "https://www.reddit.com"
            targets = [("search", q) for q in QUERIES] + [(f"r/{s}/new", None) for s in settings.reddit_subreddits]
            blocked = 0
            for path, q in targets:
                params = {"limit": 25, "sort": "new", "t": "day"}
                if q:
                    params["q"] = q
                url = f"{base}/{path}.json" if not auth else f"{base}/{path}"
                try:
                    r = client.get(url, params=params, headers=auth)
                    if r.status_code in (403, 429):
                        blocked += 1
                        if blocked >= 2:
                            log.warning("Reddit responde %s (IP bloqueada o rate limit). Pauso Reddit 6h.", r.status_code)
                            self._blocked_until = time.time() + 6 * 3600
                            break
                        continue
                    r.raise_for_status()
                    children = r.json().get("data", {}).get("children", [])
                except Exception as e:
                    log.warning("Reddit %s fallo: %s", path, e)
                    continue
                for c in children:
                    d = c.get("data", {})
                    if not d.get("id"):
                        continue
                    pid = f"reddit:{d['id']}"
                    if pid in posts:
                        continue
                    posts[pid] = Post(
                        id=pid, source=self.name, title=d.get("title", ""), text=d.get("selftext", "") or "",
                        url="https://www.reddit.com" + d.get("permalink", ""), author="u/" + str(d.get("author", "")),
                        posted_at=parse_dt(d.get("created_utc")), extra={"subreddit": d.get("subreddit")},
                    )
                time.sleep(1.2)
        log.info("Reddit: %d posts", len(posts))
        return list(posts.values())
