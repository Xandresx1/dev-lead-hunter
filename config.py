"""Configuracion central del bot (todo via variables de entorno / .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "si", "sí")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


@dataclass
class Settings:
    # --- General ---
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))))
    loop_tick_minutes: int = _int("LOOP_TICK_MINUTES", 5)
    min_score: int = _int("MIN_SCORE", 90)
    max_post_chars: int = _int("MAX_POST_CHARS", 1500)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # --- ntfy ---
    ntfy_server: str = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    ntfy_topic: str = os.getenv("NTFY_TOPIC", "")
    ntfy_token: str = os.getenv("NTFY_TOKEN", "")
    notify_errors: bool = _bool("NOTIFY_ERRORS", True)

    # --- Gemini ---
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    gemini_daily_limit: int = _int("GEMINI_DAILY_LIMIT", 900)
    gemini_min_interval_sec: float = _float("GEMINI_MIN_INTERVAL_SEC", 4.5)
    max_classify_per_tick: int = _int("MAX_CLASSIFY_PER_TICK", 40)

    # --- Apify ---
    apify_token: str = os.getenv("APIFY_TOKEN", "")
    apify_monthly_budget_usd: float = _float("APIFY_MONTHLY_BUDGET_USD", 4.5)
    apify_max_charge_per_run_usd: float = _float("APIFY_MAX_CHARGE_PER_RUN_USD", 0.15)

    # --- Filtro anti-estafa: monedas excluidas (ej. INR por reportes de estafas) ---
    excluded_currencies: list[str] = field(default_factory=lambda: [c.upper() for c in _list("EXCLUDED_CURRENCIES", ["INR"])])

    # --- Propuestas automaticas con Claude via Oxion AI (API compatible OpenAI) ---
    oxion_api_key: str = os.getenv("OXION_API_KEY", "")
    oxion_base_url: str = os.getenv("OXION_BASE_URL", "https://www.oxionai.com/v1")
    oxion_model: str = os.getenv("OXION_MODEL", "claude-sonnet-5")
    proposal_sources: list[str] = field(default_factory=lambda: _list("PROPOSAL_SOURCES", ["freelancer"]))
    proposal_languages: list[str] = field(default_factory=lambda: [l.lower()[:2] for l in _list("PROPOSAL_LANGUAGES", ["es"])])
    proposal_prompt_file: str = os.getenv("PROPOSAL_PROMPT_FILE", "")
    proposal_experience: str = os.getenv("PROPOSAL_EXPERIENCE", "")
    proposal_pause_minutes: int = _int("PROPOSAL_PAUSE_MINUTES", 15)      # pausa tras un 503 de Oxion
    proposal_retry_per_run: int = _int("PROPOSAL_RETRY_PER_RUN", 10)     # pendientes a reintentar por corrida
    proposal_pending_ttl_hours: int = _int("PROPOSAL_PENDING_TTL_HOURS", 48)

    # --- Mini paginas (GitHub Pages) con boton Copiar ---
    pages_enabled: bool = _bool("PAGES_ENABLED", True)
    pages_dir: str = os.getenv("PAGES_DIR", str(BASE_DIR / "docs"))
    pages_base_url: str = os.getenv("PAGES_BASE_URL", "")
    pages_salt: str = os.getenv("PAGES_SALT", "dev-lead-hunter")

    # --- Fuente: Freelancer (gratis, sin key) ---
    freelancer_enabled: bool = _bool("FREELANCER_ENABLED", True)
    freelancer_interval_minutes: int = _int("FREELANCER_INTERVAL_MINUTES", 10)
    freelancer_queries_es: list[str] = field(default_factory=lambda: _list(
        "FREELANCER_QUERIES_ES",
        ["sistema", "aplicacion", "app movil", "pagina web", "software", "automatizacion", "bot", "tesis"]))
    freelancer_queries_en: list[str] = field(default_factory=lambda: _list(
        "FREELANCER_QUERIES_EN", ["need a developer", "build an app", "web application", "software system", "automation bot"]))
    freelancer_limit_per_query: int = _int("FREELANCER_LIMIT_PER_QUERY", 15)

    # --- Fuente: Reddit (gratis, tolerante a bloqueos) ---
    reddit_enabled: bool = _bool("REDDIT_ENABLED", True)
    reddit_interval_minutes: int = _int("REDDIT_INTERVAL_MINUTES", 20)
    reddit_subreddits: list[str] = field(default_factory=lambda: _list(
        "REDDIT_SUBREDDITS", ["forhire", "hiring", "slavelabour", "Entrepreneur", "smallbusiness", "startups", "PERU", "Peru", "mexico", "argentina", "es"]))
    reddit_client_id: str = os.getenv("REDDIT_CLIENT_ID", "")
    reddit_client_secret: str = os.getenv("REDDIT_CLIENT_SECRET", "")

    # --- Fuente: Facebook grupos (Apify) ---
    facebook_enabled: bool = _bool("FACEBOOK_ENABLED", True)
    facebook_interval_minutes: int = _int("FACEBOOK_INTERVAL_MINUTES", 720)
    facebook_groups: list[str] = field(default_factory=lambda: _list(
        "FACEBOOK_GROUPS", ["https://www.facebook.com/groups/programadoresperu"]))
    facebook_posts_per_group: int = _int("FACEBOOK_POSTS_PER_GROUP", 5)
    facebook_newer_than: str = os.getenv("FACEBOOK_NEWER_THAN", "2 days")

    # --- Fuente: LinkedIn posts (Apify) ---
    linkedin_enabled: bool = _bool("LINKEDIN_ENABLED", True)
    linkedin_interval_minutes: int = _int("LINKEDIN_INTERVAL_MINUTES", 720)
    linkedin_keywords: list[str] = field(default_factory=lambda: _list(
        "LINKEDIN_KEYWORDS", ["busco desarrollador", "necesito un sistema"]))
    linkedin_posts_per_keyword: int = _int("LINKEDIN_POSTS_PER_KEYWORD", 10)
    linkedin_date_filter: str = os.getenv("LINKEDIN_DATE_FILTER", "past-24h")

    # --- Fuente: X / Twitter (Apify) ---
    twitter_enabled: bool = _bool("TWITTER_ENABLED", True)
    twitter_interval_minutes: int = _int("TWITTER_INTERVAL_MINUTES", 960)
    twitter_query: str = os.getenv(
        "TWITTER_QUERY",
        '("busco programador" OR "necesito un programador" OR "busco desarrollador" '
        'OR "necesito un sistema" OR "looking for a developer" OR "need a developer" OR "need an app built") -is:retweet')
    twitter_max_items: int = _int("TWITTER_MAX_ITEMS", 20)

    # --- Fuente: Telegram grupos publicos (opcional, Telethon) ---
    telegram_enabled: bool = _bool("TELEGRAM_ENABLED", False)
    telegram_interval_minutes: int = _int("TELEGRAM_INTERVAL_MINUTES", 15)
    telegram_api_id: str = os.getenv("TELEGRAM_API_ID", "")
    telegram_api_hash: str = os.getenv("TELEGRAM_API_HASH", "")
    telegram_groups: list[str] = field(default_factory=lambda: _list("TELEGRAM_GROUPS", []))
    telegram_messages_per_group: int = _int("TELEGRAM_MESSAGES_PER_GROUP", 30)

    def validate(self) -> list[str]:
        """Devuelve advertencias (no fatales) sobre la configuracion."""
        warnings = []
        if not self.ntfy_topic:
            warnings.append("NTFY_TOPIC vacio: no se enviaran notificaciones.")
        if not self.gemini_api_key:
            warnings.append("GEMINI_API_KEY vacio: se usara solo filtrado por keywords (mas falsos positivos).")
        if not self.apify_token and (self.facebook_enabled or self.linkedin_enabled or self.twitter_enabled):
            warnings.append("APIFY_TOKEN vacio: Facebook/LinkedIn/X quedan desactivados.")
        if self.oxion_api_key and not self.pages_base_url:
            warnings.append("PAGES_BASE_URL vacio: las propuestas iran solo en la notificacion (sin pagina con boton Copiar).")
        if self.telegram_enabled and not (self.telegram_api_id and self.telegram_api_hash):
            warnings.append("TELEGRAM_ENABLED=true pero faltan TELEGRAM_API_ID/HASH: Telegram desactivado.")
        return warnings


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
