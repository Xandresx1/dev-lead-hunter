"""Tests de la fuente Bright Data (grupos de Facebook) SIN gastar creditos: HTTP simulado con httpx.MockTransport.
Ejecutar:  python test_brightdata.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("BRIGHTDATA_API_TOKEN", "test-token")
os.environ["DATA_DIR"] = tempfile.mkdtemp()

import httpx  # noqa: E402

from config import settings  # noqa: E402
from sources import brightdata_facebook as bd  # noqa: E402
from sources.brightdata_facebook import BrightDataBudgetExceeded, BrightDataError, BrightDataFacebookGroupsSource  # noqa: E402
from storage import Storage  # noqa: E402

bd.POLL_SECONDS = 0  # no dormir en tests

RECORD = {
    "post_id": "1234567890123", "url": "https://www.facebook.com/groups/660236834107139/posts/1234567890123/",
    "content": "Hola, busco un programador que me haga un sistema de inventario para mi tienda en Arequipa, alguien?",
    "user_username_raw": "Maria Lopez", "date_posted": "2026-10-25T14:00:00.000Z", "likes": 3, "num_comments": 5,
    "group_name": "Emprendedores Arequipa", "group_url": "https://www.facebook.com/groups/660236834107139",
}


def make_source(handler, storage=None):
    client = httpx.Client(base_url=bd.BASE_URL, transport=httpx.MockTransport(handler))
    src = BrightDataFacebookGroupsSource(client=client)
    src.storage = storage or Storage(Path(tempfile.mkdtemp()) / "t.db")
    return src


def test_full_flow_ready():
    calls = {"trigger": 0, "progress": 0, "snapshot": 0}

    def handler(req: httpx.Request):
        if req.url.path == "/datasets/v3/trigger":
            calls["trigger"] += 1
            assert req.headers["authorization"] == "Bearer test-token"
            assert req.url.params["dataset_id"] == settings.brightdata_dataset_id
            body = json.loads(req.content)
            assert isinstance(body, list) and body and body[0]["url"].startswith("https://www.facebook.com/groups/")
            assert body[0]["num_of_posts"] == settings.brightdata_posts_per_group
            assert "start_date" in body[0] and "end_date" in body[0]
            return httpx.Response(200, json={"snapshot_id": "s_test1"})
        if req.url.path == "/datasets/v3/progress/s_test1":
            calls["progress"] += 1
            return httpx.Response(200, json={"status": "running" if calls["progress"] < 3 else "ready"})
        if req.url.path == "/datasets/v3/snapshot/s_test1":
            calls["snapshot"] += 1
            return httpx.Response(200, json=[RECORD, {**RECORD, "post_id": "9999999999999", "content": ""},
                                             {"input": {"url": "x"}, "error": "group not public", "error_code": "dead_page"}])
        return httpx.Response(404)

    src = make_source(handler)
    posts = src.fetch()
    assert calls == {"trigger": 1, "progress": 3, "snapshot": 1}, calls
    assert len(posts) == 1, posts
    p = posts[0]
    assert p.id == "facebook:1234567890123" and p.source == "facebook" and p.author == "Maria Lopez"
    assert p.posted_at is not None and p.extra["group"] == "Emprendedores Arequipa" and p.extra["provider"] == "brightdata"
    assert src.pending_snapshot() is None, "snapshot debe limpiarse al terminar"
    assert src.records_this_month() == 2, "cuenta registros entregados sin error (incluye vacios)"
    print("OK test_full_flow_ready")


def test_pending_snapshot_resume_across_runs():
    """Si el snapshot no esta listo, se guarda y la proxima corrida lo retoma SIN volver a disparar."""
    settings.brightdata_wait_seconds = 0
    state = {"triggers": 0, "ready": False}

    def handler(req: httpx.Request):
        if req.url.path == "/datasets/v3/trigger":
            state["triggers"] += 1
            return httpx.Response(200, json={"snapshot_id": "s_slow"})
        if req.url.path.startswith("/datasets/v3/progress/"):
            return httpx.Response(200, json={"status": "ready" if state["ready"] else "collecting"})
        if req.url.path.startswith("/datasets/v3/snapshot/"):
            return httpx.Response(200, json=[RECORD])
        return httpx.Response(404)

    storage = Storage(Path(tempfile.mkdtemp()) / "t.db")
    src = make_source(handler, storage)
    # corrida 1: dispara, no esta listo -> [] y snapshot pendiente
    assert src.fetch() == []
    assert src.pending_snapshot() == "s_slow" and state["triggers"] == 1
    # con snapshot pendiente la fuente "toca" aunque acabe de correr
    assert src.is_due(last_run=time.time(), now=time.time()) is True

    # simulamos export/import de state.json (GitHub Actions)
    sj = Path(tempfile.mkdtemp()) / "state.json"
    storage.export_json(sj)
    data = json.loads(sj.read_text())
    assert data["meta"]["brightdata:snapshot"] == "s_slow"
    storage2 = Storage(Path(tempfile.mkdtemp()) / "t2.db")
    storage2.import_json(sj)
    src2 = make_source(handler, storage2)
    assert src2.pending_snapshot() == "s_slow"

    # corrida 2: ya esta listo -> descarga sin disparar de nuevo
    state["ready"] = True
    posts = src2.fetch()
    assert len(posts) == 1 and state["triggers"] == 1, state
    assert src2.pending_snapshot() is None
    # sin pendiente y recien corrida -> no toca
    assert src2.is_due(last_run=time.time(), now=time.time()) is False
    settings.brightdata_wait_seconds = 420
    print("OK test_pending_snapshot_resume_across_runs")


def test_failed_snapshot_clears_and_raises():
    def handler(req: httpx.Request):
        if req.url.path == "/datasets/v3/trigger":
            return httpx.Response(200, json={"snapshot_id": "s_bad"})
        if req.url.path.startswith("/datasets/v3/progress/"):
            return httpx.Response(200, json={"status": "failed", "message": "boom"})
        return httpx.Response(404)

    src = make_source(handler)
    try:
        src.fetch()
        raise AssertionError("debia fallar")
    except BrightDataError as e:
        assert "failed" in str(e)
    assert src.pending_snapshot() is None, "un snapshot fallido no debe quedar pendiente"
    print("OK test_failed_snapshot_clears_and_raises")


def test_monthly_cap_blocks_trigger():
    def handler(req: httpx.Request):
        raise AssertionError("no debe llamar a la API con el tope alcanzado")

    storage = Storage(Path(tempfile.mkdtemp()) / "t.db")
    storage.set_counter(Storage.month_key(bd.COUNTER_PREFIX), settings.brightdata_monthly_records)
    src = make_source(handler, storage)
    try:
        src.fetch()
        raise AssertionError("debia lanzar BudgetExceeded")
    except BrightDataBudgetExceeded as e:
        assert "Tope mensual" in str(e)
    print("OK test_monthly_cap_blocks_trigger")


def test_exclude_seen_ids_and_400_fallback():
    seen_bodies = []

    def handler(req: httpx.Request):
        if req.url.path == "/datasets/v3/trigger":
            body = json.loads(req.content)
            seen_bodies.append(body)
            if "posts_to_not_include" in body[0]:
                return httpx.Response(400, json={"error": "unknown field"})
            return httpx.Response(200, json={"snapshot_id": "s_ok"})
        if req.url.path.startswith("/datasets/v3/progress/"):
            return httpx.Response(200, json={"status": "ready"})
        if req.url.path.startswith("/datasets/v3/snapshot/"):
            return httpx.Response(200, json=[RECORD])
        return httpx.Response(404)

    storage = Storage(Path(tempfile.mkdtemp()) / "t.db")
    storage.mark_seen("facebook:1111111111111", "facebook")
    storage.mark_seen("facebook:fb:abcdef0123456789", "facebook")  # hash interno: NO debe enviarse
    storage.mark_seen("freelancer:123", "freelancer")
    src = make_source(handler, storage)
    posts = src.fetch()
    assert len(posts) == 1
    assert len(seen_bodies) == 2, "primero con exclusiones, luego sin ellas tras el 400"
    assert seen_bodies[0][0]["posts_to_not_include"] == ["1111111111111"], seen_bodies[0][0]
    assert "posts_to_not_include" not in seen_bodies[1][0]
    print("OK test_exclude_seen_ids_and_400_fallback")


def test_source_registered_and_apify_groups_default():
    from sources import build_sources
    names = [s.name for s in build_sources()]
    assert "fbgroups" in names, names
    # las fuentes de pago van primero (prioridad en la cuota de Gemini)
    assert names.index("fbgroups") < names.index("freelancer"), names
    print("OK test_source_registered_and_apify_groups_default:", names)


if __name__ == "__main__":
    test_full_flow_ready()
    test_pending_snapshot_resume_across_runs()
    test_failed_snapshot_clears_and_raises()
    test_monthly_cap_blocks_trigger()
    test_exclude_seen_ids_and_400_fallback()
    test_source_registered_and_apify_groups_default()
    print("\nTODOS LOS TESTS DE BRIGHT DATA PASARON")
    sys.exit(0)
