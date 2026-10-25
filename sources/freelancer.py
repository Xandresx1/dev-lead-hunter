"""Freelancer.com - API publica (sin key). Todo lo que publica un cliente es un pedido de trabajo."""
from __future__ import annotations

import logging

import httpx

from config import settings
from sources.base import Post, Source, parse_dt

log = logging.getLogger("source.freelancer")
API = "https://www.freelancer.com/api/projects/0.1/projects/active/"
UA = "Mozilla/5.0 (X11; Linux x86_64) dev-lead-hunter/1.0"


class FreelancerSource(Source):
    name = "freelancer"
    is_request_source = True

    def __init__(self):
        self.interval_minutes = settings.freelancer_interval_minutes

    def fetch(self) -> list[Post]:
        posts: dict[str, Post] = {}
        plan = [(q, "es") for q in settings.freelancer_queries_es] + [(q, None) for q in settings.freelancer_queries_en]
        with httpx.Client(headers={"User-Agent": UA}, timeout=25) as client:
            for query, lang in plan:
                params = {
                    "query": query,
                    "limit": settings.freelancer_limit_per_query,
                    "compact": "true",
                    "full_description": "true",
                    "sort_field": "time_updated",
                    "job_details": "true",
                }
                if lang:
                    params["languages[]"] = lang
                try:
                    r = client.get(API, params=params)
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:
                    log.warning("Freelancer query '%s' fallo: %s", query, e)
                    continue
                for p in data.get("result", {}).get("projects", []):
                    pid = f"freelancer:{p['id']}"
                    if pid in posts:
                        continue
                    budget = p.get("budget") or {}
                    cur = (p.get("currency") or {}).get("code", "")
                    if cur.upper() in settings.excluded_currencies:
                        log.info("Freelancer: omito proyecto %s por moneda excluida (%s)", p.get("id"), cur)
                        continue
                    budget_txt = ""
                    if budget.get("minimum") is not None:
                        budget_txt = f"Presupuesto: {budget.get('minimum')}-{budget.get('maximum')} {cur}"
                    skills = ", ".join(j.get("name", "") for j in (p.get("jobs") or [])[:6])
                    desc = p.get("description") or p.get("preview_description") or ""
                    text = desc
                    if budget_txt:
                        text += f"\n{budget_txt}"
                    if skills:
                        text += f"\nSkills: {skills}"
                    posts[pid] = Post(
                        id=pid,
                        source=self.name,
                        title=p.get("title", ""),
                        text=text,
                        url=f"https://www.freelancer.com/projects/{p.get('seo_url', p['id'])}",
                        author=str((p.get("owner_id") or "")),
                        posted_at=parse_dt(p.get("time_submitted")),
                        extra={
                            "bids": (p.get("bid_stats") or {}).get("bid_count"),
                            "bid_avg": (p.get("bid_stats") or {}).get("bid_avg"),
                            "budget": budget_txt,
                            "budget_min": budget.get("minimum"),
                            "budget_max": budget.get("maximum"),
                            "currency": cur,
                            "price_type": p.get("type"),  # fixed | hourly
                            "hourly_commitment": (lambda h: f"{h.get('hours')} h/{h.get('interval')}" if h and h.get("hours") else None)(
                                (p.get("hourly_project_info") or {}).get("commitment")),
                            "escrow": p.get("is_escrow_project"),
                            "country": ((p.get("location") or {}).get("country") or {}).get("name"),
                            "lang": p.get("language"),
                        },
                    )
        log.info("Freelancer: %d proyectos", len(posts))
        return list(posts.values())
