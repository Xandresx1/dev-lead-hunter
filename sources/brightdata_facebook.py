"""Facebook grupos PUBLICOS via Bright Data (Web Scraper API, dataset "Facebook - Posts by group URL").

Flujo asincrono de Bright Data:
  1. POST /datasets/v3/trigger  -> snapshot_id        (se cobra ~$1.50 por 1000 registros entregados)
  2. GET  /datasets/v3/progress/{snapshot_id}         (starting/running/collecting/digesting -> ready | failed)
  3. GET  /datasets/v3/snapshot/{snapshot_id}?format=json

Como el bot corre en GitHub Actions (tiempo limitado), si el snapshot no esta listo dentro de BRIGHTDATA_WAIT_SECONDS
se guarda el snapshot_id en la memoria del bot (state.json) y se retoma en la SIGUIENTE corrida sin volver a disparar
(y sin volver a pagar). Tope mensual de registros para no pasar los $5 gratis: BRIGHTDATA_MONTHLY_RECORDS.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

from config import settings
from sources.base import Post, Source, parse_dt

log = logging.getLogger("source.fbgroups")

BASE_URL = "https://api.brightdata.com"
META_SNAPSHOT = "brightdata:snapshot"          # snapshot_id pendiente
META_SNAPSHOT_TS = "brightdata:snapshot_ts"    # cuando se disparo (epoch)
COUNTER_PREFIX = "brightdata:records"          # + ":YYYY-MM" -> registros entregados este mes
SNAPSHOT_MAX_AGE_SEC = 24 * 3600               # un snapshot pendiente de mas de 24 h se descarta
POLL_SECONDS = 15
_UNFINISHED = {"starting", "running", "collecting", "digesting", "scheduled", "building"}


class BrightDataError(RuntimeError):
    pass


class BrightDataBudgetExceeded(BrightDataError):
    pass


class BrightDataFacebookGroupsSource(Source):
    name = "fbgroups"
    paid = True

    def __init__(self, client: httpx.Client | None = None):
        self.interval_minutes = settings.brightdata_interval_minutes
        self._client = client
        if client is not None:  # cliente inyectado (tests): igual lleva la autenticacion
            client.headers.update({"Authorization": f"Bearer {settings.brightdata_token}", "Content-Type": "application/json"})

    # ---------------- infra ----------------
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=BASE_URL, timeout=60,
                headers={"Authorization": f"Bearer {settings.brightdata_token}", "Content-Type": "application/json"},
            )
        return self._client

    def _meta(self, key: str) -> str | None:
        return self.storage.get_meta(key) if self.storage else None

    def _set_meta(self, key: str, value: str | None):
        if self.storage:
            self.storage.set_meta(key, value)

    def pending_snapshot(self) -> str | None:
        snap = self._meta(META_SNAPSHOT)
        if not snap:
            return None
        ts = float(self._meta(META_SNAPSHOT_TS) or 0)
        if ts and time.time() - ts > SNAPSHOT_MAX_AGE_SEC:
            log.warning("Snapshot pendiente %s tiene mas de 24 h, lo descarto.", snap)
            self._clear_snapshot()
            return None
        return snap

    def _clear_snapshot(self):
        self._set_meta(META_SNAPSHOT, None)
        self._set_meta(META_SNAPSHOT_TS, None)

    def records_this_month(self) -> int:
        if not self.storage:
            return 0
        from storage import Storage
        return int(self.storage.get_counter(Storage.month_key(COUNTER_PREFIX)))

    def budget_status(self) -> tuple[int, int]:
        """(registros entregados este mes, tope mensual)."""
        return self.records_this_month(), settings.brightdata_monthly_records

    def is_due(self, last_run, now) -> bool:
        # si hay un snapshot en curso, hay que retomarlo aunque "no toque" por intervalo
        if self.pending_snapshot():
            return True
        return super().is_due(last_run, now)

    # ---------------- API Bright Data ----------------
    def _exclude_ids(self, limit: int = 300) -> list[str]:
        """IDs de posts de Facebook ya vistos (solo IDs numericos reales, no hashes internos)."""
        if not self.storage:
            return []
        out = []
        for sid in self.storage.seen_ids("facebook:", limit=limit * 2):
            raw = sid.split(":", 1)[1]
            if re.fullmatch(r"\d{6,}", raw):
                out.append(raw)
            if len(out) >= limit:
                break
        return out

    def _build_inputs(self, exclude: list[str]) -> list[dict]:
        today = datetime.now(timezone.utc)
        start = (today - timedelta(days=max(1, settings.brightdata_days_back))).strftime("%m-%d-%Y")
        end = today.strftime("%m-%d-%Y")
        n = max(1, settings.brightdata_posts_per_group)
        inputs = []
        for g in settings.brightdata_groups:
            item = {"url": g.strip().rstrip("/"), "num_of_posts": n, "start_date": start, "end_date": end}
            if exclude:
                item["posts_to_not_include"] = exclude
            inputs.append(item)
        return inputs

    def trigger(self, inputs: list[dict]) -> str:
        last_err = None
        for attempt in range(3):
            r = self.client.post("/datasets/v3/trigger", params={"dataset_id": settings.brightdata_dataset_id, "format": "json"}, json=inputs)
            if r.status_code < 400:
                data = r.json()
                snap = data.get("snapshot_id") if isinstance(data, dict) else None
                if not snap:
                    raise BrightDataError(f"trigger sin snapshot_id: {str(data)[:300]}")
                return snap
            last_err = BrightDataError(f"trigger HTTP {r.status_code}: {r.text[:300]}")
            # visto en pruebas: la primera llamada de una cuenta nueva responde 400 "Customer is not active" y a los segundos ya funciona
            if r.status_code in (429, 500, 502, 503) or "not active" in r.text.lower():
                log.warning("Bright Data trigger fallo (intento %d/3): %s. Reintento en %ds", attempt + 1, last_err, 20 * (attempt + 1))
                time.sleep(20 * (attempt + 1))
                continue
            raise last_err
        raise last_err

    def progress(self, snapshot_id: str) -> dict:
        r = self.client.get(f"/datasets/v3/progress/{snapshot_id}")
        if r.status_code >= 400:
            raise BrightDataError(f"progress HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    def download(self, snapshot_id: str) -> list[dict]:
        r = self.client.get(f"/datasets/v3/snapshot/{snapshot_id}", params={"format": "json"})
        if r.status_code == 202:   # todavia construyendo
            return None
        if r.status_code >= 400:
            raise BrightDataError(f"snapshot HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        if isinstance(data, dict):
            data = data.get("data") or data.get("records") or []
        return data if isinstance(data, list) else []

    def wait(self, snapshot_id: str, max_seconds: int) -> list[dict] | None:
        """Espera hasta max_seconds. Devuelve registros, o None si sigue en curso."""
        deadline = time.monotonic() + max_seconds
        while True:
            p = self.progress(snapshot_id)
            status = str(p.get("status", "")).lower()
            if status == "ready":
                rows = self.download(snapshot_id)
                if rows is not None:
                    return rows
            elif status in ("failed", "canceled", "cancelled"):
                raise BrightDataError(f"snapshot {snapshot_id} termino con status={status}: {str(p)[:200]}")
            elif status and status not in _UNFINISHED:
                log.info("Bright Data snapshot %s status desconocido '%s', sigo esperando", snapshot_id, status)
            if time.monotonic() >= deadline:
                return None
            time.sleep(POLL_SECONDS)

    # ---------------- Source ----------------
    def fetch(self) -> list[Post]:
        if not settings.brightdata_groups:
            return []
        snap = self.pending_snapshot()
        if snap:
            log.info("Bright Data: retomando snapshot pendiente %s", snap)
        else:
            used, cap = self.budget_status()
            if used >= cap:
                raise BrightDataBudgetExceeded(
                    f"Tope mensual de Bright Data alcanzado: {used}/{cap} registros. Se reanuda el proximo mes "
                    f"o si subes BRIGHTDATA_MONTHLY_RECORDS.")
            exclude = self._exclude_ids()
            inputs = self._build_inputs(exclude)
            log.info("Bright Data trigger: %d grupos x %d posts (ultimos %d dia/s, %d IDs excluidos; mes: %d/%d registros)",
                     len(inputs), settings.brightdata_posts_per_group, settings.brightdata_days_back, len(exclude), used, cap)
            try:
                snap = self.trigger(inputs)
            except BrightDataError as e:
                if exclude and "400" in str(e):
                    log.warning("Trigger rechazo posts_to_not_include, reintento sin exclusiones: %s", e)
                    snap = self.trigger(self._build_inputs([]))
                else:
                    raise
            self._set_meta(META_SNAPSHOT, snap)
            self._set_meta(META_SNAPSHOT_TS, str(int(time.time())))
            log.info("Bright Data snapshot_id=%s", snap)
        try:
            rows = self.wait(snap, settings.brightdata_wait_seconds)
        except BrightDataError:
            self._clear_snapshot()   # no reintentar un snapshot fallido
            raise
        if rows is None:
            log.info("Bright Data snapshot %s aun no esta listo; se retoma en la proxima corrida (sin costo extra).", snap)
            return []
        self._clear_snapshot()
        posts, errors = self._normalize(rows)
        if self.storage:
            from storage import Storage
            self.storage.incr(Storage.month_key(COUNTER_PREFIX), len(rows) - errors)
        log.info("Bright Data: %d registros (%d con error) -> %d posts", len(rows), errors, len(posts))
        return posts

    @staticmethod
    def _normalize(rows: list[dict]) -> tuple[list[Post], int]:
        posts: dict[str, Post] = {}
        errors = 0
        for it in rows:
            if not isinstance(it, dict):
                continue
            if it.get("error") or it.get("error_code"):
                errors += 1
                log.warning("Bright Data registro con error: %s (%s)", it.get("error"), (it.get("input") or {}).get("url"))
                continue
            text = it.get("content") or it.get("post_text") or it.get("text") or ""
            if not str(text).strip() and isinstance(it.get("original_post"), dict):
                text = it["original_post"].get("content") or ""   # post compartido: el texto va en el original
            if not str(text).strip():
                continue
            url = it.get("url") or it.get("post_url") or ""
            raw_id = it.get("post_id") or it.get("id")
            pid = f"facebook:{raw_id}" if raw_id else Post.stable_id("fbg", url, str(text)[:80])
            if pid in posts:
                continue
            author = it.get("user_username_raw") or it.get("user_name") or it.get("author") or ""
            if isinstance(author, dict):
                author = author.get("name") or ""
            posts[pid] = Post(
                id=pid, source="facebook", text=str(text), url=url, author=str(author or ""),
                posted_at=parse_dt(it.get("date_posted")),
                extra={"group": it.get("group_name"), "group_url": it.get("group_url"), "likes": it.get("likes"),
                       "comments": it.get("num_comments"), "provider": "brightdata"},
            )
        return list(posts.values()), errors
