"""Persistencia SQLite: dedup, leads, estado de fuentes, uso de Gemini. Exporta/importa JSON para GitHub Actions."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


class Storage:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        c = self.db
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, source TEXT, first_seen INTEGER);
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY, source TEXT, score INTEGER, lead_type TEXT, language TEXT,
                summary TEXT, opener TEXT, url TEXT, author TEXT, text TEXT, posted_at TEXT,
                notified_at INTEGER, ai_classified INTEGER DEFAULT 1, location TEXT
            );
            CREATE TABLE IF NOT EXISTS source_runs (
                source TEXT PRIMARY KEY, last_run INTEGER, last_ok INTEGER, last_items INTEGER,
                total_items INTEGER DEFAULT 0, total_leads INTEGER DEFAULT 0, total_errors INTEGER DEFAULT 0, last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value REAL);
            """
        )
        c.commit()
        # migracion suave para bases creadas antes de la columna location
        cols = {r[1] for r in c.execute("PRAGMA table_info(leads)").fetchall()}
        if "location" not in cols:
            c.execute("ALTER TABLE leads ADD COLUMN location TEXT")
            c.commit()

    # ---------- dedup ----------
    def is_seen(self, post_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM seen WHERE id=?", (post_id,)).fetchone() is not None

    def mark_seen(self, post_id: str, source: str) -> bool:
        """True si era nuevo."""
        try:
            self.db.execute("INSERT INTO seen VALUES (?,?,?)", (post_id, source, int(time.time())))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def unmark_seen(self, post_id: str):
        self.db.execute("DELETE FROM seen WHERE id=?", (post_id,))
        self.db.commit()

    def seen_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM seen").fetchone()[0]

    # ---------- leads ----------
    def save_lead(self, **kw):
        cols = ",".join(kw.keys())
        qs = ",".join("?" * len(kw))
        self.db.execute(f"INSERT OR REPLACE INTO leads ({cols}) VALUES ({qs})", tuple(kw.values()))
        self.db.commit()

    def recent_leads(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute("SELECT * FROM leads ORDER BY notified_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def leads_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    # ---------- source runs ----------
    def last_run(self, source: str) -> Optional[int]:
        r = self.db.execute("SELECT last_run FROM source_runs WHERE source=?", (source,)).fetchone()
        return r[0] if r else None

    def record_run(self, source: str, ok: bool, items: int = 0, leads: int = 0, error: str | None = None):
        now = int(time.time())
        row = self.db.execute("SELECT * FROM source_runs WHERE source=?", (source,)).fetchone()
        if row is None:
            self.db.execute(
                "INSERT INTO source_runs VALUES (?,?,?,?,?,?,?,?)",
                (source, now, now if ok else None, items, items, leads, 0 if ok else 1, error),
            )
        else:
            self.db.execute(
                """UPDATE source_runs SET last_run=?, last_ok=COALESCE(?, last_ok), last_items=?,
                   total_items=total_items+?, total_leads=total_leads+?, total_errors=total_errors+?, last_error=?
                   WHERE source=?""",
                (now, now if ok else None, items, items, leads, 0 if ok else 1, error, source),
            )
        self.db.commit()

    def source_stats(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM source_runs ORDER BY source").fetchall()]

    # ---------- counters (cuota gemini por dia, etc.) ----------
    def incr(self, key: str, by: float = 1) -> float:
        self.db.execute(
            "INSERT INTO counters(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=value+excluded.value", (key, by)
        )
        self.db.commit()
        return self.get_counter(key)

    def get_counter(self, key: str) -> float:
        r = self.db.execute("SELECT value FROM counters WHERE key=?", (key,)).fetchone()
        return float(r[0]) if r else 0.0

    def set_counter(self, key: str, value: float):
        self.db.execute("INSERT OR REPLACE INTO counters(key,value) VALUES(?,?)", (key, value))
        self.db.commit()

    @staticmethod
    def today_key(prefix: str) -> str:
        return f"{prefix}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

    # ---------- export / import (modo GitHub Actions) ----------
    def export_json(self, path: Path, max_seen: int = 8000, include_leads: bool = False):
        """Estado minimo para GitHub Actions. Por defecto NO incluye el texto de los leads
        (el repo puede ser publico); el historial de leads vive en tus notificaciones ntfy."""
        seen = [r[0] for r in self.db.execute("SELECT id FROM seen ORDER BY first_seen DESC LIMIT ?", (max_seen,)).fetchall()]
        runs = {r["source"]: r["last_run"] for r in self.db.execute("SELECT source,last_run FROM source_runs").fetchall()}
        counters = {r[0]: r[1] for r in self.db.execute("SELECT key,value FROM counters").fetchall()}
        leads = self.recent_leads(100) if include_leads else []
        stats = {"leads_total": self.leads_count(), "seen_total": self.seen_count()}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"seen": seen, "runs": runs, "counters": counters, "leads": leads, "stats": stats},
                                         ensure_ascii=False, indent=0))

    def import_json(self, path: Path):
        p = Path(path)
        if not p.exists():
            return
        data = json.loads(p.read_text() or "{}")
        now = int(time.time())
        self.db.executemany("INSERT OR IGNORE INTO seen VALUES (?,?,?)", [(s, "import", now) for s in data.get("seen", [])])
        for source, last_run in (data.get("runs") or {}).items():
            self.db.execute("INSERT OR IGNORE INTO source_runs(source,last_run) VALUES(?,?)", (source, last_run))
        for k, v in (data.get("counters") or {}).items():
            self.db.execute("INSERT OR IGNORE INTO counters(key,value) VALUES(?,?)", (k, v))
        for lead in data.get("leads") or []:
            cols = ",".join(lead.keys()); qs = ",".join("?" * len(lead))
            self.db.execute(f"INSERT OR IGNORE INTO leads ({cols}) VALUES ({qs})", tuple(lead.values()))
        self.db.commit()

    def close(self):
        self.db.close()
