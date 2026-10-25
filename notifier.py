"""Notificaciones push via ntfy (https://ntfy.sh)."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import quote

import httpx

from config import settings

log = logging.getLogger("notifier")

# Circulo de color por fuente en el titulo (ntfy no soporta colores reales; la pagina si).
SOURCE_DOT = {"freelancer": "\U0001F535", "facebook": "\U0001F7E2", "linkedin": "\U0001F7E3", "twitter": "\u26AB",
              "reddit": "\U0001F7E0", "telegram": "\U0001F537"}

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

    def send(self, title: str, message: str, *, priority: str = "default", tags: str = "bell", click: str | None = None,
             actions: list[dict] | None = None) -> bool:
        if not self.enabled:
            log.info("[ntfy desactivado] %s | %s", title, message[:120])
            return False
        try:
            # ntfy exige headers ASCII; para titulos con tildes/emoji usamos el formato JSON.
            payload = {"topic": settings.ntfy_topic, "title": title, "message": message, "priority": _prio_num(priority),
                       "tags": tags.split(","), "markdown": True}
            if click:
                payload["click"] = click
            if actions:
                payload["actions"] = actions[:3]  # ntfy permite max 3 botones
            headers = {"Authorization": f"Bearer {settings.ntfy_token}"} if settings.ntfy_token else {}
            r = httpx.post(settings.ntfy_server, json=payload, headers=headers, timeout=20)
            r.raise_for_status()
            return True
        except Exception as e:
            log.error("Fallo ntfy: %s", e)
            return False

    @staticmethod
    def reply_actions(source: str, url: str, opener: str, post_id: str = "") -> list[dict]:
        """Botones de la notificacion. 'view' abre la publicacion; en X la respuesta va pre-escrita."""
        actions = []
        if source == "twitter" and opener:
            tweet_id = post_id.split(":")[-1] if post_id else ""
            m = re.search(r"/status/(\d+)", url or "")
            if m:
                tweet_id = m.group(1)
            if tweet_id.isdigit():
                intent = f"https://twitter.com/intent/tweet?in_reply_to={tweet_id}&text={quote(opener)}"
                actions.append({"action": "view", "label": "Responder (pre-escrito)", "url": intent, "clear": True})
        if url:
            label = {"facebook": "Responder en Facebook", "linkedin": "Responder en LinkedIn", "freelancer": "Ver proyecto y ofertar",
                     "reddit": "Responder en Reddit", "telegram": "Abrir en Telegram", "twitter": "Ver tweet"}.get(source, "Abrir publicacion")
            actions.append({"action": "view", "label": label, "url": url, "clear": True})
        return actions

    def send_lead(self, *, source: str, score: int, language: str, summary: str, opener: str, text: str, url: str,
                  author: str | None, ai: bool, posted_at: str | None, location: str | None = None, post_id: str = "",
                  proposal=None, page_url: str | None = None, proposal_failed: bool = False) -> bool:
        if score >= 85:
            prio, flag = "urgent", "🔥"
        elif score >= 70:
            prio, flag = "high", "🎯"
        else:
            prio, flag = "default", "👀"
        dot = SOURCE_DOT.get(source, "\u26AA")
        title = f"{dot} {flag} Lead {score}/100 · {source.capitalize()} · {language.upper()}"
        excerpt = text.strip().replace("\n\n", "\n")
        if len(excerpt) > 500:
            excerpt = excerpt[:500] + "…"
        parts = [f"**{summary}**"]
        if proposal is not None:
            parts.append(f"\U0001F4B0 **Cobrar: {proposal.price_label}** · \u23F1 **{proposal.days} d\u00edas**")
            if proposal.justification:
                parts.append(f"_{proposal.justification}_")
        if author:
            parts.append(f"👤 {author}")
        if location:
            parts.append(f"📍 {location}")
        if posted_at:
            parts.append(f"🕒 {posted_at}")
        parts.append(f"\n**{excerpt}**")
        if proposal is not None and proposal.text:
            prop = proposal.text if len(proposal.text) <= 900 else proposal.text[:900] + "\u2026"
            parts.append(f"\n\U0001F4DD **Propuesta lista:**\n{prop}")
            if proposal.question:
                parts.append(f"\n\u2753 **Preguntar en el chat:** {proposal.question}")
        if opener:
            parts.append(f"\n💬 **Sugerencia para abrir** (mantén presionado para copiar):\n{opener}")
        parts.append(f"\n🔗 {url}")
        if proposal_failed:
            parts.append("\n\u26A0\uFE0F _Propuesta automatica no disponible ahora (Oxion no respondio). Usa el mensaje sugerido._")
        if not ai:
            parts.append("\n_(clasificado solo por keywords, sin IA)_")
        tags = SOURCE_TAGS.get(source, "bell")
        actions = []
        if page_url:
            actions.append({"action": "view", "label": "\U0001F4CB Copiar propuesta" if proposal else "\U0001F4CB Copiar mensaje",
                            "url": page_url, "clear": False})
        actions += self.reply_actions(source, url, opener, post_id)
        return self.send(title, "\n".join(parts), priority=prio, tags=tags, click=page_url or url, actions=actions)

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
