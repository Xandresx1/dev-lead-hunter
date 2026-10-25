"""Clasificador de leads: Gemini (google-genai, salida JSON estricta) con fallback a keywords."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel

from config import settings
from keywords import PrefilterResult
from storage import Storage

log = logging.getLogger("classifier")


class LeadVerdict(BaseModel):
    is_lead: bool
    score: int
    lead_type: Literal["cliente_directo", "oferta_servicios", "empleo_corporativo", "otro"]
    language: Literal["es", "en", "otro"]
    summary_es: str
    reply_opener: str


@dataclass
class Verdict:
    is_lead: bool
    score: int
    lead_type: str
    language: str
    summary_es: str
    reply_opener: str
    ai: bool  # True si lo decidio Gemini, False si fue fallback por keywords


SYSTEM_PROMPT = """Eres el filtro de un ingeniero de software/sistemas freelance de Peru que busca CLIENTES (no empleo).
Analizas publicaciones de redes sociales y portales (espanol o ingles).

is_lead = true SOLO si una persona, emprendedor o pequeno negocio NECESITA que alguien le construya, arregle o automatice
software (sistema, app, pagina web, bot, scraping, integracion, tesis, excel avanzado, etc.) y esta buscando a quien contratar
o pidiendo recomendaciones/cotizacion. Tambien cuenta si una empresa pequena busca un freelancer o proveedor para un proyecto concreto.

SOLO cuenta desarrollo de SOFTWARE/sistemas/automatizacion/datos. Si el pedido es de otra cosa (edicion de video, diseno grafico,
redaccion, marketing, ventas, contabilidad, documentacion ISO, traduccion, soporte al cliente, ingenieria mecanica/civil/FEA/CFD, etc.) -> is_lead=false, lead_type=otro.

is_lead = false si:
- La persona OFRECE sus servicios o busca empleo (lead_type = oferta_servicios).
- Es una oferta de empleo corporativa: empresa contratando empleados con requisitos, anos de experiencia, planilla, senior/junior (lead_type = empleo_corporativo).
- Es spam, curso, noticia, meme, tutorial, pregunta tecnica, debate o cualquier otra cosa (lead_type = otro).

score (0-100) = probabilidad de que sea un cliente real alcanzable por mensaje directo que pagaria por el desarrollo.
Penaliza: texto vago, muy antiguo, sin proyecto concreto, o que pide trabajo gratis.
Deseos casuales o bromas ("ojala existiera una app que...", "alguien deberia hacer una app", "necesito una app que me haga X" sin
intencion real de contratar/pagar) -> is_lead=false o score <= 30.
Premia: proyecto claro, negocio real, menciona presupuesto/cotizacion, pide contacto.

language: es | en | otro.
summary_es: 1 linea en espanol: QUIEN necesita QUE (max 30 palabras).
reply_opener: primera frase sugerida para contactar a la persona, escrita en el idioma del post, cercana y concreta, max 30 palabras.
"""


class Classifier:
    def __init__(self, storage: Storage):
        self.storage = storage
        self._client = None
        self._last_call = 0.0
        self._disabled_until = 0.0
        if settings.gemini_api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=settings.gemini_api_key)
                log.info("Gemini activo (%s)", settings.gemini_model)
            except Exception as e:  # pragma: no cover
                log.warning("No se pudo iniciar Gemini: %s", e)

    @property
    def available(self) -> bool:
        if self._client is None or time.time() < self._disabled_until:
            return False
        used = self.storage.get_counter(Storage.today_key("gemini"))
        if used >= settings.gemini_daily_limit:
            log.warning("Cuota diaria de Gemini alcanzada (%s). Fallback a keywords.", int(used))
            return False
        return True

    def classify(self, text: str, source: str, pre: PrefilterResult) -> Verdict:
        if self.available:
            v = self._classify_gemini(text, source)
            if v is not None:
                return v
        return self._fallback(pre)

    def _fallback(self, pre: PrefilterResult) -> Verdict:
        return Verdict(
            is_lead=pre.passes and pre.score >= settings.min_score,
            score=pre.score,
            lead_type="cliente_directo" if pre.passes else "otro",
            language="?",
            summary_es="(Sin IA) Coincidencia por palabras clave: " + ", ".join(pre.need_hits[:2]) if pre.need_hits else "(Sin IA) Pedido en portal freelance",
            reply_opener="",
            ai=False,
        )

    def _classify_gemini(self, text: str, source: str) -> Optional[Verdict]:
        from google.genai import types

        wait = settings.gemini_min_interval_sec - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        contents = f"FUENTE: {source}\nPUBLICACION:\n{text[: settings.max_post_chars]}"
        for attempt in range(3):
            try:
                self._last_call = time.time()
                resp = self._client.models.generate_content(
                    model=settings.gemini_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=LeadVerdict,
                        temperature=0.1,
                    ),
                )
                self.storage.incr(Storage.today_key("gemini"))
                parsed: LeadVerdict | None = resp.parsed
                if parsed is None:
                    parsed = LeadVerdict.model_validate_json(resp.text)
                return Verdict(
                    is_lead=parsed.is_lead,
                    score=max(0, min(100, int(parsed.score))),
                    lead_type=parsed.lead_type,
                    language=parsed.language,
                    summary_es=parsed.summary_es.strip(),
                    reply_opener=parsed.reply_opener.strip(),
                    ai=True,
                )
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    backoff = 10 * (attempt + 1)
                    log.warning("Gemini 429 (rate limit). Espero %ss", backoff)
                    time.sleep(backoff)
                    continue
                if "403" in msg or "401" in msg or "API key" in msg or "PERMISSION_DENIED" in msg:
                    log.error("Gemini: problema de API key (%s). Desactivo IA por 1h.", msg[:120])
                    self._disabled_until = time.time() + 3600
                    return None
                log.warning("Gemini error (%s): %s", type(e).__name__, msg[:200])
                time.sleep(2)
        log.warning("Gemini fallo 3 veces; desactivo IA por 10 min y uso fallback.")
        self._disabled_until = time.time() + 600
        return None
