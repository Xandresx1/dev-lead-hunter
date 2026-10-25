"""X / Twitter busqueda via Apify (simoit/x-twitter-search-tweets-scrapper). Cuenta free: ~50 runs/mes."""
from __future__ import annotations

import logging

from config import settings
from sources.apify_base import ApifySource
from sources.base import Post, parse_dt

log = logging.getLogger("source.twitter")


class TwitterSource(ApifySource):
    name = "twitter"
    actor_id = "simoit/x-twitter-search-tweets-scrapper"

    def __init__(self):
        self.interval_minutes = settings.twitter_interval_minutes

    def fetch(self) -> list[Post]:
        n = max(10, min(100, settings.twitter_max_items))
        run_input = {
            "inputTargetType": "search",
            "rawQuery": settings.twitter_query,
            "sort": "latest",
            "limit": n,
            "maxPages": 1,
            "maxItems": n,
            "includeReplies": False,
            "includeRetweets": False,
        }
        items = self.run_actor(run_input, max_items=n)
        posts = []
        for it in items:
            text = it.get("rawContent") or it.get("text") or it.get("full_text") or ""
            if not text.strip():
                continue
            user = it.get("user") or {}
            pid = f"twitter:{it.get('id_str') or it.get('id') or Post.stable_id('tw', it.get('url',''))}"
            posts.append(Post(
                id=pid, source=self.name, text=text, url=it.get("url", ""),
                author=f"@{user.get('username')}" if user.get("username") else "",
                posted_at=parse_dt(it.get("date")),
                extra={"lang": it.get("lang"), "likes": it.get("likeCount"), "followers": user.get("followersCount")},
            ))
        return posts
