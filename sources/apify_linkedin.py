"""LinkedIn posts por keyword via Apify (datadoping/linkedin-posts-search-scraper)."""
from __future__ import annotations

import logging

from config import settings
from sources.apify_base import ApifySource
from sources.base import Post, parse_dt

log = logging.getLogger("source.linkedin")


class LinkedInSource(ApifySource):
    name = "linkedin"
    actor_id = "datadoping/linkedin-posts-search-scraper"

    def __init__(self):
        self.interval_minutes = settings.linkedin_interval_minutes

    def fetch(self) -> list[Post]:
        if not settings.linkedin_keywords:
            return []
        run_input = {
            "keywords": settings.linkedin_keywords,
            "max_posts": max(10, settings.linkedin_posts_per_keyword),  # el actor exige >= 10
            "sort_by": "date_posted",
            "date_filter": settings.linkedin_date_filter,
        }
        items = self.run_actor(run_input, max_items=max(10, settings.linkedin_posts_per_keyword) * len(settings.linkedin_keywords))
        posts = []
        for it in items:
            text = it.get("text") or ""
            if not text.strip():
                continue
            url = it.get("post_url") or it.get("url") or ""
            pid = f"linkedin:{it.get('activity_id') or Post.stable_id('li', url, text[:80])}"
            author = it.get("owner_name") or (it.get("author") or {}).get("name", "")
            posts.append(Post(
                id=pid, source=self.name, text=text, url=url, author=author,
                posted_at=parse_dt(it.get("timestamp") or it.get("posted_at")),
                extra={"reactions": it.get("total_reactions"), "comments": it.get("comments"),
                       "author_headline": (it.get("author") or {}).get("headline")},
            ))
        return posts
