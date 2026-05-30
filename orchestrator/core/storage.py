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

-- R30 / ADR-013 — bitácora de links analizados
CREATE TABLE IF NOT EXISTS links_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT NOT NULL,
    source_file     TEXT,                -- nombre del archivo de donde salió (whatsapp/txt/docx) o NULL
    status          TEXT NOT NULL,       -- 'pending' | 'analyzed' | 'rejected' | 'error'
    idea_summary    TEXT,
    sector          TEXT,
    area            TEXT,
    rejection_reason TEXT,
    created_at      INTEGER NOT NULL,
    analyzed_at     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_links_status ON links_log(status);
CREATE INDEX IF NOT EXISTS idx_links_ts ON links_log(created_at DESC);

-- M4.0 / ADR-018 — registro de cuentas conectadas por plataforma
-- Esta tabla NO almacena secrets. Las credenciales viven en env vars.
-- Esta tabla solo registra el ESTADO observado por el founder:
--   "esta plataforma está lista", "falta configurar oauth", etc.
CREATE TABLE IF NOT EXISTS connected_accounts (
    platform        TEXT PRIMARY KEY,    -- youtube|bluesky|linkedin|x|instagram|tiktok|...
    status          TEXT NOT NULL,       -- 'ready'|'configured'|'missing_credentials'|'deferred'
    oauth_required  INTEGER NOT NULL DEFAULT 0,
    notes           TEXT,                -- libre — el founder anota qué hizo
    configured_at   INTEGER              -- unix ts cuando se marcó como configurada
);

-- M4.1 / ADR-019 — embeddings de señales para aprendizaje de preferencias
-- vector_blob: bytes packed con struct ('<384f') para ahorrar espacio vs JSON
-- cluster_id: -1 == ruido / no clasificado
CREATE TABLE IF NOT EXISTS signal_embeddings (
    signal_id      INTEGER PRIMARY KEY,
    vector_blob    BLOB NOT NULL,
    cluster_id     INTEGER NOT NULL DEFAULT -1,
    model_version  TEXT NOT NULL,
    created_at     INTEGER NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_emb_cluster ON signal_embeddings(cluster_id);

-- M4.1 / ADR-019 — nivel de autonomía del cazador (single-row)
CREATE TABLE IF NOT EXISTS autonomy (
    id           INTEGER PRIMARY KEY CHECK (id = 1),  -- enforce single row
    level        TEXT NOT NULL DEFAULT 'manual',      -- manual|assisted|autonomous_with_approval
    updated_at   INTEGER NOT NULL
);
INSERT OR IGNORE INTO autonomy(id, level, updated_at) VALUES(1, 'manual', strftime('%s','now'));
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
    # M3.2 follow-up: original publication timestamp of the source item
    cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "published_at" not in cols:
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN published_at INTEGER")
            logger.info("storage: migrated signals.published_at column")
        except sqlite3.OperationalError as e:
            logger.warning("storage: migration published_at failed: %s", e)
    # M4.4 — language detection + on-demand translation
    cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "language" not in cols:
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN language TEXT")
            logger.info("storage: migrated signals.language column")
        except sqlite3.OperationalError as e:
            logger.warning("storage: migration language failed: %s", e)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "translated_theme" not in cols:
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN translated_theme TEXT")
            conn.execute("ALTER TABLE signals ADD COLUMN translated_excerpt TEXT")
            logger.info("storage: migrated signals.translated_theme + translated_excerpt columns")
        except sqlite3.OperationalError as e:
            logger.warning("storage: migration translation failed: %s", e)
    # M4.3 — content_type classification (heuristic, sin LLM)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "content_type" not in cols:
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN content_type TEXT")
            logger.info("storage: migrated signals.content_type column")
        except sqlite3.OperationalError as e:
            logger.warning("storage: migration content_type failed: %s", e)
    # M3.5: optional analysis JSON blob (idea_analyzer output) — nullable until
    # the founder clicks "Analizar" in the dashboard
    cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "analysis_json" not in cols:
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN analysis_json TEXT")
            logger.info("storage: migrated signals.analysis_json column")
        except sqlite3.OperationalError as e:
            logger.warning("storage: migration analysis_json failed: %s", e)
    # M3.6: parallel array of titles for each evidence URL (for nicer hovercards)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "item_titles_json" not in cols:
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN item_titles_json TEXT")
            logger.info("storage: migrated signals.item_titles_json column")
        except sqlite3.OperationalError as e:
            logger.warning("storage: migration item_titles_json failed: %s", e)


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

    def list_recent(self, limit: int = 20, verdict: Optional[str] = None) -> List[Dict]:
        """M4.10 — Lista de runs ordenados por fecha desc, lista para mostrar
        en el dashboard de overview. Devuelve dicts con los campos
        esenciales (no la RunGateResponse completa) para hacer el payload
        más ligero. Si necesitás más detalle, hacer GET /gate/runs/{run_id}.

        Args:
            limit: máximo de runs a retornar (1-100)
            verdict: filtra por "pass" / "kill" / "iterate" si está dado
        """
        _ensure_init()
        rows: List[Dict] = []
        if _db_path:
            with _conn() as c:
                q = "SELECT run_id, data_json, created_at FROM gate_runs ORDER BY created_at DESC"
                if limit > 0:
                    q += f" LIMIT {int(limit) * 4}"  # leemos extra por si filtramos
                for row in c.execute(q):
                    try:
                        data = json.loads(row["data_json"])
                    except (ValueError, TypeError):
                        continue
                    if verdict and data.get("verdict") != verdict:
                        continue
                    rows.append({
                        "run_id": row["run_id"],
                        "idea_title": data.get("idea_title") or "(sin título)",
                        "verdict": data.get("verdict") or "unknown",
                        "confidence": float(data.get("confidence") or 0),
                        "landing_slug": data.get("landing_slug") or "",
                        "cost_usd_estimated": float(data.get("cost_usd_estimated") or 0),
                        "needs_human_review": bool(data.get("needs_human_review")),
                        "created_at": int(row["created_at"]),
                    })
                    if limit > 0 and len(rows) >= limit:
                        break
            return rows
        # In-memory fallback
        items = list(_memory_runs.items())
        # Sin timestamps en memoria — usamos orden de inserción (más nuevo último)
        items.reverse()
        for run_id, run_obj in items:
            data = run_obj.model_dump(mode="json") if hasattr(run_obj, "model_dump") else (run_obj or {})
            if verdict and data.get("verdict") != verdict:
                continue
            rows.append({
                "run_id": run_id,
                "idea_title": data.get("idea_title") or "(sin título)",
                "verdict": data.get("verdict") or "unknown",
                "confidence": float(data.get("confidence") or 0),
                "landing_slug": data.get("landing_slug") or "",
                "cost_usd_estimated": float(data.get("cost_usd_estimated") or 0),
                "needs_human_review": bool(data.get("needs_human_review")),
                "created_at": 0,
            })
            if limit > 0 and len(rows) >= limit:
                break
        return rows

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

    def delete_many(
        self,
        source_ids: Optional[List[int]] = None,
        kind_filter: Optional[str] = None,
        name_contains: Optional[str] = None,
        target_contains: Optional[str] = None,
    ) -> int:
        """M3.16: bulk delete with filters. Returns count deleted.

        Modes (combine OR-style or use only one):
          - source_ids: explicit list of IDs to delete
          - kind_filter: delete all sources of one kind (e.g. "url")
          - name_contains: substring match on name (case-insensitive)
          - target_contains: substring match on target URL (e.g. "instagram.com")
        """
        _ensure_init()
        if not any([source_ids, kind_filter, name_contains, target_contains]):
            return 0  # safety: never delete-all without explicit criterion
        if _db_path:
            with _conn() as c:
                if source_ids:
                    placeholders = ",".join("?" for _ in source_ids)
                    cur = c.execute(
                        f"DELETE FROM sources WHERE id IN ({placeholders})",
                        tuple(source_ids),
                    )
                    return int(cur.rowcount or 0)
                where_parts: List[str] = []
                params: List = []
                if kind_filter:
                    where_parts.append("kind = ?")
                    params.append(kind_filter)
                if name_contains:
                    where_parts.append("LOWER(name) LIKE ?")
                    params.append(f"%{name_contains.lower()}%")
                if target_contains:
                    where_parts.append("LOWER(target) LIKE ?")
                    params.append(f"%{target_contains.lower()}%")
                where = " AND ".join(where_parts)
                cur = c.execute(f"DELETE FROM sources WHERE {where}", tuple(params))
                return int(cur.rowcount or 0)
        # In-memory fallback
        def _matches(r: Dict) -> bool:
            if source_ids and r["id"] in source_ids:
                return True
            if not source_ids:
                ok = True
                if kind_filter and r.get("kind") != kind_filter:
                    ok = False
                if name_contains and name_contains.lower() not in str(r.get("name", "")).lower():
                    ok = False
                if target_contains and target_contains.lower() not in str(r.get("target", "")).lower():
                    ok = False
                return ok
            return False
        before = len(_memory_sources)
        _memory_sources[:] = [r for r in _memory_sources if not _matches(r)]
        return before - len(_memory_sources)

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
        published_at: Optional[int] = None,
        item_titles: Optional[List[str]] = None,
    ) -> int:
        _ensure_init()
        ts = int(time.time())
        ev_json = json.dumps(evidence_urls, ensure_ascii=False)
        titles_json = json.dumps(item_titles or [], ensure_ascii=False)
        # Compute trend_score: +1 per other signal with similar theme in last 7 days
        trend = self._compute_trend_score(theme, ts)
        # M4.3 — auto-classify content type from URL + theme + excerpt
        from .content_type import classify_content_type
        from .language import detect_language
        cat, _, _ = classify_content_type(
            evidence_urls[0] if evidence_urls else "",
            theme, excerpt,
        )
        # M4.4 — detect language of theme+excerpt
        lang, _ = detect_language(f"{theme} {excerpt}")
        if _db_path:
            with _conn() as c:
                cur = c.execute(
                    "INSERT INTO signals(source_id,source_kind,theme,score,excerpt,"
                    "evidence_json,suggested_topic,trend_score,published_at,item_titles_json,content_type,language,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (source_id, source_kind, theme, score, excerpt, ev_json, suggested_topic, trend, published_at, titles_json, cat, lang, ts),
                )
                return int(cur.lastrowid)
        new_id = max([s["id"] for s in _memory_signals], default=0) + 1
        _memory_signals.append({
            "id": new_id, "source_id": source_id, "source_kind": source_kind,
            "theme": theme, "score": score, "excerpt": excerpt,
            "evidence_json": ev_json, "suggested_topic": suggested_topic,
            "feedback": None, "promoted_run_id": None,
            "trend_score": trend, "published_at": published_at,
            "item_titles_json": titles_json, "content_type": cat,
            "language": lang, "translated_theme": None, "translated_excerpt": None,
            "created_at": ts,
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

    def list(
        self,
        limit: int = 100,
        min_score: float = 0.0,
        search: Optional[str] = None,
    ) -> List[Dict]:
        """List signals filtered by score, optionally fuzzy-matched against
        theme/excerpt/suggested_topic.

        `search`: case-insensitive substring match. LIKE-based — good enough
        for <5k signals. Upgrade to SQLite FTS5 (virtual table + MATCH) when
        the dataset hits that scale.
        """
        _ensure_init()
        like = f"%{search.lower()}%" if search else None
        if _db_path:
            with _conn() as c:
                if like:
                    rows = c.execute(
                        "SELECT id,source_id,source_kind,theme,score,excerpt,evidence_json,"
                        "suggested_topic,feedback,promoted_run_id,trend_score,published_at,analysis_json,item_titles_json,content_type,language,translated_theme,translated_excerpt,created_at "
                        "FROM signals WHERE score>=? AND ("
                        " LOWER(theme) LIKE ? OR LOWER(excerpt) LIKE ? OR LOWER(suggested_topic) LIKE ?"
                        ") ORDER BY trend_score DESC, score DESC, created_at DESC LIMIT ?",
                        (min_score, like, like, like, limit),
                    ).fetchall()
                else:
                    rows = c.execute(
                        "SELECT id,source_id,source_kind,theme,score,excerpt,evidence_json,"
                        "suggested_topic,feedback,promoted_run_id,trend_score,published_at,analysis_json,item_titles_json,content_type,language,translated_theme,translated_excerpt,created_at "
                        "FROM signals WHERE score>=? "
                        "ORDER BY trend_score DESC, score DESC, created_at DESC LIMIT ?",
                        (min_score, limit),
                    ).fetchall()
                return [_signal_row_to_dict(dict(r)) for r in rows]
        # In-memory fallback
        rows = [r for r in _memory_signals if r["score"] >= min_score]
        if like:
            needle = search.lower()
            rows = [
                r for r in rows
                if needle in (r.get("theme", "") or "").lower()
                or needle in (r.get("excerpt", "") or "").lower()
                or needle in (r.get("suggested_topic", "") or "").lower()
            ]
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
                    "suggested_topic,feedback,promoted_run_id,trend_score,published_at,analysis_json,item_titles_json,content_type,language,translated_theme,translated_excerpt,created_at "
                    "FROM signals WHERE id=?", (signal_id,),
                ).fetchone()
                return _signal_row_to_dict(dict(row)) if row else None
        for r in _memory_signals:
            if r["id"] == signal_id:
                return _signal_row_to_dict(dict(r))
        return None

    def list_promoted(self, limit: int = 50) -> List[Dict]:
        """List signals that were promoted to a workflow run, newest first.

        Used by the dashboard "Promociones" log so the founder can see which
        signals turned into runs, when, and follow the link back to either
        the signal or the run.
        """
        _ensure_init()
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT id,source_id,source_kind,theme,score,excerpt,evidence_json,"
                    "suggested_topic,feedback,promoted_run_id,trend_score,published_at,analysis_json,item_titles_json,content_type,language,translated_theme,translated_excerpt,created_at "
                    "FROM signals WHERE promoted_run_id IS NOT NULL "
                    "ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [_signal_row_to_dict(dict(r)) for r in rows]
        rows = [r for r in _memory_signals if r.get("promoted_run_id")]
        rows = sorted(rows, key=lambda r: r.get("created_at", 0), reverse=True)[:limit]
        return [_signal_row_to_dict(dict(r)) for r in rows]

    def update_content(
        self,
        signal_id: int,
        *,
        theme: Optional[str] = None,
        excerpt: Optional[str] = None,
        item_titles: Optional[List[str]] = None,
    ) -> None:
        """M3.17: enrich a signal in-place with content scraped from its
        evidence URLs (og:title, og:description). Used by /signals/{id}/enrich.

        Only updates the fields that are provided (non-None).
        """
        _ensure_init()
        if _db_path:
            with _conn() as c:
                sets: List[str] = []
                params: List = []
                if theme is not None:
                    sets.append("theme=?")
                    params.append(theme[:240])
                if excerpt is not None:
                    sets.append("excerpt=?")
                    params.append(excerpt[:2000])
                if item_titles is not None:
                    sets.append("item_titles_json=?")
                    params.append(json.dumps(item_titles, ensure_ascii=False))
                if not sets:
                    return
                params.append(signal_id)
                c.execute(
                    f"UPDATE signals SET {', '.join(sets)} WHERE id=?",
                    tuple(params),
                )
            return
        for r in _memory_signals:
            if r["id"] == signal_id:
                if theme is not None:
                    r["theme"] = theme[:240]
                if excerpt is not None:
                    r["excerpt"] = excerpt[:2000]
                if item_titles is not None:
                    r["item_titles_json"] = json.dumps(item_titles, ensure_ascii=False)
                return

    def set_translation(
        self,
        signal_id: int,
        translated_theme: str,
        translated_excerpt: str,
        original_language: str = "en",
    ) -> None:
        """M4.4 — persist the LLM-generated Spanish translation."""
        _ensure_init()
        if _db_path:
            with _conn() as c:
                c.execute(
                    "UPDATE signals SET translated_theme=?, translated_excerpt=?, language=? "
                    "WHERE id=?",
                    (translated_theme[:240], translated_excerpt[:2000], original_language, signal_id),
                )
            return
        for r in _memory_signals:
            if r["id"] == signal_id:
                r["translated_theme"] = translated_theme[:240]
                r["translated_excerpt"] = translated_excerpt[:2000]
                r["language"] = original_language
                return

    def set_analysis(self, signal_id: int, analysis: Optional[Dict]) -> None:
        """Persist a JSON blob with the IdeaAnalyzer output (M3.5).

        Pass None to clear an existing analysis (e.g. user wants to re-run).
        """
        _ensure_init()
        raw = json.dumps(analysis, ensure_ascii=False) if analysis is not None else None
        if _db_path:
            with _conn() as c:
                c.execute("UPDATE signals SET analysis_json=? WHERE id=?", (raw, signal_id))
        else:
            for r in _memory_signals:
                if r["id"] == signal_id:
                    r["analysis_json"] = raw
                    return

    def cleanup_mocks(self) -> int:
        """Remove legacy mock-mode and placeholder signals.

        Targets ANY of:
          - theme like "Mock signal from %"          (mock-mode v1)
          - suggested_topic like "Mock topic ..."    (mock-mode v1)
          - excerpt like "Detected pattern across %" (genérico, no informativo)
          - theme like "Tema recurrente en %"        (fallback genérico)
          - theme like "Item de %"                   (fallback single-item)

        These are placeholders that don't help the founder decide.
        Real signals (with concrete item titles) are preserved.
        """
        _ensure_init()
        patterns = [
            ("theme LIKE ?", "Mock signal from %"),
            ("theme LIKE ?", "Mock single-source signal from %"),
            ("suggested_topic LIKE ?", "Mock topic derived from %"),
            ("excerpt LIKE ?", "Detected pattern across %"),
            ("excerpt LIKE ?", "Single item: %"),
            ("theme LIKE ?", "Tema recurrente en %"),
            ("theme LIKE ?", "Item de %"),
            # M3.18 — SPA fallbacks (x.com, instagram, etc. sin JS)
            ("theme LIKE ?", "JavaScript is not available%"),
            ("theme LIKE ?", "We've detected that JavaScript%"),
            ("theme LIKE ?", "Please enable JavaScript%"),
            ("excerpt LIKE ?", "JavaScript is not available%"),
            ("excerpt LIKE ?", "We've detected that JavaScript%"),
            ("theme LIKE ?", "Log in to Instagram%"),
            ("theme LIKE ?", "Log into Facebook%"),
            ("theme LIKE ?", "Instagram"),  # exacto — la home
            ("theme LIKE ?", "Login • Instagram%"),
            # M3.18b — titles de homepage genéricos (no son ideas)
            ("theme LIKE ?", "TikTok - Make Your Day"),
            ("theme LIKE ?", "TikTok"),
            ("theme LIKE ?", "Launch Meeting - Zoom"),
            ("theme LIKE ?", "Zoom"),
            ("theme LIKE ?", "Coming Soon"),
            ("theme LIKE ?", "Page not found%"),
            ("theme LIKE ?", "404%"),
            ("theme LIKE ?", "Page Not Found%"),
            ("theme LIKE ?", "Access denied%"),
            ("theme LIKE ?", "Sign in - Google%"),
            ("theme LIKE ?", "Sign In%"),
            ("theme LIKE ?", "Iniciar sesión%"),
            ("theme LIKE ?", "Redirecting%"),
            ("theme LIKE ?", "Loading%"),
            # M4.2 — descripciones corporativas (founder feedback: "Asiservy
            # — Alimentos del Mar con Propósito" pasó como idea pero es la
            # home de la empresa, no una idea)
            ("excerpt LIKE ?", "%Empresa líder en%"),
            ("excerpt LIKE ?", "%empresa lider en%"),
            ("excerpt LIKE ?", "%trazabilidad blockchain%"),
            ("excerpt LIKE ?", "%certificaciones globales%"),
            ("excerpt LIKE ?", "%años de experiencia%"),
            ("excerpt LIKE ?", "%anos de experiencia%"),
            ("excerpt LIKE ?", "%Nuestra misión%"),
            ("excerpt LIKE ?", "%nuestra mision%"),
            ("theme LIKE ?", "%Acerca de%"),
            ("theme LIKE ?", "%About Us%"),
            ("theme LIKE ?", "%Quiénes Somos%"),
            ("theme LIKE ?", "%Quienes Somos%"),
            ("theme LIKE ?", "%Sobre Nosotros%"),
            # M4.2b — más patterns observados en BD real del founder
            ("excerpt LIKE ?", "%Procesamiento y exportacion%"),
            ("excerpt LIKE ?", "%procesamos y exportamos%"),
            ("excerpt LIKE ?", "%Nosotros Negocios%"),
            ("excerpt LIKE ?", "%Del Mar al Mundo%"),
            ("excerpt LIKE ?", "%alimentos del mar%"),
            ("theme LIKE ?", "Asiservy%"),
            ("theme LIKE ?", "ASISERVY%"),
            ("theme LIKE ?", "App Asiservy%"),
            # Zoom join links genéricos
            ("theme LIKE ?", "Join our Cloud HD Video Meeting%"),
            ("theme LIKE ?", "Video Conferencing, Web Conferencing%"),
            ("theme LIKE ?", "Google Maps%"),
            ("theme LIKE ?", "Google Photos%"),
        ]
        if _db_path:
            with _conn() as c:
                where = " OR ".join(p[0] for p in patterns)
                params = tuple(p[1] for p in patterns)
                cur = c.execute(f"DELETE FROM signals WHERE {where}", params)
                return int(cur.rowcount or 0)
        before = len(_memory_signals)
        def _is_mock(r: Dict) -> bool:
            theme = str(r.get("theme", ""))
            topic = str(r.get("suggested_topic", ""))
            excerpt = str(r.get("excerpt", ""))
            # M4.2 corporate descriptions
            blob = f"{theme} {excerpt}".lower()
            corporate_signals = (
                "empresa líder en", "empresa lider en",
                "trazabilidad blockchain",
                "certificaciones globales",
                "años de experiencia", "anos de experiencia",
                "nuestra misión", "nuestra mision",
                "nuestra visión", "nuestra vision",
                "fundada en", "founded in",
                "quiénes somos", "quienes somos",
                "sobre nosotros", "acerca de nosotros",
                "about us",
            )
            corporate_hits = sum(1 for s in corporate_signals if s in blob)
            is_corporate = corporate_hits >= 2

            # M3.18 SPA fallbacks + homepage titles genéricos
            generic_titles = {
                "Instagram", "TikTok - Make Your Day", "TikTok",
                "Launch Meeting - Zoom", "Zoom", "Coming Soon",
            }
            spa = (
                theme.startswith("JavaScript is not available")
                or theme.startswith("We've detected that JavaScript")
                or theme.startswith("Please enable JavaScript")
                or excerpt.startswith("JavaScript is not available")
                or excerpt.startswith("We've detected that JavaScript")
                or theme.startswith("Log in to Instagram")
                or theme.startswith("Log into Facebook")
                or theme.startswith("Login • Instagram")
                or theme.startswith("Page not found")
                or theme.startswith("Page Not Found")
                or theme.startswith("404")
                or theme.startswith("Access denied")
                or theme.startswith("Sign in - Google")
                or theme.startswith("Sign In")
                or theme.startswith("Iniciar sesión")
                or theme.startswith("Redirecting")
                or theme.startswith("Loading")
                or theme in generic_titles
                or is_corporate
                or theme.startswith("Asiservy")
                or theme.startswith("ASISERVY")
                or theme.startswith("App Asiservy")
                or theme.startswith("Join our Cloud HD Video Meeting")
                or theme.startswith("Video Conferencing")
                or theme.startswith("Google Maps")
                or "Procesamiento y exportacion" in excerpt
                or "procesamos y exportamos" in excerpt
                or "Del Mar al Mundo" in excerpt
            )
            return (
                theme.startswith("Mock signal from ")
                or theme.startswith("Mock single-source signal from ")
                or topic.startswith("Mock topic derived from ")
                or excerpt.startswith("Detected pattern across ")
                or excerpt.startswith("Single item: ")
                or theme.startswith("Tema recurrente en ")
                or theme.startswith("Item de ")
                or spa
            )
        _memory_signals[:] = [r for r in _memory_signals if not _is_mock(r)]
        return before - len(_memory_signals)

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

    def delete_bulk(
        self,
        content_type: Optional[str] = None,
        source_kind: Optional[str] = None,
        source_id: Optional[int] = None,
        keep_promoted: bool = True,
        keep_feedback: bool = True,
    ) -> int:
        """M4.6b — Borrado masivo de señales por content_type Y/O fuente.

        Generaliza delete_by_content_type para aceptar también filtros por
        source_kind ("rss", "url", "hn"...) y source_id (fuente puntual).
        Al menos uno de los tres filtros debe ser no-None. Si se pasan
        varios, se combinan con AND (intersección).

        Por defecto preserva promovidas y con feedback (igual que el método
        anterior).

        Returns:
            count of deleted rows
        """
        if content_type is None and source_kind is None and source_id is None:
            raise ValueError("delete_bulk requires at least one filter")
        _ensure_init()

        if _db_path:
            with _conn() as c:
                where: list = []
                params: list = []
                if content_type is not None:
                    if content_type == "unknown":
                        where.append("(content_type IS NULL OR content_type = 'unknown' OR content_type = '')")
                    else:
                        where.append("content_type = ?")
                        params.append(content_type)
                if source_kind is not None:
                    where.append("source_kind = ?")
                    params.append(source_kind)
                if source_id is not None:
                    where.append("source_id = ?")
                    params.append(source_id)
                if keep_promoted:
                    where.append("promoted_run_id IS NULL")
                if keep_feedback:
                    where.append("feedback IS NULL")
                sql = "DELETE FROM signals WHERE " + " AND ".join(where)
                cur = c.execute(sql, tuple(params))
                return int(cur.rowcount or 0)
        # In-memory fallback
        before = len(_memory_signals)

        def matches(r: Dict) -> bool:
            if content_type is not None:
                ct = r.get("content_type")
                if content_type == "unknown":
                    if ct not in (None, "", "unknown"):
                        return False
                elif ct != content_type:
                    return False
            if source_kind is not None and r.get("source_kind") != source_kind:
                return False
            if source_id is not None and r.get("source_id") != source_id:
                return False
            if keep_promoted and r.get("promoted_run_id"):
                return False
            if keep_feedback and r.get("feedback"):
                return False
            return True

        _memory_signals[:] = [r for r in _memory_signals if not matches(r)]
        return before - len(_memory_signals)

    def delete_by_content_type(
        self,
        content_type: str,
        keep_promoted: bool = True,
        keep_feedback: bool = True,
    ) -> int:
        """M4.6 — Borra todas las señales cuyo content_type coincida.

        Compat: delega en delete_bulk (M4.6b) para no romper callers.
        Founder request: "debe existir la opción de eliminar las noticias por
        tipo noticia, blog, estudio, etc."
        """
        return self.delete_bulk(
            content_type=content_type,
            keep_promoted=keep_promoted,
            keep_feedback=keep_feedback,
        )

    def niche_opportunities(
        self,
        min_parent_size: int = 5,
        max_niche_size: int = 3,
        top_parents: int = 10,
    ) -> List[Dict]:
        """M4.15 — Niche-en-gigante detector (heurístico Phase 1).

        Founder del audio: "recoger las migajas de donde están los gigantes —
        pero recoger migajas es demasiado grande para nuestra realidad".

        Heurística: agrupa todas las señales por su "parent market" (primeras
        2 palabras significativas del suggested_topic). Dentro de cada
        gigante, identifica sub-niches (suggested_topic completo) con poca
        actividad pero que pertenecen al mismo mercado padre.

        Las micro-niches representan oportunidades sub-exploradas dentro de
        verticales grandes — donde los gigantes no se molestan en competir.

        Args:
            min_parent_size: mínimo de señales totales en el parent para que
                cuente como "gigante". Default 5.
            max_niche_size: máximo de señales en un sub-niche para que se
                considere "sub-explorado". Default 3.
            top_parents: cuántos parents (gigantes) retornar como máximo.
                Default 10, ordenados por tamaño desc.

        Returns:
            Lista [{ parent_market: str, parent_size: int,
                    leader_niche: {topic, signals, sample_themes},
                    underexplored_niches: [{topic, signals, sample_themes}, ...],
                    opportunity_count: int }]
        """
        import re as _re
        _ensure_init()
        rows = self.list(limit=10_000, min_score=0.0)

        # Stop-words típicos en suggested_topic que no aportan al "parent market"
        STOP = {
            "para", "en", "con", "de", "del", "la", "el", "los", "las",
            "y", "o", "u", "a", "ai", "ia", "saas", "automática",
            "automatica", "automatizada", "para pymes", "for", "with",
            "to", "and", "or", "based", "powered",
        }
        # Países que vamos a ignorar para evitar que se vuelvan el parent
        COUNTRIES = {
            "ecuador", "méxico", "mexico", "colombia", "perú", "peru",
            "chile", "argentina", "brasil", "uruguay", "panamá", "panama",
            "costa rica", "españa", "espana", "usa", "us", "latam",
            "estados unidos", "estados", "unidos",
        }

        def parent_market_of(topic: str) -> str:
            """Extrae la primera palabra significativa como parent market.

            Decisión de diseño: usar SOLO la primera palabra (no bigrama) para
            que sub-niches distintos del mismo gigante agrupen juntos. Ej:
            "fintech para PYMEs" y "fintech para adultos mayores" comparten el
            parent "fintech" — exactamente lo que el founder pide cuando habla
            de "migajas del gigante fintech".
            """
            if not topic:
                return ""
            cleaned = _re.sub(r"[^\w\s]", " ", topic.lower()).strip()
            tokens = [t for t in cleaned.split() if t and t not in STOP]
            # Quitar países del inicio
            while tokens and tokens[0] in COUNTRIES:
                tokens = tokens[1:]
            if not tokens:
                return ""
            return tokens[0][:40]

        # Index: parent_market → { sub_topic → list[signal_row] }
        from collections import defaultdict
        parents: Dict[str, Dict[str, List[Dict]]] = defaultdict(lambda: defaultdict(list))
        for r in rows:
            topic = (r.get("suggested_topic") or r.get("theme") or "").strip()
            parent = parent_market_of(topic)
            if not parent:
                continue
            # sub-niche = el topic completo (sin truncar) para preservar matiz
            sub = topic.lower().strip()[:80]
            if not sub:
                continue
            parents[parent][sub].append(r)

        results: List[Dict] = []
        for parent, subs in parents.items():
            total = sum(len(sigs) for sigs in subs.values())
            if total < min_parent_size:
                continue  # no es un "gigante" todavía
            if len(subs) < 2:
                continue  # 1 solo sub-niche, no hay dispersión real

            # Identificar leader_niche (el sub con más signals) y los under-explored
            ordered = sorted(subs.items(), key=lambda kv: len(kv[1]), reverse=True)
            leader_topic, leader_sigs = ordered[0]
            leader = {
                "topic": leader_topic,
                "signals": len(leader_sigs),
                "sample_themes": [s.get("theme") or "" for s in leader_sigs[:3]],
            }
            underexplored = []
            for sub_topic, sub_sigs in ordered[1:]:
                n = len(sub_sigs)
                if n > max_niche_size:
                    continue  # ya no es "sub-explorado"
                underexplored.append({
                    "topic": sub_topic,
                    "signals": n,
                    "sample_themes": [s.get("theme") or "" for s in sub_sigs[:3]],
                })
                if len(underexplored) >= 5:
                    break  # cap por visualización

            if not underexplored:
                continue  # no hay niches sub-explorados en este gigante

            results.append({
                "parent_market": parent,
                "parent_size": total,
                "leader_niche": leader,
                "underexplored_niches": underexplored,
                "opportunity_count": len(underexplored),
            })

        # Ordenar por opportunity_count desc, luego por parent_size desc
        results.sort(key=lambda r: (r["opportunity_count"], r["parent_size"]), reverse=True)
        return results[:top_parents]

    def cross_country_gaps(
        self,
        min_validation_signals: int = 2,
        min_validation_feedback: int = 1,
        target_countries: Optional[List[str]] = None,
    ) -> List[Dict]:
        """M4.11 — Detector de huecos geográficos para first-mover advantage.

        Founder del audio: "Si algo se está desarrollando en un país porque
        se cumplió A,B,C y en otro sabes que inevitablemente va a pasar… si
        llegas first-mover ahí, eventualmente tienes posibilidades de
        poderla reventar."

        Algoritmo:
        1. Agrupa signals por embedding cluster (usa preferences.recluster
           si está computado, o un hash-bucket fallback como heurística).
        2. Por cada cluster, extrae los `country_focus` de cada signal
           (idea_analyzer ya los rellena desde M3.11).
        3. Detecta clusters que están "validados" en ≥1 país: tienen al
           menos `min_validation_signals` signals con feedback up O score
           >= 0.7, todos del mismo país.
        4. Para cada cluster validado, lista los países objetivo
           (`target_countries`) donde NO existe ningún signal — son los
           "huecos" first-mover.

        Args:
            min_validation_signals: cuántas signals del mismo país hacen
                "validation". Default 2.
            min_validation_feedback: cuántas de esas signals deben tener
                feedback="up" para considerar realmente validado por el
                founder. Default 1 (al menos UN 👍 explícito).
            target_countries: lista de países a evaluar como "huecos". Si
                None, usa el default LATAM_DEFAULTS.

        Returns:
            Lista de dicts {
                idea_summary: str,
                cluster_size: int,
                validated_in: [{country, signals, ups, downs, sample_themes}],
                missing_in: [country, ...],
                opportunity_score: float (0-1, más alto = más oportunidad),
            }
        """
        _ensure_init()
        LATAM_DEFAULTS = [
            "Ecuador", "México", "Colombia", "Perú", "Chile",
            "Argentina", "Brasil", "Uruguay", "Costa Rica", "Panamá",
            "España", "Estados Unidos",
        ]
        target = target_countries or LATAM_DEFAULTS
        # Normalizar para matching case-insensitive
        target_norm = {c.lower(): c for c in target}

        rows = self.list(limit=10_000, min_score=0.0)

        # Indexar por (suggested_topic, theme_prefix) como cluster heurístico
        # cheap (sin tener que cargar embeddings). En M5 esto se reemplaza
        # con clustering vectorial real.
        from collections import defaultdict
        clusters: Dict[str, List[Dict]] = defaultdict(list)
        for r in rows:
            # cluster key: primero suggested_topic (que es la idea cleaneada),
            # si está vacío, primeros 40 chars del theme
            topic = (r.get("suggested_topic") or r.get("theme") or "").lower().strip()
            key = topic[:60]  # tolera variaciones cortas
            if not key:
                continue
            clusters[key].append(r)

        results: List[Dict] = []
        for cluster_key, signals in clusters.items():
            if len(signals) < 2:
                continue  # un solo signal no hace cluster

            # Extraer country por signal del analysis_json
            by_country: Dict[str, Dict] = defaultdict(lambda: {
                "signals": 0, "ups": 0, "downs": 0,
                "themes": [], "best_score": 0.0,
            })
            for s in signals:
                analysis = s.get("analysis") or {}
                country = (analysis.get("country_focus") or "").strip()
                if not country:
                    continue
                # Normalizar abreviaciones comunes
                norm = country.lower()
                if "ec" == norm or "ecuad" in norm:
                    country = "Ecuador"
                elif "mx" == norm or "méxico" in norm or "mexico" in norm:
                    country = "México"
                elif "co" == norm or "colombia" in norm:
                    country = "Colombia"
                elif "us" == norm or "usa" == norm or "united" in norm or "estados unidos" in norm:
                    country = "Estados Unidos"
                elif "latam" in norm:
                    # señales pan-LATAM no cuentan como validación específica
                    continue
                bucket = by_country[country]
                bucket["signals"] += 1
                bucket["best_score"] = max(bucket["best_score"], float(s.get("score") or 0))
                if s.get("feedback") == "up":
                    bucket["ups"] += 1
                if s.get("feedback") == "down":
                    bucket["downs"] += 1
                if len(bucket["themes"]) < 3:
                    bucket["themes"].append(s.get("theme") or "")

            # ¿Hay al menos un país validado?
            validated: List[Dict] = []
            for country, b in by_country.items():
                meets_count = b["signals"] >= min_validation_signals
                meets_feedback = b["ups"] >= min_validation_feedback
                # Alternativa: si hay muchos signals con score alto sin
                # feedback explícito, también considerar validado
                meets_score = b["signals"] >= min_validation_signals and b["best_score"] >= 0.7
                if meets_count and (meets_feedback or meets_score):
                    validated.append({
                        "country": country,
                        "signals": b["signals"],
                        "ups": b["ups"],
                        "downs": b["downs"],
                        "sample_themes": b["themes"],
                    })

            if not validated:
                continue

            # ¿Cuáles target_countries NO tienen ningún signal de este cluster?
            present_countries_norm = {c.lower() for c in by_country.keys()}
            missing = [
                display
                for norm, display in target_norm.items()
                if norm not in present_countries_norm
            ]
            if not missing:
                continue  # cluster ya cubierto en todos los target → no es gap

            # Sample theme para el resumen (primer signal del cluster)
            sample = signals[0]
            idea_summary = (
                (sample.get("analysis") or {}).get("idea_summary")
                or sample.get("suggested_topic")
                or sample.get("theme")
                or "(sin resumen)"
            )

            # opportunity_score: combina #países validados, fuerza del feedback,
            # y cantidad de huecos. Normalizado a [0, 1].
            n_val = len(validated)
            total_ups = sum(v["ups"] for v in validated)
            n_missing = len(missing)
            score = min(1.0, (n_val * 0.3 + total_ups * 0.2 + n_missing * 0.05))

            results.append({
                "idea_summary": idea_summary[:200],
                "cluster_size": len(signals),
                "validated_in": validated,
                "missing_in": missing,
                "opportunity_score": round(score, 3),
            })

        # Ordenar por opportunity_score desc
        results.sort(key=lambda r: r["opportunity_score"], reverse=True)
        return results

    def delete_by_ids(self, signal_ids: List[int]) -> int:
        """M4.9 — Borrado por lista explícita de IDs. No respeta promoted/
        feedback porque el founder está seleccionando manualmente — confiamos
        en su decisión.

        Returns count of deleted rows.
        """
        if not signal_ids:
            return 0
        _ensure_init()
        if _db_path:
            with _conn() as c:
                placeholders = ",".join("?" * len(signal_ids))
                cur = c.execute(
                    f"DELETE FROM signals WHERE id IN ({placeholders})",
                    tuple(signal_ids),
                )
                return int(cur.rowcount or 0)
        before = len(_memory_signals)
        wanted = set(signal_ids)
        _memory_signals[:] = [r for r in _memory_signals if r.get("id") not in wanted]
        return before - len(_memory_signals)

    def stats_by_content_type(self) -> Dict[str, int]:
        """M4.7 — Distribución de señales activas por content_type.

        Returns un dict {content_type → count} para cada uno de los 9 tipos
        del clasificador, más una entrada "total". Señales con content_type
        NULL o vacío se cuentan como "unknown" (legacy pre-M4.3).

        Útil para que el founder vea de un vistazo qué tipos dominan su feed
        y decida qué limpiar con delete-by-type (M4.6).
        """
        _ensure_init()
        TYPES = (
            "news", "blog", "research_paper", "tool_product",
            "course_tutorial", "video_podcast", "community", "corporate",
            "unknown",
        )
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT COALESCE(NULLIF(content_type, ''), 'unknown') AS ct, "
                    "COUNT(*) AS n "
                    "FROM signals GROUP BY ct"
                ).fetchall()
                buckets = {t: 0 for t in TYPES}
                for row in rows:
                    ct = row["ct"] if row["ct"] in TYPES else "unknown"
                    buckets[ct] = buckets.get(ct, 0) + int(row["n"])
                buckets["total"] = sum(buckets[t] for t in TYPES)
                return buckets
        # In-memory fallback
        buckets = {t: 0 for t in TYPES}
        for r in _memory_signals:
            ct = r.get("content_type") or "unknown"
            if ct not in TYPES:
                ct = "unknown"
            buckets[ct] += 1
        buckets["total"] = sum(buckets[t] for t in TYPES)
        return buckets

    def cleanup_stale(self, older_than_days: int = 30) -> int:
        """Delete signals older than `older_than_days` that have NO feedback AND
        were NOT promoted. Returns count of deleted rows.

        Rationale (ADR-014 follow-up): the cazador accumulates noise over time.
        After 30 days, a signal that nobody touched (no 👍, no 👎, no promote)
        is dead weight in the UI and skews the trend-score baseline. Promoted
        and feedback-tagged signals are preserved as audit history.
        """
        _ensure_init()
        cutoff_ts = int(time.time()) - older_than_days * 86_400
        if _db_path:
            with _conn() as c:
                cur = c.execute(
                    "DELETE FROM signals "
                    "WHERE created_at < ? "
                    "AND feedback IS NULL "
                    "AND promoted_run_id IS NULL",
                    (cutoff_ts,),
                )
                return int(cur.rowcount or 0)
        # In-memory fallback
        before = len(_memory_signals)
        _memory_signals[:] = [
            r for r in _memory_signals
            if not (
                r.get("created_at", 0) < cutoff_ts
                and r.get("feedback") is None
                and r.get("promoted_run_id") is None
            )
        ]
        return before - len(_memory_signals)

    def quality_by_source(self) -> List[Dict]:
        """
        Aggregate signal stats per source_id:
          { source_id, signals_total, signals_up, signals_down,
            signals_promoted, avg_score, quality_score }
        quality_score is a heuristic in [0,1]: rewards up-rate AND volume.
        """
        _ensure_init()
        rows: List[Dict] = []
        if _db_path:
            with _conn() as c:
                cur = c.execute(
                    "SELECT source_id, "
                    "COUNT(*) AS signals_total, "
                    "SUM(CASE WHEN feedback='up' THEN 1 ELSE 0 END) AS signals_up, "
                    "SUM(CASE WHEN feedback='down' THEN 1 ELSE 0 END) AS signals_down, "
                    "SUM(CASE WHEN promoted_run_id IS NOT NULL THEN 1 ELSE 0 END) AS signals_promoted, "
                    "AVG(score) AS avg_score "
                    "FROM signals "
                    "WHERE source_id IS NOT NULL "
                    "GROUP BY source_id"
                ).fetchall()
                rows = [dict(r) for r in cur]
        else:
            from collections import defaultdict
            grouped: Dict[int, Dict] = defaultdict(lambda: {
                "signals_total": 0, "signals_up": 0, "signals_down": 0,
                "signals_promoted": 0, "score_sum": 0.0,
            })
            for s in _memory_signals:
                if s.get("source_id") is None:
                    continue
                g = grouped[s["source_id"]]
                g["signals_total"] += 1
                if s.get("feedback") == "up":
                    g["signals_up"] += 1
                elif s.get("feedback") == "down":
                    g["signals_down"] += 1
                if s.get("promoted_run_id"):
                    g["signals_promoted"] += 1
                g["score_sum"] += s.get("score", 0)
            rows = [
                {
                    "source_id": sid,
                    "signals_total": g["signals_total"],
                    "signals_up": g["signals_up"],
                    "signals_down": g["signals_down"],
                    "signals_promoted": g["signals_promoted"],
                    "avg_score": (g["score_sum"] / g["signals_total"]) if g["signals_total"] else 0.0,
                }
                for sid, g in grouped.items()
            ]
        # Composite quality_score: up_rate (0..1) penalized by down votes,
        # boosted by promotion rate, dampened when volume is low.
        for r in rows:
            total = max(1, r["signals_total"])
            up_rate = (r["signals_up"] - r["signals_down"]) / total
            promote_rate = r["signals_promoted"] / total
            vol_factor = min(1.0, total / 10.0)  # full weight at >=10 signals
            r["quality_score"] = max(0.0, min(1.0, (0.6 * up_rate + 0.4 * promote_rate) * vol_factor + 0.05))
        return rows


def _signal_row_to_dict(row: Dict) -> Dict:
    """Parse the evidence_json column back into a list."""
    try:
        row["evidence_urls"] = json.loads(row.pop("evidence_json"))
    except Exception:  # noqa: BLE001
        row["evidence_urls"] = []
    # Parse the optional analysis_json blob (M3.5)
    raw_analysis = row.pop("analysis_json", None)
    if raw_analysis:
        try:
            row["analysis"] = json.loads(raw_analysis)
        except Exception:  # noqa: BLE001
            row["analysis"] = None
    else:
        row["analysis"] = None
    # Parse item_titles_json — parallel to evidence_urls (M3.6)
    raw_titles = row.pop("item_titles_json", None)
    if raw_titles:
        try:
            row["item_titles"] = json.loads(raw_titles)
        except Exception:  # noqa: BLE001
            row["item_titles"] = []
    else:
        row["item_titles"] = []
    # Ensure trend_score + published_at are always present (legacy rows may lack)
    row.setdefault("trend_score", 0)
    row.setdefault("published_at", None)
    # M4.3 — content_type may be NULL (legacy rows). Compute on the fly if missing.
    if not row.get("content_type"):
        try:
            from .content_type import classify_content_type
            urls = row.get("evidence_urls", [])
            cat, _, _ = classify_content_type(
                urls[0] if urls else "",
                row.get("theme", ""),
                row.get("excerpt", ""),
            )
            row["content_type"] = cat
        except Exception:  # noqa: BLE001
            row["content_type"] = "unknown"
    # M4.4 — language defaults + on-the-fly detection
    if not row.get("language"):
        try:
            from .language import detect_language
            lang, _ = detect_language(f"{row.get('theme','')} {row.get('excerpt','')}")
            row["language"] = lang
        except Exception:  # noqa: BLE001
            row["language"] = "unknown"
    row.setdefault("translated_theme", None)
    row.setdefault("translated_excerpt", None)
    return row


# ---------------------------------------------------------------------------
# Links log — bitácora de URLs extraídos de archivos + analizados por LLM (R30)
# ---------------------------------------------------------------------------


_memory_links: List[Dict] = []


class LinksLogStore:
    """Audit log of every URL the system ever saw (from file imports etc.)."""

    def add(self, url: str, source_file: Optional[str] = None) -> int:
        _ensure_init()
        ts = int(time.time())
        if _db_path:
            with _conn() as c:
                cur = c.execute(
                    "INSERT INTO links_log(url,source_file,status,created_at) "
                    "VALUES(?,?,'pending',?)",
                    (url, source_file, ts),
                )
                return int(cur.lastrowid)
        new_id = max([l["id"] for l in _memory_links], default=0) + 1
        _memory_links.append({
            "id": new_id, "url": url, "source_file": source_file,
            "status": "pending", "idea_summary": None, "sector": None, "area": None,
            "rejection_reason": None, "created_at": ts, "analyzed_at": None,
        })
        return new_id

    def update_analysis(
        self,
        link_id: int,
        status: str,
        idea_summary: Optional[str] = None,
        sector: Optional[str] = None,
        area: Optional[str] = None,
        rejection_reason: Optional[str] = None,
    ) -> None:
        _ensure_init()
        if status not in ("pending", "analyzed", "rejected", "error"):
            raise ValueError(f"invalid status: {status}")
        ts = int(time.time())
        if _db_path:
            with _conn() as c:
                c.execute(
                    "UPDATE links_log SET status=?, idea_summary=?, sector=?, area=?, "
                    "rejection_reason=?, analyzed_at=? WHERE id=?",
                    (status, idea_summary, sector, area, rejection_reason, ts, link_id),
                )
        else:
            for r in _memory_links:
                if r["id"] == link_id:
                    r.update({
                        "status": status, "idea_summary": idea_summary,
                        "sector": sector, "area": area,
                        "rejection_reason": rejection_reason, "analyzed_at": ts,
                    })
                    return

    def list(self, status: Optional[str] = None, limit: int = 200) -> List[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                if status:
                    rows = c.execute(
                        "SELECT id,url,source_file,status,idea_summary,sector,area,"
                        "rejection_reason,created_at,analyzed_at FROM links_log "
                        "WHERE status=? ORDER BY created_at DESC LIMIT ?",
                        (status, limit),
                    ).fetchall()
                else:
                    rows = c.execute(
                        "SELECT id,url,source_file,status,idea_summary,sector,area,"
                        "rejection_reason,created_at,analyzed_at FROM links_log "
                        "ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [dict(r) for r in rows]
        rows = _memory_links
        if status:
            rows = [r for r in rows if r["status"] == status]
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)[:limit]

    def stats(self) -> Dict[str, int]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT status, COUNT(*) AS n FROM links_log GROUP BY status"
                ).fetchall()
                return {r["status"]: int(r["n"]) for r in rows}
        from collections import Counter
        return dict(Counter(r["status"] for r in _memory_links))

    def get(self, link_id: int) -> Optional[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute(
                    "SELECT id,url,source_file,status,idea_summary,sector,area,"
                    "rejection_reason,created_at,analyzed_at FROM links_log WHERE id=?",
                    (link_id,),
                ).fetchone()
                return dict(row) if row else None
        for r in _memory_links:
            if r["id"] == link_id:
                return dict(r)
        return None

    def clear(self) -> None:
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM links_log")
        _memory_links.clear()


# M4.0 — connected accounts store (ADR-018)
# ---------------------------------------------------------------------------
class ConnectedAccountsStore:
    """Stores OBSERVED status of platform integrations, NOT credentials.

    Credentials live in env vars (YOUTUBE_API_KEY, etc.). This table only
    records "founder marked this platform as configured at <ts>".
    """

    def upsert(
        self,
        platform: str,
        status: str,
        *,
        oauth_required: bool = False,
        notes: Optional[str] = None,
    ) -> None:
        _ensure_init()
        ts = int(time.time()) if status == "configured" else None
        if _db_path:
            with _conn() as c:
                c.execute(
                    "INSERT INTO connected_accounts(platform,status,oauth_required,notes,configured_at) "
                    "VALUES(?,?,?,?,?) "
                    "ON CONFLICT(platform) DO UPDATE SET "
                    "  status=excluded.status, "
                    "  oauth_required=excluded.oauth_required, "
                    "  notes=excluded.notes, "
                    "  configured_at=COALESCE(excluded.configured_at, connected_accounts.configured_at)",
                    (platform, status, 1 if oauth_required else 0, notes, ts),
                )
            return
        for r in _memory_connected:
            if r["platform"] == platform:
                r["status"] = status
                r["oauth_required"] = 1 if oauth_required else 0
                r["notes"] = notes
                if ts is not None:
                    r["configured_at"] = ts
                return
        _memory_connected.append({
            "platform": platform, "status": status,
            "oauth_required": 1 if oauth_required else 0,
            "notes": notes, "configured_at": ts,
        })

    def get(self, platform: str) -> Optional[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute(
                    "SELECT platform,status,oauth_required,notes,configured_at "
                    "FROM connected_accounts WHERE platform=?",
                    (platform,),
                ).fetchone()
                return dict(row) if row else None
        for r in _memory_connected:
            if r["platform"] == platform:
                return dict(r)
        return None

    def list(self) -> List[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT platform,status,oauth_required,notes,configured_at "
                    "FROM connected_accounts ORDER BY platform"
                ).fetchall()
                return [dict(r) for r in rows]
        return sorted([dict(r) for r in _memory_connected], key=lambda r: r["platform"])

    def clear(self) -> None:
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM connected_accounts")
        _memory_connected.clear()


_memory_connected: List[Dict] = []


# ---------------------------------------------------------------------------
# M4.1 / ADR-019 — embeddings + autonomy stores
# ---------------------------------------------------------------------------
import struct as _struct


def _pack_vector(vec: List[float]) -> bytes:
    return _struct.pack(f"<{len(vec)}f", *vec)


def _unpack_vector(blob: bytes) -> List[float]:
    n = len(blob) // 4
    return list(_struct.unpack(f"<{n}f", blob))


_memory_embeddings: Dict[int, Dict] = {}
_memory_autonomy = {"level": "manual", "updated_at": int(time.time())}


class EmbeddingsStore:
    """Stores 384-dim embeddings per signal + cluster_id."""

    def upsert(
        self,
        signal_id: int,
        vector: List[float],
        cluster_id: int = -1,
        model_version: str = "fallback-1",
    ) -> None:
        _ensure_init()
        blob = _pack_vector(vector)
        ts = int(time.time())
        if _db_path:
            with _conn() as c:
                c.execute(
                    "INSERT INTO signal_embeddings(signal_id,vector_blob,cluster_id,model_version,created_at) "
                    "VALUES(?,?,?,?,?) "
                    "ON CONFLICT(signal_id) DO UPDATE SET "
                    "  vector_blob=excluded.vector_blob, "
                    "  cluster_id=excluded.cluster_id, "
                    "  model_version=excluded.model_version",
                    (signal_id, blob, cluster_id, model_version, ts),
                )
            return
        _memory_embeddings[signal_id] = {
            "signal_id": signal_id, "vector": vector,
            "cluster_id": cluster_id, "model_version": model_version,
            "created_at": ts,
        }

    def get_vector(self, signal_id: int) -> Optional[List[float]]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute(
                    "SELECT vector_blob FROM signal_embeddings WHERE signal_id=?",
                    (signal_id,),
                ).fetchone()
                return _unpack_vector(row["vector_blob"]) if row else None
        rec = _memory_embeddings.get(signal_id)
        return list(rec["vector"]) if rec else None

    def set_cluster(self, signal_id: int, cluster_id: int) -> None:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                c.execute(
                    "UPDATE signal_embeddings SET cluster_id=? WHERE signal_id=?",
                    (cluster_id, signal_id),
                )
            return
        if signal_id in _memory_embeddings:
            _memory_embeddings[signal_id]["cluster_id"] = cluster_id

    def list_all(self) -> List[Dict]:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                rows = c.execute(
                    "SELECT signal_id,vector_blob,cluster_id,model_version,created_at "
                    "FROM signal_embeddings"
                ).fetchall()
                return [
                    {
                        "signal_id": r["signal_id"],
                        "vector": _unpack_vector(r["vector_blob"]),
                        "cluster_id": r["cluster_id"],
                        "model_version": r["model_version"],
                        "created_at": r["created_at"],
                    }
                    for r in rows
                ]
        return [dict(r, vector=list(r["vector"])) for r in _memory_embeddings.values()]

    def get_by_signal_ids(self, signal_ids: List[int]) -> Dict[int, List[float]]:
        """Bulk fetch vectors for a set of signal IDs (used by scoring)."""
        _ensure_init()
        if not signal_ids:
            return {}
        if _db_path:
            with _conn() as c:
                placeholders = ",".join("?" for _ in signal_ids)
                rows = c.execute(
                    f"SELECT signal_id, vector_blob FROM signal_embeddings "
                    f"WHERE signal_id IN ({placeholders})",
                    tuple(signal_ids),
                ).fetchall()
                return {r["signal_id"]: _unpack_vector(r["vector_blob"]) for r in rows}
        return {
            sid: list(rec["vector"])
            for sid, rec in _memory_embeddings.items()
            if sid in signal_ids
        }

    def clear(self) -> None:
        if _db_path:
            with _conn() as c:
                c.execute("DELETE FROM signal_embeddings")
        _memory_embeddings.clear()


class AutonomyStore:
    """Single-row store for the cazador's autonomy level (M4.1)."""

    VALID_LEVELS = ("manual", "assisted", "autonomous_with_approval")

    def get_level(self) -> str:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute("SELECT level FROM autonomy WHERE id=1").fetchone()
                return row["level"] if row else "manual"
        return _memory_autonomy["level"]

    def set_level(self, level: str) -> None:
        if level not in self.VALID_LEVELS:
            raise ValueError(f"Invalid autonomy level: {level!r}")
        _ensure_init()
        ts = int(time.time())
        if _db_path:
            with _conn() as c:
                c.execute(
                    "UPDATE autonomy SET level=?, updated_at=? WHERE id=1",
                    (level, ts),
                )
            return
        _memory_autonomy["level"] = level
        _memory_autonomy["updated_at"] = ts

    def get_full(self) -> Dict:
        _ensure_init()
        if _db_path:
            with _conn() as c:
                row = c.execute(
                    "SELECT level, updated_at FROM autonomy WHERE id=1"
                ).fetchone()
                return dict(row) if row else {"level": "manual", "updated_at": 0}
        return dict(_memory_autonomy)

    def clear(self) -> None:
        if _db_path:
            with _conn() as c:
                c.execute("UPDATE autonomy SET level='manual' WHERE id=1")
        _memory_autonomy["level"] = "manual"
        _memory_autonomy["updated_at"] = int(time.time())


# Module-level singletons used by api.py
leads_store = LeadsStore()
runs_store = RunsStore()
auth_store = AuthStore()
sources_store = SourcesStore()
signals_store = SignalsStore()
links_log_store = LinksLogStore()
connected_accounts_store = ConnectedAccountsStore()
embeddings_store = EmbeddingsStore()
autonomy_store = AutonomyStore()


__all__ = [
    "ConnectedAccountsStore", "connected_accounts_store",
    "EmbeddingsStore", "embeddings_store",
    "AutonomyStore", "autonomy_store",
    "leads_store",
    "runs_store",
    "auth_store",
    "sources_store",
    "signals_store",
    "links_log_store",
    "LeadsStore",
    "RunsStore",
    "AuthStore",
    "SourcesStore",
    "SignalsStore",
    "LinksLogStore",
]
