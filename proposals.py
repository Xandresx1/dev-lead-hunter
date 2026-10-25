"""Redaccion automatica de propuestas (precio + plazo + texto) con Claude via Oxion AI (API compatible OpenAI).
Solo para las fuentes/idiomas configurados (por defecto: Freelancer en espanol)."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from config import BASE_DIR, settings
from sources.base import Post

log = logging.getLogger("proposals")


@dataclass
class Proposal:
    text: str
    price_usd: float
    price_type: str  # fijo | por_hora
    days: int
    justification: str
    question: str
    model: str

    @property
    def price_label(self) -> str:
        p = f"USD {self.price_usd:,.0f}" if self.price_usd >= 10 else f"USD {self.price_usd:,.2f}"
        return f"{p}/hora" if self.price_type == "por_hora" else p


class ProposalWriter:
    def __init__(self):
        self.enabled = bool(settings.oxion_api_key)
        self.base_url = settings.oxion_base_url.rstrip("/")
        self.model = settings.oxion_model
        self._disabled_until = 0.0
        self._template = self._load_template()
        if self.enabled:
            log.info("Propuestas automaticas activas (%s) para %s en %s", self.model, settings.proposal_sources, settings.proposal_languages)

    @staticmethod
    def _load_template() -> str:
        p = Path(settings.proposal_prompt_file) if settings.proposal_prompt_file else BASE_DIR / "prompts" / "proposal_es.md"
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            log.warning("No pude leer el prompt de propuestas (%s): %s", p, e)
            return ""

    def applies(self, post: Post, language: str, ignore_pause: bool = False) -> bool:
        """True si a este lead le corresponde propuesta automatica. ignore_pause=True para decidir si se encola aunque Oxion este caido."""
        if not self.enabled or not self._template:
            return False
        if not ignore_pause and time.time() < self._disabled_until:
            return False
        if post.source not in settings.proposal_sources:
            return False
        lang = (post.extra.get("lang") or language or "").lower()[:2]
        return lang in settings.proposal_languages

    # ---------- contexto desde el post ----------
    @staticmethod
    def _context(post: Post) -> dict:
        x = post.extra or {}
        budget = x.get("budget") or "no indicado"
        if x.get("budget_min") is not None:
            budget = f"{x.get('budget_min')}-{x.get('budget_max')} {x.get('currency', '')} ({'por hora' if x.get('price_type') == 'hourly' else 'precio fijo'})"
        avg = "sin datos"
        if x.get("bid_avg"):
            avg = f"{x['bid_avg']:.0f} {x.get('currency', '')} ({x.get('bids', '?')} ofertas)"
        client_bits = []
        if x.get("country"):
            client_bits.append(f"pais {x['country']}")
        client_bits.append("proyecto con escrow" if x.get("escrow") else "sin escrow")
        if x.get("hourly_commitment"):
            client_bits.append(f"dedicacion {x['hourly_commitment']}")
        client_bits.append("sin historial visible (asumir cliente nuevo)")
        return {
            "DESCRIPCION": post.full_text[: settings.max_post_chars],
            "PRESUPUESTO": budget,
            "PROMEDIO": avg,
            "INFO_CLIENTE": ", ".join(client_bits),
            "EXPERIENCIA_RELEVANTE": settings.proposal_experience or "(nada adicional)",
        }

    def _render(self, post: Post) -> str:
        out = self._template
        for k, v in self._context(post).items():
            out = out.replace("{{" + k + "}}", str(v))
        return out

    # ---------- llamada a Oxion ----------
    def write(self, post: Post, language: str) -> Optional[Proposal]:
        if not self.applies(post, language):
            return None
        prompt = self._render(post)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Devuelves unicamente JSON valido. Nada de markdown ni explicaciones fuera del JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 900,
        }
        headers = {"Authorization": f"Bearer {settings.oxion_api_key}", "Content-Type": "application/json"}
        for attempt in range(3):
            try:
                r = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=90)
                if r.status_code in (401, 403):
                    log.error("Oxion: API key invalida o sin permisos (%s). Desactivo propuestas 1h.", r.status_code)
                    self._disabled_until = time.time() + 3600
                    return None
                if r.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                if r.status_code in (502, 503, 504):
                    log.warning("Oxion no disponible (%s: %s). Pauso propuestas %d min; los leads quedan en cola de reintento.",
                                r.status_code, r.text[:90].replace("\n", " "), settings.proposal_pause_minutes)
                    self._disabled_until = time.time() + settings.proposal_pause_minutes * 60
                    return None
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                data = self._parse_json(content)
                return Proposal(
                    text=str(data.get("propuesta", "")).strip(),
                    price_usd=float(data.get("precio_usd") or 0),
                    price_type="por_hora" if str(data.get("tipo_precio", "")).lower().startswith("por") else "fijo",
                    days=int(float(data.get("plazo_dias") or 0)),
                    justification=str(data.get("justificacion", "")).strip(),
                    question=str(data.get("pregunta", "")).strip(),
                    model=self.model,
                )
            except Exception as e:
                log.warning("Oxion intento %d fallo: %s: %s", attempt + 1, type(e).__name__, str(e)[:200])
                time.sleep(2)
        log.warning("Oxion fallo 3 veces; pauso propuestas %d min.", settings.proposal_pause_minutes)
        self._disabled_until = time.time() + settings.proposal_pause_minutes * 60
        return None

    @property
    def paused(self) -> bool:
        return time.time() < self._disabled_until

    @staticmethod
    def post_payload(post: Post, language: str, score: int, summary: str, opener: str, location: str | None) -> dict:
        """Serializa lo necesario para reintentar la propuesta mas tarde (cola en state.json)."""
        return {"id": post.id, "source": post.source, "title": post.title, "text": post.text, "url": post.url, "author": post.author,
                "extra": post.extra, "language": language, "score": score, "summary": summary, "opener": opener, "location": location}

    @staticmethod
    def post_from_payload(d: dict) -> Post:
        return Post(id=d["id"], source=d["source"], text=d.get("text", ""), url=d.get("url", ""), title=d.get("title", ""),
                    author=d.get("author", ""), extra=d.get("extra") or {})

    @staticmethod
    def _parse_json(content: str) -> dict:
        content = content.strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.S)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, flags=re.S)
            if not m:
                raise
            return json.loads(m.group(0))

    def list_models(self) -> list[str]:
        r = httpx.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {settings.oxion_api_key}"}, timeout=30)
        r.raise_for_status()
        return [m.get("id") for m in r.json().get("data", [])]
