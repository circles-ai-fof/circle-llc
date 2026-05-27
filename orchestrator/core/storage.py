"""
SQLite-backed persistence for leads and gate runs (M2).

Drop-in replacement for the in-memory dicts used in M1. Activation:
  - If DATABASE_PATH env var is set -> SQLite at that path
  - Otherwise                       -> in-memory dicts (preserves test behavior)

Why SQLite, not Postgres?
  - Zero ops in M2 (Railway volume + 1 file).
  - Migration to Outcome DB (Postgres + pgvector) happens in M3 when N>=3 factories.
  - SQLite handles 1000+ writes/sec sequentially — fine for landing form traffic.

Thread-safety: SQLite connection is created per-request via context manager.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL,
    email           TEXT NOT NULL,
    name            TEXT,
    ip              TEXT,
    user_agent      TEXT,
    ts              INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_slug ON leads(slug);
CREATE INDEX IF NOT EXISTS idx_leads_ts ON leads(ts);

CREATE TABLE IF NOT EXISTS gate_runs (
    run_id              TEXT PRIMARY KEY,
    data_json           TEXT NOT NULL,
    needs_human_review  INTEGER NOT NULL DEFAULT 0,
    has_override        INTEGER NOT NULL DEFAULT 0,
    created_at          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gate_review
    ON gate_runs(needs_human_review, has_override);

-- R27 / ADR-010 — closed beta auth
CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    expires_at  INTEGER NOT NULL,
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_email ON sessions(email);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS auth_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL,
    ip          TEXT,
    user_agent  TEXT,
    ts          INTEGER NOT NULL,
    allowed     INTEGER NOT NULL DEFAULT 0,
    reason      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_ts ON auth_attempts(ts);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_email ON auth_attempts(email);

-- R28 / ADR-011 — autonomous hunter (sources + signals)
CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,         -- url|rss|hn|reddit|github_trending|product_hunt
    target          TEXT NOT NULL,         -- url or subreddit name
    name            TEXT NOT NULL,         -- display name for the UI
    active          INTEGER NOT NULL DEFAULT 1,
    last_scanned_at INTEGER,
    created_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_active ON sources(active);

CREATE TABLE IF NOT EXISTS signals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id         INTEGER,
    source_kind       TEXT NOT NULL,
    theme             TEXT NOT NULL,
    score             REAL NOT NULL,
    excerpt           TEXT NOT NULL,
    evidence_json     TEXT NOT NULL,       -- JSON array of urls
    suggested_topic   TEXT NOT NULL,
    feedback          TEXT,                -- 'up' | 'down' | NULL
    promoted_run_id   TEXT,                -- run_id if promoted to idea_hunter
    trend_score       REAL NOT NULL DEFAULT 0,  -- bumped when same theme reappears
    created_at        INTEGER NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_feedback ON signals(feedback);
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(created_at DESC);
"""

# Singleton path; resolved at first import after env load
_db_path: Optional[str] = None
_init_lock = threading.Lock()
_initialised = False


def _resolve_db_path() -> Optional[str]:
    raw = os.getenv("DATABASE_PATH", "").strip()
    return raw if raw else None


def _ensure_init() -> None:
    """Idempotently create the schema. Cheap to call repeatedly."""
    global _initialised, _db_path
    with _init_lock:
        if _initialised:
            return
        _db_path = _resolve_db_path()
        if _db_path:
            Path(_db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(_db_path) as conn:
                conn.executescript(_SCHEMA)
                # Migrations for existing databases — additive only
                _migrate(conn)
                conn.commit()
            logger.info("storage: SQLite ready at %s", _db_path)
        else:
            logger.info("storage: DATABASE_PATH not set -> in-memory mode")
        _initialised = True


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive column migrations idempotently."""
    # Add trend_score to signals if missing (M3.1)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "trend_score" not in cols:
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN trend_score REAL NOT NULL DEFAULT 0")
            logger.info("storage: migrated signals.trend_score column")
        except sqlite3.OperationalError as e:
            logger.warning("storage: migration trend_score failed: %s", e)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    """Per-call connection; sqlite3 handles locking with WAL well enough for M2."""
    _ensure_init()
    if not _db_path:
        raise RuntimeError("SQLite path not configured")
    conn = sqlite3.connect(_db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


# Memory fallback (used when DATABASE_PATH is unset)
_memory_leads: Dict[str, List[Dict]] = defaultdict(list)


class LeadsStore:
    """
    Append-mostly store. Public surface:
      - add(slug, email, name, ip, user_agent)
      - list_by_slug(slug) -> list of dicts
      - count() -> int
      - clear() -> for tests
    """

    def add(
        self,
        slug: str,
        email: str,
        name: Optional[str],
        ip: Optional[str],
        user_agent: Optional[str] = None,
    ) -> None:
        _ensure_init()
        ts = int(time.time())
        if _db_path:
            with _conn() as c:
                c.execute(
                    "INSERT INTO leads(slug,email,name,ip,user_agent,ts) "
                    "VALUES(?,?,?,?,?,?)",
                    (slug, email, name, ip, user_agent, ts),
                )
        else:
            _memory_leads[slug].append(
                {
                    "email": email,
                    "name": name,
                    "ip": ip,
                    "user_agent": user_agent,
                    "ts": ts,
                }
            )

    def list_by_slug(self, slug: str) -> List[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT slug,email,name,ip,user_agent,ts FROM leads "
                    "WHERE slug=? ORDER BY ts DESC",
                    (slug,),
                ).fetchall()
                return [dict(r) for r in rows]
        return list(_memory_leads.get(slug, []))

    def count(self) -> int:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute("SELECT COUNT(*) AS n FROM leads").fetchone()
                return int(row["n"])
        return sum(len(v) for v in _memory_leads.values())

    def clear(self) -> None:
        """Test-only."""
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM leads")
        _memory_leads.clear()


# ---------------------------------------------------------------------------
# Gate runs (already-serialised dicts)
# ---------------------------------------------------------------------------


# Memory store holds RunGateResponse objects directly (no roundtrip)
_memory_runs: Dict[str, Any] = {}


def _to_response(payload: Any):
    """Reconstruct a RunGateResponse from a dict so api.py code can use attribute access."""
    # Lazy import to avoid circular dependency at module load
    from ..schemas.api import RunGateResponse
    if isinstance(payload, RunGateResponse):
        return payload
    if isinstance(payload, dict):
        return RunGateResponse(**payload)
    return payload


class RunsStore:
    """
    Stores RunGateResponse keyed by run_id. Dict-like API:
      runs[run_id] = data         (Pydantic or dict accepted)
      runs.get(run_id) -> RunGateResponse | None
      runs.values()    -> [RunGateResponse, ...]
    """

    def __setitem__(self, run_id: str, data: Any) -> None:
        _ensure_init()
        if hasattr(data, "model_dump"):
            payload = data.model_dump(mode="json")
        else:
            payload = data
        if _db_path:
            with _conn() as c:
                c.execute(
                    "INSERT OR REPLACE INTO gate_runs"
                    "(run_id,data_json,needs_human_review,has_override,created_at)"
                    " VALUES(?,?,?,?,?)",
                    (
                        run_id,
                        json.dumps(payload, default=str),
                        1 if payload.get("needs_human_review") else 0,
                        1 if payload.get("human_override") else 0,
                        int(time.time()),
                    ),
                )
        else:
            _memory_runs[run_id] = data  # keep the original object in memory mode

    def __getitem__(self, run_id: str):
        v = self.get(run_id)
        if v is None:
            raise KeyError(run_id)
        return v

    def __contains__(self, run_id: str) -> bool:
        return self.get(run_id) is not None

    def get(self, run_id: str, default: Any = None):
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute(
                    "SELECT data_json FROM gate_runs WHERE run_id=?",
                    (run_id,),
                ).fetchone()
                if not row:
                    return default
                return _to_response(json.loads(row["data_json"]))
        v = _memory_runs.get(run_id, default)
        return _to_response(v) if v is not default and v is not None else default

    def values(self) -> List[Any]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT data_json FROM gate_runs ORDER BY created_at DESC"
                ).fetchall()
                return [_to_response(json.loads(r["data_json"])) for r in rows]
        return [_to_response(v) for v in _memory_runs.values()]

    def clear(self) -> None:
        """Test-only."""
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM gate_runs")
        _memory_runs.clear()


# ---------------------------------------------------------------------------
# Sessions + Auth attempts (closed beta auth, R27 / ADR-010)
# ---------------------------------------------------------------------------


_memory_sessions: Dict[str, Dict] = {}
_memory_auth_attempts: List[Dict] = []


class AuthStore:
    """
    Holds:
      - sessions: token -> {email, expires_at}
      - auth_attempts: append-only log of every login attempt
    """

    # ---- Sessions ----

    def create_session(self, token: str, email: str, expires_at: int) -> None:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                c.execute(
                    "INSERT OR REPLACE INTO sessions(token,email,expires_at,created_at) "
                    "VALUES(?,?,?,?)",
                    (token, email, expires_at, int(time.time())),
                )
        else:
            _memory_sessions[token] = {
                "email": email,
                "expires_at": expires_at,
                "created_at": int(time.time()),
            }

    def verify_session(self, token: str) -> Optional[Dict]:
        """Returns {email, expires_at} if valid + unexpired, else None."""
        _ensure_init()
        now = int(time.time())
        if _db_path:
            with _conn() as c:
                row = c.execute(
                    "SELECT email, expires_at FROM sessions "
                    "WHERE token=? AND expires_at > ?",
                    (token, now),
                ).fetchone()
                return dict(row) if row else None
        s = _memory_sessions.get(token)
        if s and s["expires_at"] > now:
            return {"email": s["email"], "expires_at": s["expires_at"]}
        return None

    def revoke_session(self, token: str) -> None:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM sessions WHERE token=?", (token,))
        else:
            _memory_sessions.pop(token, None)

    def cleanup_expired(self) -> int:
        """Remove sessions past their expiry. Returns count deleted."""
        _ensure_init()
        now = int(time.time())
        if _db_path:
            with _conn() as c:
                cur = c.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
                return cur.rowcount
        n = 0
        for t in list(_memory_sessions.keys()):
            if _memory_sessions[t]["expires_at"] <= now:
                del _memory_sessions[t]
                n += 1
        return n

    # ---- Auth attempts ----

    def log_attempt(
        self,
        email: str,
        ip: Optional[str],
        user_agent: Optional[str],
        allowed: bool,
        reason: str,
    ) -> None:
        _ensure_init()
        ts = int(time.time())
        if _db_path:
            with _conn() as c:
                c.execute(
                    "INSERT INTO auth_attempts(email,ip,user_agent,ts,allowed,reason) "
                    "VALUES(?,?,?,?,?,?)",
                    (email, ip, user_agent, ts, 1 if allowed else 0, reason),
                )
        else:
            _memory_auth_attempts.append(
                {
                    "email": email,
                    "ip": ip,
                    "user_agent": user_agent,
                    "ts": ts,
                    "allowed": allowed,
                    "reason": reason,
                }
            )

    def list_attempts(self, limit: int = 200) -> List[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT email,ip,user_agent,ts,allowed,reason FROM auth_attempts "
                    "ORDER BY ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
        return sorted(_memory_auth_attempts, key=lambda x: x["ts"], reverse=True)[:limit]

    def count_attempts(self) -> int:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute("SELECT COUNT(*) AS n FROM auth_attempts").fetchone()
                return int(row["n"])
        return len(_memory_auth_attempts)

    def clear(self) -> None:
        """Test-only."""
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM sessions")
                c.execute("DELETE FROM auth_attempts")
        _memory_sessions.clear()
        _memory_auth_attempts.clear()


# ---------------------------------------------------------------------------
# Sources + Signals (R28 / ADR-011 — autonomous hunter)
# ---------------------------------------------------------------------------


_memory_sources: List[Dict] = []
_memory_signals: List[Dict] = []


class SourcesStore:
    """CRUD for the source catalog."""

    def add(self, kind: str, target: str, name: str) -> int:
        _ensure_init()
        ts = int(time.time())
        if _db_path:
            with _conn() as c:
                cur = c.execute(
                    "INSERT INTO sources(kind,target,name,active,created_at) "
                    "VALUES(?,?,?,1,?)",
                    (kind, target, name, ts),
                )
                return int(cur.lastrowid)
        new_id = (max([s["id"] for s in _memory_sources], default=0) + 1)
        _memory_sources.append({
            "id": new_id, "kind": kind, "target": target, "name": name,
            "active": 1, "last_scanned_at": None, "created_at": ts,
        })
        return new_id

    def list(self, active_only: bool = False) -> List[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                q = "SELECT id,kind,target,name,active,last_scanned_at,created_at FROM sources"
                if active_only:
                    q += " WHERE active=1"
                q += " ORDER BY created_at DESC"
                return [dict(r) for r in c.execute(q).fetchall()]
        rows = _memory_sources
        if active_only:
            rows = [r for r in rows if r["active"]]
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)

    def get(self, source_id: int) -> Optional[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute(
                    "SELECT id,kind,target,name,active,last_scanned_at,created_at "
                    "FROM sources WHERE id=?", (source_id,)
                ).fetchone()
                return dict(row) if row else None
        for r in _memory_sources:
            if r["id"] == source_id:
                return dict(r)
        return None

    def mark_scanned(self, source_id: int) -> None:
        _ensure_init()
        ts = int(time.time())
        if _db_path:
            with _conn() as c:
                c.execute("UPDATE sources SET last_scanned_at=? WHERE id=?", (ts, source_id))
        else:
            for r in _memory_sources:
                if r["id"] == source_id:
                    r["last_scanned_at"] = ts
                    return

    def set_active(self, source_id: int, active: bool) -> None:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                c.execute("UPDATE sources SET active=? WHERE id=?", (1 if active else 0, source_id))
        else:
            for r in _memory_sources:
                if r["id"] == source_id:
                    r["active"] = 1 if active else 0
                    return

    def delete(self, source_id: int) -> None:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM sources WHERE id=?", (source_id,))
        else:
            _memory_sources[:] = [r for r in _memory_sources if r["id"] != source_id]

    def clear(self) -> None:
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM sources")
        _memory_sources.clear()


class SignalsStore:
    """Append-mostly store. Signals come from source_scanner runs."""

    def add(
        self,
        source_id: Optional[int],
        source_kind: str,
        theme: str,
        score: float,
        excerpt: str,
        evidence_urls: List[str],
        suggested_topic: str,
    ) -> int:
        _ensure_init()
        ts = int(time.time())
        ev_json = json.dumps(evidence_urls, ensure_ascii=False)
        # Compute trend_score: +1 per other signal with similar theme in last 7 days
        trend = self._compute_trend_score(theme, ts)
        if _db_path:
            with _conn() as c:
                cur = c.execute(
                    "INSERT INTO signals(source_id,source_kind,theme,score,excerpt,"
                    "evidence_json,suggested_topic,trend_score,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (source_id, source_kind, theme, score, excerpt, ev_json, suggested_topic, trend, ts),
                )
                return int(cur.lastrowid)
        new_id = max([s["id"] for s in _memory_signals], default=0) + 1
        _memory_signals.append({
            "id": new_id, "source_id": source_id, "source_kind": source_kind,
            "theme": theme, "score": score, "excerpt": excerpt,
            "evidence_json": ev_json, "suggested_topic": suggested_topic,
            "feedback": None, "promoted_run_id": None,
            "trend_score": trend, "created_at": ts,
        })
        return new_id

    def _compute_trend_score(self, theme: str, ts: int) -> float:
        """
        +1 for each prior signal with overlapping theme keywords seen in the
        last 7 days. Capped at 5.0 so a single hot topic doesn't dominate.
        """
        if not theme.strip():
            return 0.0
        cutoff = ts - 7 * 24 * 3600
        keywords = {w.lower() for w in theme.split() if len(w) > 4}
        if not keywords:
            return 0.0
        prior_themes: List[str] = []
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT theme FROM signals WHERE created_at >= ?", (cutoff,)
                ).fetchall()
                prior_themes = [r["theme"] for r in rows]
        else:
            prior_themes = [s["theme"] for s in _memory_signals if s["created_at"] >= cutoff]
        hits = 0
        for prev in prior_themes:
            prev_kw = {w.lower() for w in prev.split() if len(w) > 4}
            if keywords & prev_kw:
                hits += 1
        return min(5.0, float(hits))

    def list(self, limit: int = 100, min_score: float = 0.0) -> List[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT id,source_id,source_kind,theme,score,excerpt,evidence_json,"
                    "suggested_topic,feedback,promoted_run_id,trend_score,created_at "
                    "FROM signals WHERE score>=? "
                    "ORDER BY trend_score DESC, score DESC, created_at DESC LIMIT ?",
                    (min_score, limit),
                ).fetchall()
                return [_signal_row_to_dict(dict(r)) for r in rows]
        rows = [r for r in _memory_signals if r["score"] >= min_score]
        rows = sorted(
            rows,
            key=lambda r: (r.get("trend_score", 0), r["score"], r["created_at"]),
            reverse=True,
        )[:limit]
        return [_signal_row_to_dict(dict(r)) for r in rows]

    def get(self, signal_id: int) -> Optional[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute(
                    "SELECT id,source_id,source_kind,theme,score,excerpt,evidence_json,"
                    "suggested_topic,feedback,promoted_run_id,trend_score,created_at "
                    "FROM signals WHERE id=?", (signal_id,),
                ).fetchone()
                return _signal_row_to_dict(dict(row)) if row else None
        for r in _memory_signals:
            if r["id"] == signal_id:
                return _signal_row_to_dict(dict(r))
        return None

    def set_feedback(self, signal_id: int, feedback: Optional[str]) -> None:
        _ensure_init()
        if feedback not in (None, "up", "down"):
            raise ValueError(f"feedback must be up|down|None, got {feedback!r}")
        if _db_path:
            with _conn() as c:
                c.execute("UPDATE signals SET feedback=? WHERE id=?", (feedback, signal_id))
        else:
            for r in _memory_signals:
                if r["id"] == signal_id:
                    r["feedback"] = feedback
                    return

    def mark_promoted(self, signal_id: int, run_id: str) -> None:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                c.execute("UPDATE signals SET promoted_run_id=? WHERE id=?", (run_id, signal_id))
        else:
            for r in _memory_signals:
                if r["id"] == signal_id:
                    r["promoted_run_id"] = run_id
                    return

    def clear(self) -> None:
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM signals")
        _memory_signals.clear()


def _signal_row_to_dict(row: Dict) -> Dict:
    """Parse the evidence_json column back into a list."""
    try:
        row["evidence_urls"] = json.loads(row.pop("evidence_json"))
    except Exception:  # noqa: BLE001
        row["evidence_urls"] = []
    # Ensure trend_score is always present (legacy memory rows may lack it)
    row.setdefault("trend_score", 0)
    return row


# Module-level singletons used by api.py
leads_store = LeadsStore()
runs_store = RunsStore()
auth_store = AuthStore()
sources_store = SourcesStore()
signals_store = SignalsStore()


__all__ = [
    "leads_store",
    "runs_store",
    "auth_store",
    "sources_store",
    "signals_store",
    "LeadsStore",
    "RunsStore",
    "AuthStore",
    "SourcesStore",
    "SignalsStore",
]
