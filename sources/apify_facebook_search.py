"""Busqueda de posts por PALABRA CLAVE en todo Facebook (grupos y perfiles publicos) via Apify (scrapeforge/facebook-search-posts).
Es la fuente mas directa para encontrar gente que dice "busco programador" / "necesito un sistema".
Costo: ~$0.0026 por resultado. Plan Free de Apify: maximo 5 resultados por run (por query)."""
from __future__ import annotations

import logging

from config import settings
from sources.apify_base import ApifySource
from sources.base import Post, parse_dt

log = logging.getLogger("source.fbsearch")


class FacebookSearchSource(ApifySource):
    name = "fbsearch"
    actor_id = "scrapeforge/facebook-search-posts"

    def __init__(self):
        self.interval_minutes = settings.fbsearch_interval_minutes

    def fetch(self) -> list[Post]:
        posts: dict[str, Post] = {}
        n = max(1, min(50, settings.fbsearch_results_per_query))
        for query in settings.fbsearch_queries:
            run_input = {"query": query, "search_type": "posts", "max_results": n, "recent_posts": settings.fbsearch_recent_first}
            try:
                items = self.run_actor(run_input, max_items=n, timeout_sec=240)
            except Exception as e:
                # presupuesto agotado u otro error: no seguimos gastando con las demas queries
                log.warning("FB search '%s' fallo: %s", query, e)
                raise
            for it in items:
                text = it.get("message") or it.get("text") or ""
                if not text.strip():
                    continue
                url = it.get("url") or ""
                pid = f"facebook:{it.get('post_id') or Post.stable_id('fbs', url, text[:80])}"
                if pid in posts:
                    continue
                author = it.get("author")
                if isinstance(author, dict):
                    author = author.get("name") or author.get("username") or ""
                group = it.get("associated_group")
                if isinstance(group, dict):
                    group = group.get("name")
                posts[pid] = Post(
                    id=pid, source="facebook", text=text, url=url, author=str(author or ""),
                    posted_at=parse_dt(it.get("timestamp")),
                    extra={"group": group, "query": query, "reactions": it.get("reactions_count"), "comments": it.get("comments_count")},
                )
        log.info("FB search: %d posts de %d queries", len(posts), len(settings.fbsearch_queries))
        return list(posts.values())
