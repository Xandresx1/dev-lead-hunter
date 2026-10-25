"""Base para fuentes Apify con control de gasto (budget guard) real via API de Apify."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from decimal import Decimal

from config import settings
from sources.base import Source

log = logging.getLogger("source.apify")

_client = None
_budget_cache = {"ts": 0.0, "used": 0.0, "max": 0.0}


def apify_client():
    global _client
    if _client is None:
        from apify_client import ApifyClient

        _client = ApifyClient(settings.apify_token)
    return _client


def apify_budget_status(force: bool = False) -> tuple[float, float]:
    """(usado_usd_este_mes, limite_plan_usd). Cache de 10 minutos."""
    if force or time.time() - _budget_cache["ts"] > 600:
        try:
            lim = apify_client().user().limits()
            d = lim.model_dump() if hasattr(lim, "model_dump") else dict(lim)
            _budget_cache["used"] = float(d["current"]["monthly_usage_usd"])
            _budget_cache["max"] = float(d["limits"]["max_monthly_usage_usd"])
            _budget_cache["ts"] = time.time()
        except Exception as e:
            log.warning("No pude leer limites de Apify: %s", e)
    return _budget_cache["used"], _budget_cache["max"]


class BudgetExceeded(RuntimeError):
    pass


class ApifySource(Source):
    uses_apify = True
    actor_id: str = ""

    def run_actor(self, run_input: dict, *, max_items: int | None = None, timeout_sec: int = 300) -> list[dict]:
        used, plan_max = apify_budget_status()
        budget = min(settings.apify_monthly_budget_usd, plan_max or settings.apify_monthly_budget_usd)
        if used >= budget:
            raise BudgetExceeded(f"Presupuesto Apify agotado: ${used:.2f} usados de ${budget:.2f} este mes. "
                                 f"Se reanuda al iniciar el siguiente ciclo o si subes APIFY_MONTHLY_BUDGET_USD.")
        client = apify_client()
        log.info("Apify run %s (gasto mes: $%.3f / $%.2f)", self.actor_id, used, budget)
        run = client.actor(self.actor_id).call(
            run_input=run_input,
            max_items=max_items,
            max_total_charge_usd=Decimal(str(settings.apify_max_charge_per_run_usd)),
            run_timeout=timedelta(seconds=timeout_sec),
            wait_duration=timedelta(seconds=timeout_sec + 30),
            logger=None,
        )
        if run is None:
            raise RuntimeError("Apify no devolvio run")
        rd = run.model_dump(by_alias=True) if hasattr(run, "model_dump") else dict(run)
        status = str(rd.get("status", ""))
        if "SUCCEEDED" not in status:
            raise RuntimeError(f"Actor {self.actor_id} termino con status={status}: {rd.get('statusMessage')}")
        items = list(client.dataset(rd["defaultDatasetId"]).iterate_items(limit=max_items or 500))
        apify_budget_status(force=True)
        log.info("Apify %s -> %d items (usd run=%s)", self.actor_id, len(items), rd.get("usageTotalUsd"))
        return items
