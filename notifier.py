"""Notificaciones push via ntfy (https://ntfy.sh)."""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from config import settings

log = logging.getLogger("notifier")

SOURCE_TAGS = {
    "facebook": "blue_book",
    "linkedin": "briefcase",
    "twitter": "bird",
    "freelancer": "money_with_wings",
    "reddit": "robot",
    "telegram": "airplane",
}


class Notifier:
    def __init__(self):
        self.enabled = bool(settings.ntfy_topic)
        self.url = f"{settings.ntfy_server}/{settings.ntfy_topic}"

    def _headers(self, title: str, priority: str, tags: str, click: str | None = None) -> dict:
        h = {"Title": title.encode("utf-8").decode("latin-1", "ignore") if not title.isascii() else title,
             "Priority": priority, "Tags": tags, "Markdown": "yes"}
        if click:
            h["Click"] = click
        if settings.ntfy_token:
            h["Authorization"] = f"Bearer {settings.ntfy_token}"
        return h

    def send(self, title: str, message: str, *, priority: str = "default", tags: str = "bell", click: str | None = None) -> bool:
        if not self.enabled:
            log.info("[ntfy desactivado] %s | %s", title, message[:120])
            return False
        try:
            # ntfy exige headers ASCII; para titulos con tildes/emoji usamos el formato JSON.
            payload = {"topic": settings.ntfy_topic, "title": title, "message": message, "priority": _prio_num(priority),
                       "tags": tags.split(","), "markdown": True}
            if click:
                payload["click"] = click
            headers = {"Authorization": f"Bearer {settings.ntfy_token}"} if settings.ntfy_token else {}
            r = httpx.post(settings.ntfy_server, json=payload, headers=headers, timeout=20)
            r.raise_for_status()
            return True
        except Exception as e:
            log.error("Fallo ntfy: %s", e)
            return False

    def send_lead(self, *, source: str, score: int, language: str, summary: str, opener: str, text: str, url: str,
                  author: str | None, ai: bool, posted_at: str | None) -> bool:
        if score >= 85:
            prio, flag = "urgent", "🔥"
        elif score >= 70:
            prio, flag = "high", "🎯"
        else:
            prio, flag = "default", "👀"
        title = f"{flag} Lead {score}/100 · {source.capitalize()} · {language.upper()}"
        excerpt = text.strip().replace("\n\n", "\n")
        if len(excerpt) > 500:
            excerpt = excerpt[:500] + "…"
        parts = [f"**{summary}**"]
        if author:
            parts.append(f"👤 {author}")
        if posted_at:
            parts.append(f"🕒 {posted_at}")
        parts.append(f"\n{excerpt}")
        if opener:
            parts.append(f"\n💬 **Sugerencia para abrir:**\n{opener}")
        parts.append(f"\n🔗 {url}")
        if not ai:
            parts.append("\n_(clasificado solo por keywords, sin IA)_")
        tags = SOURCE_TAGS.get(source, "bell")
        return self.send(title, "\n".join(parts), priority=prio, tags=tags, click=url)

    def send_error(self, source: str, error: str) -> bool:
        if not settings.notify_errors:
            return False
        return self.send(f"⚠️ Error en fuente {source}", error[:400], priority="low", tags="warning")

    def send_startup(self, sources: list[str]) -> bool:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return self.send("🤖 Dev Lead Hunter iniciado", f"Fuentes activas: {', '.join(sources) or 'ninguna'}\n{now}",
                         priority="low", tags="rocket")


def _prio_num(p: str) -> int:
    return {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}.get(p, 3)
