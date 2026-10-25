#!/usr/bin/env python3
"""
Dev Lead Hunter - bot que vigila redes/portales buscando personas que NECESITAN un desarrollador de software
y te avisa al instante por ntfy.

Uso:
  python main.py                 # modo 24/7 (loop, respeta el intervalo de cada fuente)
  python main.py --once          # una pasada por las fuentes que "toquen" segun su intervalo
  python main.py --once --force  # una pasada por TODAS las fuentes activas (ideal GitHub Actions)
  python main.py --once --state-json data/state.json   # persiste dedup en JSON (GitHub Actions)
  python main.py --dry-run       # no envia notificaciones, solo imprime
  python main.py --sources freelancer,facebook         # limita fuentes
  python main.py --test-notify   # envia una notificacion de prueba y sale
  python main.py --stats         # muestra estadisticas y ultimos leads
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from classifier import Classifier
from config import settings
from keywords import prefilter
from notifier import Notifier
from sources import build_sources
from sources.base import Post, Source
from storage import Storage

log = logging.getLogger("hunter")
_stop = False


def setup_logging():
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    try:
        fh = RotatingFileHandler(settings.data_dir / "hunter.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass
    for noisy in ("httpx", "httpcore", "apify_client", "google_genai", "google.genai", "telethon"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class Hunter:
    def __init__(self, *, dry_run: bool = False, only: list[str] | None = None, state_json: Path | None = None):
        self.dry_run = dry_run
        self.state_json = state_json
        self.storage = Storage(settings.data_dir / "hunter.db")
        if state_json:
            self.storage.import_json(state_json)
        self.notifier = Notifier()
        self.classifier = Classifier(self.storage)
        self.sources: list[Source] = [s for s in build_sources() if not only or s.name in only]
        self._error_notified: dict[str, float] = {}
        self._classified_this_tick = 0
        self._deferred = 0

    # ---------------- pipeline ----------------
    def process_post(self, post: Post) -> bool:
        """Devuelve True si se notifico como lead."""
        if not self.storage.mark_seen(post.id, post.source):
            return False
        text = post.full_text
        if len(text) < 25:
            return False
        src = next((s for s in self.sources if s.name == post.source), None)
        pre = prefilter(text, source_is_request=bool(src and src.is_request_source))
        if not pre.passes:
            log.debug("[%s] descartado por keywords (score=%d neg=%s): %s", post.source, pre.score, pre.negative_hits, text[:70])
            return False
        if self._classified_this_tick >= settings.max_classify_per_tick:
            # tope por tick para no colgarse con backlogs grandes: lo dejamos pendiente para el siguiente tick
            self.storage.unmark_seen(post.id)
            self._deferred += 1
            return False
        self._classified_this_tick += 1
        verdict = self.classifier.classify(text, post.source, pre)
        log.info("[%s] %s score=%d tipo=%s ai=%s | %s", post.source, "LEAD" if verdict.is_lead else "no",
                 verdict.score, verdict.lead_type, verdict.ai, (verdict.summary_es or text)[:80])
        if not verdict.is_lead or verdict.score < settings.min_score:
            return False
        self.storage.save_lead(
            id=post.id, source=post.source, score=verdict.score, lead_type=verdict.lead_type, language=verdict.language,
            summary=verdict.summary_es, opener=verdict.reply_opener, url=post.url, author=post.author,
            text=text[:2000], posted_at=post.posted_at_str, notified_at=int(time.time()), ai_classified=int(verdict.ai),
            location=verdict.location,
        )
        if self.dry_run:
            print(f"\n=== LEAD (dry-run) {verdict.score}/100 [{post.source}] ===\n{verdict.summary_es}\n{post.url}\n")
            return True
        return self.notifier.send_lead(
            source=post.source, score=verdict.score, language=verdict.language, summary=verdict.summary_es,
            opener=verdict.reply_opener, text=text, url=post.url, author=post.author, ai=verdict.ai, posted_at=post.posted_at_str,
            location=verdict.location if verdict.location and verdict.location.lower() != "no indicado" else None, post_id=post.id,
        )

    def run_source(self, source: Source) -> tuple[int, int]:
        t0 = time.time()
        try:
            posts = source.fetch()
        except Exception as e:
            msg = f"{type(e).__name__}: {str(e)[:300]}"
            log.error("Fuente %s fallo: %s", source.name, msg)
            self.storage.record_run(source.name, ok=False, error=msg)
            # avisa por ntfy maximo 1 vez cada 6h por fuente
            if not self.dry_run and time.time() - self._error_notified.get(source.name, 0) > 6 * 3600:
                self.notifier.send_error(source.name, msg)
                self._error_notified[source.name] = time.time()
            return 0, 0
        leads = 0
        posts.sort(key=lambda p: p.posted_at.timestamp() if p.posted_at else 0, reverse=True)  # mas nuevos primero
        for post in posts:
            try:
                if self.process_post(post):
                    leads += 1
            except Exception as e:  # un post corrupto no debe tumbar la fuente
                log.exception("Error procesando post %s: %s", post.id, e)
        self.storage.record_run(source.name, ok=True, items=len(posts), leads=leads)
        log.info("Fuente %s: %d posts, %d leads nuevos (%.1fs)", source.name, len(posts), leads, time.time() - t0)
        return len(posts), leads

    def due_sources(self, force: bool = False) -> list[Source]:
        if force:
            return list(self.sources)
        now = time.time()
        due = []
        for s in self.sources:
            last = self.storage.last_run(s.name)
            if last is None or now - last >= s.interval_minutes * 60:
                due.append(s)
        return due

    def run_once(self, force: bool = False) -> dict:
        due = self.due_sources(force)
        log.info("Fuentes a ejecutar: %s", [s.name for s in due] or "ninguna (todas dentro de su intervalo)")
        total_posts = total_leads = 0
        self._classified_this_tick = 0
        self._deferred = 0
        for s in due:
            if _stop:
                break
            p, l = self.run_source(s)
            total_posts += p
            total_leads += l
        if self._deferred:
            log.info("%d posts quedaron pendientes de clasificar (tope MAX_CLASSIFY_PER_TICK=%d); siguen en el proximo tick.",
                     self._deferred, settings.max_classify_per_tick)
        if self.state_json:
            self.storage.export_json(self.state_json)
        return {"sources": [s.name for s in due], "posts": total_posts, "leads": total_leads, "deferred": self._deferred}

    def loop(self):
        names = [s.name for s in self.sources]
        log.info("Modo 24/7. Fuentes: %s. Tick cada %d min.", names, settings.loop_tick_minutes)
        if not self.dry_run:
            self.notifier.send_startup(names)
        while not _stop:
            try:
                r = self.run_once()
                if r["sources"]:
                    log.info("Tick: %d posts, %d leads. Dedup total: %d. Leads total: %d",
                             r["posts"], r["leads"], self.storage.seen_count(), self.storage.leads_count())
            except Exception as e:
                log.exception("Error en tick: %s", e)
            for _ in range(settings.loop_tick_minutes * 60):
                if _stop:
                    break
                time.sleep(1)
        log.info("Detenido.")

    def print_stats(self):
        print("\n== Fuentes ==")
        for r in self.storage.source_stats():
            last = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["last_run"])) if r["last_run"] else "-"
            print(f"  {r['source']:<11} ultima={last} items={r['total_items']} leads={r['total_leads']} "
                  f"errores={r['total_errors']} {('ERR: ' + (r['last_error'] or '')[:60]) if r['last_error'] else ''}")
        print(f"\n== Totales == vistos={self.storage.seen_count()} leads={self.storage.leads_count()} "
              f"gemini_hoy={int(self.storage.get_counter(Storage.today_key('gemini')))}")
        if settings.apify_token:
            try:
                from sources.apify_base import apify_budget_status
                used, mx = apify_budget_status(force=True)
                print(f"== Apify == gastado este mes: ${used:.3f} / plan ${mx:.2f} (tope bot ${settings.apify_monthly_budget_usd})")
            except Exception:
                pass
        print("\n== Ultimos leads ==")
        for l in self.storage.recent_leads(10):
            print(f"  [{l['score']:>3}] {l['source']:<10} {l['summary'][:70]}\n        {l['url']}")


def _handle_stop(signum, frame):
    global _stop
    _stop = True
    log.info("Senal %s recibida, cerrando...", signum)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dev Lead Hunter")
    ap.add_argument("--once", action="store_true", help="una sola pasada y salir")
    ap.add_argument("--force", action="store_true", help="ignorar intervalos (ejecutar todas las fuentes)")
    ap.add_argument("--dry-run", action="store_true", help="no enviar notificaciones")
    ap.add_argument("--sources", default="", help="lista separada por comas: freelancer,reddit,facebook,linkedin,twitter,telegram")
    ap.add_argument("--state-json", default="", help="ruta JSON para importar/exportar dedup (GitHub Actions)")
    ap.add_argument("--test-notify", action="store_true", help="enviar notificacion de prueba")
    ap.add_argument("--stats", action="store_true", help="mostrar estadisticas")
    args = ap.parse_args(argv)

    setup_logging()
    for w in settings.validate():
        log.warning("CONFIG: %s", w)

    if args.test_notify:
        n = Notifier()
        ok = n.send_lead(source="facebook", score=92, language="es",
                         summary="Duena de bodega en Lima busca sistema de ventas e inventario con boletas electronicas",
                         opener="Hola! Vi que necesitas un sistema de ventas para tu bodega, he hecho varios con facturacion electronica, te cuento?",
                         text="Hola, busco un programador que me haga un sistema de ventas e inventario para mi bodega en Lima...",
                         url="https://www.facebook.com/groups/programadoresperu", author="Prueba", ai=True, posted_at=None,
                         location="Lima, Peru", post_id="facebook:test")
        print("Notificacion enviada" if ok else "No se pudo enviar (revisa NTFY_TOPIC)")
        return 0 if ok else 1

    only = [s.strip() for s in args.sources.split(",") if s.strip()] or None
    state = Path(args.state_json) if args.state_json else None
    hunter = Hunter(dry_run=args.dry_run, only=only, state_json=state)

    if args.stats:
        hunter.print_stats()
        return 0

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    if not hunter.sources:
        log.error("No hay fuentes activas. Revisa tu .env")
        return 1

    if args.once:
        r = hunter.run_once(force=args.force)
        log.info("Listo: %s", r)
        return 0
    hunter.loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
