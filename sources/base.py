"""Clases base para fuentes."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Post:
    id: str  # unico y estable, prefijado por fuente: "facebook:123"
    source: str
    text: str
    url: str
    title: str = ""
    author: str = ""
    posted_at: Optional[datetime] = None
    extra: dict = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return f"{self.title}\n{self.text}".strip() if self.title else self.text.strip()

    @property
    def posted_at_str(self) -> str | None:
        return self.posted_at.strftime("%Y-%m-%d %H:%M UTC") if self.posted_at else None

    @staticmethod
    def stable_id(source: str, *parts: str) -> str:
        raw = "|".join(p for p in parts if p)
        return f"{source}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


class Source:
    name: str = "base"
    interval_minutes: int = 60
    is_request_source: bool = False  # True si TODO lo que devuelve son pedidos de trabajo (ej. Freelancer)
    uses_apify: bool = False
    paid: bool = False  # True si cada post leido cuesta dinero (Apify, Bright Data)
    storage = None  # lo inyecta Hunter; permite a la fuente guardar estado entre corridas (ej. snapshot pendiente)

    def fetch(self) -> list[Post]:  # pragma: no cover - interface
        raise NotImplementedError

    def is_due(self, last_run: float | None, now: float) -> bool:
        """Toca ejecutar? Por defecto respeta interval_minutes. Las fuentes pueden forzar (ej. trabajo pendiente)."""
        return last_run is None or now - last_run >= self.interval_minutes * 60

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} every {self.interval_minutes}m>"


def parse_dt(value) -> Optional[datetime]:
    """Convierte epoch / ISO string a datetime UTC (tolerante)."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            if value > 1e12:
                value /= 1000
            return datetime.fromtimestamp(value, tz=timezone.utc)
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None
