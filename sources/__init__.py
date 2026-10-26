"""Registro de fuentes. Cada fuente se activa/desactiva por .env y falla de forma aislada."""
from __future__ import annotations

import logging

from config import settings
from sources.base import Source

log = logging.getLogger("sources")


def build_sources() -> list[Source]:
    sources: list[Source] = []

    if settings.freelancer_enabled:
        from sources.freelancer import FreelancerSource
        sources.append(FreelancerSource())

    if settings.reddit_enabled:
        from sources.reddit import RedditSource
        sources.append(RedditSource())

    if settings.brightdata_enabled and settings.brightdata_token and settings.brightdata_groups:
        from sources.brightdata_facebook import BrightDataFacebookGroupsSource
        sources.append(BrightDataFacebookGroupsSource())

    if settings.apify_token:
        if settings.facebook_enabled and settings.facebook_groups:
            from sources.apify_facebook import FacebookGroupsSource
            sources.append(FacebookGroupsSource())
        if settings.fbsearch_enabled and settings.fbsearch_queries:
            from sources.apify_facebook_search import FacebookSearchSource
            sources.append(FacebookSearchSource())
        if settings.linkedin_enabled:
            from sources.apify_linkedin import LinkedInSource
            sources.append(LinkedInSource())
        if settings.twitter_enabled:
            from sources.apify_twitter import TwitterSource
            sources.append(TwitterSource())
    else:
        log.warning("APIFY_TOKEN vacio -> Facebook/LinkedIn/X desactivados")

    if settings.telegram_enabled and settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_groups:
        try:
            from sources.telegram_groups import TelegramSource
            sources.append(TelegramSource())
        except ImportError:
            log.warning("Telethon no instalado -> Telegram desactivado (pip install telethon)")

    # Las fuentes de pago (Apify / Bright Data: mas caras y mas valiosas) primero para que tengan prioridad en la cuota de Gemini por tick
    sources.sort(key=lambda s: (not (s.uses_apify or s.paid), s.name))
    return sources
