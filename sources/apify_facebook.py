"""Facebook grupos PUBLICOS via Apify (apify/facebook-groups-scraper). Sin credenciales personales = sin riesgo de baneo."""
from __future__ import annotations

import logging

from config import settings
from sources.apify_base import ApifySource
from sources.base import Post, parse_dt

log = logging.getLogger("source.facebook")


class FacebookGroupsSource(ApifySource):
    name = "facebook"
    actor_id = "apify/facebook-groups-scraper"

    def __init__(self):
        self.interval_minutes = settings.facebook_interval_minutes

    def fetch(self) -> list[Post]:
        if not settings.facebook_groups:
            return []
        run_input = {
            "startUrls": [{"url": g} for g in settings.facebook_groups],
            "resultsLimit": settings.facebook_posts_per_group,
            "viewOption": "CHRONOLOGICAL",
            "onlyPostsNewerThan": settings.facebook_newer_than,
        }
        items = self.run_actor(run_input, max_items=settings.facebook_posts_per_group * len(settings.facebook_groups))
        posts = []
        for it in items:
            text = it.get("text") or (it.get("sharedPost") or {}).get("text") or ""
            if not text.strip():
                continue
            url = it.get("url") or it.get("topLevelUrl") or it.get("facebookUrl", "")
            pid = f"facebook:{it.get('id') or it.get('legacyId') or Post.stable_id('fb', url, text[:80])}"
            user = it.get("user") or {}
            posts.append(Post(
                id=pid, source=self.name, text=text, url=url, author=user.get("name", ""),
                posted_at=parse_dt(it.get("time")),
                extra={"group": it.get("groupTitle"), "likes": it.get("likesCount"), "comments": it.get("commentsCount")},
            ))
        return posts
