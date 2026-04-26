"""
Incremental sync from local SQLite to Supabase Postgres.

Replaces the old "gzip + git push" workflow for getting data to the cloud.
Scrapers continue writing to local SQLite; this script pushes changes to Supabase.

Usage:
    python -m scrapers.sync_to_supabase
    # or from refresh.sh:
    python scrapers/sync_to_supabase.py

Env vars:
    SUPABASE_DATABASE_URL  — Postgres connection string (pooler, port 6543)
    DATABASE_URL           — Fallback if SUPABASE_DATABASE_URL not set
"""

import hashlib
import os
import sys
import signal
from datetime import datetime, date

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

_env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
try:
    from dotenv import load_dotenv
    load_dotenv(_env_file)
except ImportError:
    # Fallback: manually parse .env if python-dotenv not installed
    if os.path.isfile(_env_file):
        with open(_env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from scrapers.database import (
    get_session,
    Practice,
    Deal,
    PracticeChange,
    ZipScore,
    WatchedZip,
    DSOLocation,
    ADAHPIBenchmark,
    PESponsor,
    Platform,
    ZipOverview,
    ZipQualitativeIntel,
    PracticeIntel,
    PracticeSignal,
    ZipSignal,
    PracticeLocation,  # ULTRA-FIX dedup
)
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error
from scrapers.logger_config import get_logger

log = get_logger("sync_to_supabase")

# ---------------------------------------------------------------------------
# Fix 3: Graceful SIGINT/SIGTERM handler
# ---------------------------------------------------------------------------
# launchd sends SIGTERM on timeout; the user sends SIGINT via Ctrl-C.
# Without a handler an in-flight sync dies mid-batch, leaving Supabase tables
# in a partial state with no rollback path. We catch both signals, set a flag,
# and check it before each batch commit so we drain the current batch cleanly,
# write sync_metadata, and exit non-zero rather than leaving a half-written table.
_shutdown_requested = False


def _handle_shutdown(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True
    log.warning("Received signal %s — requesting graceful shutdown after current batch", signum)


signal.signal(signal.SIGINT, _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BATCH_SIZE = 2000
PG_STATEMENT_TIMEOUT_MS = int(os.environ.get("SUPABASE_STATEMENT_TIMEOUT_MS", "600000"))


def _set_statement_timeout(conn, *, local=False):
    """Raise Supabase's 2-minute default timeout for long sync/verify steps."""
    if not hasattr(conn, "exec_driver_sql"):
        # Unit-test fakes only implement execute(); skipping here keeps timeout
        # plumbing from being mistaken for row-level DML in resilience tests.
        return
    scope = "LOCAL " if local else ""
    conn.exec_driver_sql(f"SET {scope}statement_timeout = {PG_STATEMENT_TIMEOUT_MS}")

# Fix 2: Minimum row floors for full_replace tables.
# If SQLite returns fewer rows than this threshold the TRUNCATE is aborted.
# Floors are based on known data sizes (conservatively set to ~50% of expected).
# Set to 0 for tables that are allowed to be empty (pe_sponsors, platforms, etc.)
# or that grow from zero (practice_intel at bootstrap).
# RISK NOTE: if a legitimate reset/wipe of a table is needed (e.g., after a full
# re-scrape that intentionally deletes records), temporarily lower the floor or
# add a --force flag (not yet implemented).
MIN_ROWS_THRESHOLD = {
    "zip_scores":            200,   # 290 scored ZIPs expected
    "watched_zips":          200,   # 290 watched ZIPs expected
    "dso_locations":          50,   # 408 locations expected
    "ada_hpi_benchmarks":    500,   # 918 rows expected
    "zip_qualitative_intel":   0,   # grows over time; no floor — may be legitimately empty on a fresh install
    "practice_intel":          1,   # allowed to grow from zero; 1 ensures some data exists
    "platforms":              20,   # 140 live rows; floor catches catastrophic source loss. Fresh install must manually override.
    "pe_sponsors":            10,   # 40 live rows; floor catches catastrophic source loss. Fresh install must manually override.
    "zip_overviews":           5,   # 12 live rows; floor catches catastrophic source loss. Fresh install must manually override.
    "practice_signals":     1000,   # ~14k watched-ZIP practices expected; floor catches broken materialization.
    "zip_signals":            50,   # 290 watched ZIPs expected; floor catches broken materialization.
    "practice_locations":    1000,  # ~5700 locations in watched ZIPs; floor catches broken dedup run.
}

# Tables and their sync strategy
# "incremental_updated_at" — WHERE updated_at > last_sync_ts
# "incremental_id"         — WHERE id > last_max_id
# "full_replace"           — TRUNCATE + INSERT
SYNC_CONFIG = [
    # Practices: only sync rows in watched ZIPs (Chicagoland + Boston ≈ 14k rows)
    # Full 400k stays in local SQLite. This makes sync fast and keeps Supabase lean.
    {"table": "practices",        "model": Practice,        "strategy": "watched_zips_only", "conflict_col": "npi"},
    {"table": "deals",            "model": Deal,            "strategy": "incremental_updated_at", "conflict_col": "id"},
    {"table": "practice_changes", "model": PracticeChange,  "strategy": "incremental_id",         "conflict_col": "id", "filter_watched_zips": True},
    {"table": "zip_scores",       "model": ZipScore,        "strategy": "full_replace",           "conflict_col": None},
    {"table": "watched_zips",     "model": WatchedZip,      "strategy": "full_replace",           "conflict_col": None},
    {"table": "dso_locations",    "model": DSOLocation,     "strategy": "full_replace",           "conflict_col": None},
    {"table": "ada_hpi_benchmarks", "model": ADAHPIBenchmark, "strategy": "full_replace",         "conflict_col": None},
    {"table": "pe_sponsors",      "model": PESponsor,       "strategy": "full_replace",           "conflict_col": None},
    {"table": "platforms",        "model": Platform,        "strategy": "full_replace",           "conflict_col": None},
    {"table": "zip_overviews",    "model": ZipOverview,     "strategy": "full_replace",           "conflict_col": None},
    {"table": "zip_qualitative_intel", "model": ZipQualitativeIntel, "strategy": "full_replace", "conflict_col": None},
    # practice_intel and practice_signals have FK → practices.npi in Supabase.
    # TRUNCATE TABLE practices CASCADE wipes them both. They must be re-synced
    # every run. filter_watched_zips_npi=True trims any SQLite rows whose NPI is
    # not in Supabase practices (e.g., non-watched-ZIP rows from compute_signals)
    # to prevent FK violations that would abort the full_replace and leave 0 rows.
    {"table": "practice_intel",   "model": PracticeIntel,  "strategy": "full_replace", "conflict_col": None, "filter_watched_zips_npi": True},
    {"table": "practice_signals", "model": PracticeSignal, "strategy": "full_replace", "conflict_col": None, "filter_watched_zips_npi": True},
    {"table": "zip_signals",      "model": ZipSignal,      "strategy": "full_replace", "conflict_col": None},
    # practice_locations: additive dedup table (ULTRA-FIX dedup). full_replace is safe —
    # re-derived from practices on every dedup run. No FK deps on other Supabase tables.
    {"table": "practice_locations", "model": PracticeLocation, "strategy": "full_replace", "conflict_col": None},
]


# ---------------------------------------------------------------------------
# Postgres engine
# ---------------------------------------------------------------------------

def _get_pg_url():
    """Get the Postgres connection URL from environment."""
    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No Postgres URL found. Set SUPABASE_DATABASE_URL or DATABASE_URL."
        )
    return url


def _get_pg_engine():
    """Create a SQLAlchemy engine for the Supabase Postgres database.

    Connection hardening (added 2026-04-25 after debugging an abandoned
    Supabase backend that held `SELECT npi FROM practices` for 16+ minutes
    after the local Python process died, blocking every subsequent TRUNCATE):

    - `idle_in_transaction_session_timeout=300000` — Postgres kills any
      connection sitting idle inside a transaction for >5 min. Prevents a
      crashed local sync from leaving zombie locks on practices.
    - TCP keepalives (30s idle / 10s interval / 5 retries) — detect
      half-closed connections within ~80s instead of the OS default 2hr,
      so the backend gets cleaned up even if the local TCP socket vanishes
      without a FIN packet (NAT timeouts, laptop sleep, etc.).
    """
    url = _get_pg_url()
    engine = create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={
            "options": (
                f"-c statement_timeout={PG_STATEMENT_TIMEOUT_MS} "
                f"-c idle_in_transaction_session_timeout=300000"
            ),
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
        echo=False,
    )
    return engine


# ---------------------------------------------------------------------------
# sync_metadata table management
# ---------------------------------------------------------------------------

_SYNC_METADATA_DDL = """
CREATE TABLE IF NOT EXISTS sync_metadata (
    id SERIAL PRIMARY KEY,
    table_name TEXT UNIQUE NOT NULL,
    last_sync_at TIMESTAMP,
    last_sync_value TEXT,
    rows_synced INTEGER DEFAULT 0,
    sync_type TEXT,
    notes TEXT
)
"""

_PIPELINE_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_events (
    id SERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    event TEXT,
    status TEXT,
    summary TEXT,
    details JSONB
)
"""


def _ensure_sync_metadata(pg_engine):
    """Create the sync_metadata and pipeline_events tables if they don't exist."""
    with pg_engine.connect() as conn:
        conn.execute(text(_SYNC_METADATA_DDL))
        conn.execute(text(_PIPELINE_EVENTS_DDL))
        conn.commit()


def _get_sync_state(pg_engine, table_name):
    """Read the last sync state for a table. Returns dict or None."""
    with pg_engine.connect() as conn:
        result = conn.execute(
            text("SELECT last_sync_at, last_sync_value, rows_synced, sync_type "
                 "FROM sync_metadata WHERE table_name = :tn"),
            {"tn": table_name},
        ).fetchone()
    if result:
        return {
            "last_sync_at": result[0],
            "last_sync_value": result[1],
            "rows_synced": result[2],
            "sync_type": result[3],
        }
    return None


def _update_sync_state(pg_engine, table_name, rows_synced, sync_type, last_sync_value=None, notes=None):
    """Upsert sync_metadata for a table."""
    with pg_engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO sync_metadata (table_name, last_sync_at, last_sync_value, rows_synced, sync_type, notes)
                VALUES (:tn, :now, :lsv, :rs, :st, :notes)
                ON CONFLICT (table_name) DO UPDATE SET
                    last_sync_at = :now,
                    last_sync_value = :lsv,
                    rows_synced = :rs,
                    sync_type = :st,
                    notes = :notes
            """),
            {
                "tn": table_name,
                "now": datetime.now(),
                "lsv": last_sync_value,
                "rs": rows_synced,
                "st": sync_type,
                "notes": notes,
            },
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Model to dict conversion
# ---------------------------------------------------------------------------

def _model_to_dict(instance):
    """Convert a SQLAlchemy model instance to a plain dict, handling types."""
    mapper = inspect(type(instance))
    result = {}
    for col in mapper.columns:
        val = getattr(instance, col.key)
        # Convert date/datetime to string for safe serialization
        if isinstance(val, datetime):
            val = val.isoformat()
        elif isinstance(val, date):
            val = val.isoformat()
        result[col.key] = val
    return result


def _get_column_names(model_class):
    """Get all column names from a SQLAlchemy model class."""
    mapper = inspect(model_class)
    return [col.key for col in mapper.columns]


# ---------------------------------------------------------------------------
# SQL generation for upserts
# ---------------------------------------------------------------------------

def _build_upsert_sql(table_name, columns, conflict_col):
    """Build an INSERT ... ON CONFLICT DO UPDATE statement for Postgres."""
    col_list = ", ".join(columns)
    param_list = ", ".join(f":{c}" for c in columns)
    update_cols = [c for c in columns if c != conflict_col]
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    sql = (
        f"INSERT INTO {table_name} ({col_list}) "
        f"VALUES ({param_list}) "
        f"ON CONFLICT ({conflict_col}) DO UPDATE SET {update_set}"
    )
    return sql


def _build_insert_sql(table_name, columns):
    """Build a plain INSERT statement (no conflict handling)."""
    col_list = ", ".join(columns)
    param_list = ", ".join(f":{c}" for c in columns)
    return f"INSERT INTO {table_name} ({col_list}) VALUES ({param_list})"


# ---------------------------------------------------------------------------
# Ensure Postgres tables exist
# ---------------------------------------------------------------------------

def _ensure_pg_tables(pg_engine):
    """Create all tables in Postgres using SQLAlchemy metadata.

    This uses the same Base declarative models as SQLite, so tables are
    structurally identical.
    """
    from scrapers.database import Base
    Base.metadata.create_all(pg_engine)
    log.info("Ensured all tables exist in Postgres")


# ---------------------------------------------------------------------------
# Sync strategies
# ---------------------------------------------------------------------------

def _sync_incremental_updated_at(sqlite_session, pg_engine, config):
    """Sync rows where updated_at > last sync timestamp."""
    table_name = config["table"]
    model = config["model"]
    conflict_col = config["conflict_col"]
    columns = _get_column_names(model)

    # Get last sync state
    state = _get_sync_state(pg_engine, table_name)
    if state and state["last_sync_value"]:
        last_ts = state["last_sync_value"]
        log.info("[%s] Incremental sync since %s", table_name, last_ts)
        # SQLAlchemy stores SQLite DateTime as space-separated ISO ('YYYY-MM-DD HH:MM:SS'),
        # but we persist the watermark via datetime.isoformat() which emits a 'T' separator.
        # SQLite does lexicographic TEXT comparison, and 'T' > ' ', so a string-vs-string
        # filter silently drops every row newer than the stored watermark. Parse back to
        # datetime so SQLAlchemy's bind processor renders it in the on-disk format.
        if isinstance(last_ts, str):
            try:
                last_ts = datetime.fromisoformat(last_ts)
            except ValueError:
                log.warning("[%s] Could not parse watermark %r, using raw string", table_name, last_ts)
        rows = (
            sqlite_session.query(model)
            .filter(model.updated_at > last_ts)
            .order_by(model.updated_at.asc())
            .all()
        )
    else:
        log.info("[%s] First sync — fetching all rows", table_name)
        rows = sqlite_session.query(model).all()

    if not rows:
        log.info("[%s] No new rows to sync", table_name)
        return 0

    log.info("[%s] Syncing %d rows in batches of %d", table_name, len(rows), BATCH_SIZE)
    upsert_sql = _build_upsert_sql(table_name, columns, conflict_col)
    total_synced = 0

    # Per-row savepoints: deals has a secondary partial UNIQUE INDEX
    # (uix_deal_no_dup on platform_company+target_name+deal_date) that isn't
    # the ON CONFLICT target. A duplicate hitting that index raises
    # IntegrityError and, without a savepoint, aborts the whole transaction
    # — losing every queued row in the batch. begin_nested() scopes the
    # failure so we skip the dup and continue.
    total_skipped = 0
    # Watermark accounting (two lists, distinct purposes):
    #   synced_rows    — rows that actually committed (drives the "X synced" log)
    #   processed_rows — rows we successfully called execute() on, INCLUDING the
    #                    expected uix_deal_no_dup skips. These are "done" — Supabase
    #                    already holds an equivalent row, so we have to advance the
    #                    watermark past them, otherwise the next run re-fetches the
    #                    same window, gets the same dups, and the watermark is frozen
    #                    forever (the failure mode that produced the 54-day-stale
    #                    deals.last_sync_at and the misleading DATA FRESHNESS card).
    synced_rows: list = []
    processed_rows: list = []
    for i in range(0, len(rows), BATCH_SIZE):
        # Fix 3: honour shutdown request before each batch commit
        if _shutdown_requested:
            log.warning("[%s] Shutdown requested — stopping after %d/%d rows synced",
                        table_name, total_synced, len(rows))
            break

        batch = rows[i:i + BATCH_SIZE]
        dicts = [(r, _model_to_dict(r)) for r in batch]
        batch_synced = 0
        batch_skipped = 0
        with pg_engine.connect() as conn:
            _set_statement_timeout(conn, local=True)
            for r, d in dicts:
                sp = conn.begin_nested()
                try:
                    conn.execute(text(upsert_sql), d)
                    sp.commit()
                    batch_synced += 1
                    synced_rows.append(r)
                    processed_rows.append(r)
                except IntegrityError as e:
                    sp.rollback()
                    # Phase 1.2: narrow the exception scope. Only the known
                    # partial unique index uix_deal_no_dup is an expected dup;
                    # FK / NOT NULL / other constraint violations should not be
                    # silently swallowed — they indicate a real schema or data
                    # problem that must abort the batch visibly.
                    err_str = str(getattr(e, "orig", e))
                    if "uix_deal_no_dup" in err_str:
                        batch_skipped += 1
                        # Dup is "processed" — Supabase holds an equivalent row keyed
                        # on (platform_company, target_name, deal_date). Advancing the
                        # watermark past this row is the whole point: otherwise the
                        # next sync replays the same window and the watermark stalls.
                        processed_rows.append(r)
                        log.warning(
                            "[%s] id=%s skipped dup (uix_deal_no_dup): %s",
                            table_name, getattr(r, "id", "?"),
                            err_str.split("\n")[0][:200],
                        )
                    else:
                        log.error(
                            "[%s] id=%s UNEXPECTED IntegrityError — aborting batch: %s",
                            table_name, getattr(r, "id", "?"),
                            err_str.split("\n")[0][:400],
                        )
                        raise
            conn.commit()
        total_synced += batch_synced
        total_skipped += batch_skipped
        log.info("[%s] Batch %d-%d committed (%d synced, %d skipped; %d/%d)",
                 table_name, i, i + len(batch), batch_synced, batch_skipped,
                 total_synced, len(rows))
    if total_skipped:
        log.info("[%s] %d duplicates skipped via savepoint", table_name, total_skipped)

    # Watermark advances past every row we actually processed (committed OR
    # dup-skipped). On graceful shutdown that breaks the loop early, processed_rows
    # only contains rows from completed batches — never rows beyond the break.
    if _shutdown_requested and not processed_rows:
        log.info("[%s] No rows processed this run — leaving watermark unchanged", table_name)
        return 0

    processed_with_ts = [
        getattr(r, "updated_at") for r in processed_rows if getattr(r, "updated_at", None) is not None
    ]
    if not processed_with_ts:
        log.warning("[%s] No processed rows carry updated_at — skipping watermark update", table_name)
        return total_synced
    max_updated_at = max(processed_with_ts)
    last_val = max_updated_at.isoformat() if isinstance(max_updated_at, (datetime, date)) else str(max_updated_at)

    _update_sync_state(
        pg_engine, table_name,
        rows_synced=total_synced,
        sync_type="incremental_updated_at",
        last_sync_value=last_val,
        notes=f"Synced {total_synced} rows",
    )
    return total_synced


def _sync_incremental_id(sqlite_session, pg_engine, config):
    """Sync rows where id > last synced max id, plus recently updated rows."""
    table_name = config["table"]
    model = config["model"]
    conflict_col = config["conflict_col"]
    columns = _get_column_names(model)

    state = _get_sync_state(pg_engine, table_name)
    if state and state["last_sync_value"]:
        last_id = int(state["last_sync_value"])
        log.info("[%s] Incremental sync for id > %d", table_name, last_id)
        rows = (
            sqlite_session.query(model)
            .filter(model.id > last_id)
            .order_by(model.id.asc())
            .all()
        )
        # Also fetch rows updated since last sync (catches edits to existing rows)
        if hasattr(model, "updated_at") and state.get("last_sync_at"):
            last_sync_ts = state["last_sync_at"]
            # Same SQLite text-vs-datetime trap as _sync_incremental_updated_at.
            if isinstance(last_sync_ts, str):
                try:
                    last_sync_ts = datetime.fromisoformat(last_sync_ts)
                except ValueError:
                    log.warning("[%s] Could not parse watermark %r", table_name, last_sync_ts)
            updated_rows = (
                sqlite_session.query(model)
                .filter(model.updated_at > last_sync_ts)
                .filter(model.id <= last_id)
                .all()
            )
            if updated_rows:
                log.info("[%s] Found %d updated rows (id <= %d, updated since %s)",
                         table_name, len(updated_rows), last_id, last_sync_ts)
                # Merge: add updated rows that aren't already in the new-id set
                existing_ids = {r.id for r in rows}
                for r in updated_rows:
                    if r.id not in existing_ids:
                        rows.append(r)
    else:
        log.info("[%s] First sync — fetching all rows", table_name)
        rows = sqlite_session.query(model).all()

    # Filter to watched ZIPs if configured (e.g., practice_changes FK depends on practices)
    if config.get("filter_watched_zips") and rows:
        watched = sqlite_session.query(WatchedZip.zip_code).all()
        watched_zips = {z[0] for z in watched}
        # Get NPIs of practices in watched ZIPs
        watched_npis = {
            p[0] for p in sqlite_session.query(Practice.npi)
            .filter(Practice.zip.in_(watched_zips))
            .all()
        }
        before = len(rows)
        rows = [r for r in rows if getattr(r, "npi", None) in watched_npis]
        log.info("[%s] Filtered to watched ZIPs: %d → %d rows", table_name, before, len(rows))

    if not rows:
        log.info("[%s] No new rows to sync", table_name)
        return 0

    log.info("[%s] Syncing %d rows", table_name, len(rows))

    upsert_sql = _build_upsert_sql(table_name, columns, conflict_col)

    # Per-row savepoints: deals has a secondary partial UNIQUE INDEX
    # (uix_deal_no_dup on platform_company+target_name+deal_date) that isn't
    # the ON CONFLICT target. A duplicate hitting that index raises
    # IntegrityError and, without a savepoint, aborts the whole transaction
    # — losing every queued row. begin_nested() scopes the failure so we
    # skip the dup and continue with the rest.
    inserted = 0
    skipped = 0
    # Phase 1.1: track rows that actually committed so the watermark reflects
    # only them, not the full fetched batch. Otherwise a graceful shutdown
    # advances the watermark past rows we never sent.
    synced_rows: list = []
    # Fix 3: honour shutdown request — commit in bounded batches so a timeout
    # or signal never holds one long transaction across the entire changes set.
    for i in range(0, len(rows), BATCH_SIZE):
        if _shutdown_requested:
            log.warning("[%s] Shutdown requested — stopping at %d/%d rows",
                        table_name, inserted, len(rows))
            break

        batch = rows[i:i + BATCH_SIZE]
        batch_inserted = 0
        batch_skipped = 0
        with pg_engine.connect() as conn:
            _set_statement_timeout(conn, local=True)
            for r in batch:
                if _shutdown_requested:
                    log.warning("[%s] Shutdown requested mid-batch — stopping at %d/%d rows",
                                table_name, inserted, len(rows))
                    break
                d = _model_to_dict(r)
                sp = conn.begin_nested()
                try:
                    conn.execute(text(upsert_sql), d)
                    sp.commit()
                    inserted += 1
                    batch_inserted += 1
                    synced_rows.append(r)
                except IntegrityError as e:
                    sp.rollback()
                    # Phase 1.2: narrow the exception scope. practice_changes only
                    # has practice_changes_pkey as an expected duplicate path; any
                    # FK / NOT NULL / other constraint violation must surface, not
                    # be silently skipped.
                    err_str = str(getattr(e, "orig", e))
                    if "practice_changes_pkey" in err_str:
                        skipped += 1
                        batch_skipped += 1
                        log.warning(
                            "[%s] id=%s skipped dup (practice_changes_pkey): %s",
                            table_name, getattr(r, "id", "?"),
                            err_str.split("\n")[0][:200],
                        )
                    else:
                        log.error(
                            "[%s] id=%s UNEXPECTED IntegrityError — aborting batch: %s",
                            table_name, getattr(r, "id", "?"),
                            err_str.split("\n")[0][:400],
                        )
                        raise
            conn.commit()
        log.info("[%s] Batch %d-%d committed (%d synced, %d skipped; %d/%d)",
                 table_name, i, i + len(batch), batch_inserted, batch_skipped,
                 inserted, len(rows))

        if _shutdown_requested:
            break

    if skipped:
        log.info("[%s] Inserted %d, skipped %d duplicates", table_name, inserted, skipped)

    # Phase 1.1: derive watermark from committed rows only. If shutdown fired
    # before anything committed, leave the watermark untouched.
    if _shutdown_requested and not synced_rows:
        log.info("[%s] No committed rows this run — leaving watermark unchanged", table_name)
        return 0

    if not synced_rows:
        log.warning("[%s] No rows committed — skipping watermark update", table_name)
        return inserted
    max_id = max(r.id for r in synced_rows)
    _update_sync_state(
        pg_engine, table_name,
        rows_synced=inserted,
        sync_type="incremental_id",
        last_sync_value=str(max_id),
        notes=f"Synced {inserted} rows ({skipped} dup-skipped), max id={max_id}",
    )
    return inserted


def _sync_full_replace(sqlite_session, pg_engine, config):
    """TRUNCATE + INSERT all rows (for small reference tables).

    Fix 2: Row-count precheck before TRUNCATE prevents wipe-on-empty.
    The TRUNCATE + INSERT run in a single connection/transaction so a
    crash or rollback mid-insert leaves the old data intact.
    Post-sync assertion confirms actual Supabase count matches expected.
    """
    table_name = config["table"]
    model = config["model"]
    columns = _get_column_names(model)

    rows = sqlite_session.query(model).all()

    # Fix 5: NPI-based watched-ZIP filter for tables that reference practices.npi
    # practice_intel and practice_signals have FK → practices.npi in Supabase.
    # Rows whose NPI is not in Supabase practices cause FK violations that abort
    # the full_replace and leave 0 rows after the TRUNCATE CASCADE wipe.
    # Pre-filter them out before the TRUNCATE so the transaction can commit cleanly.
    if config.get("filter_watched_zips_npi") and rows:
        try:
            with pg_engine.connect() as _conn:
                _set_statement_timeout(_conn)
                _npi_result = _conn.execute(text("SELECT npi FROM practices"))
                _supabase_npis = {row[0] for row in _npi_result}
            before_filter = len(rows)
            rows = [r for r in rows if getattr(r, "npi", None) in _supabase_npis]
            if len(rows) < before_filter:
                log.warning(
                    "[%s] filter_watched_zips_npi: dropped %d rows with NPIs not in Supabase practices (%d -> %d)",
                    table_name, before_filter - len(rows), before_filter, len(rows),
                )
            else:
                log.info("[%s] filter_watched_zips_npi: all %d NPIs in Supabase practices — no rows dropped",
                         table_name, len(rows))
        except Exception as _fe:
            log.warning("[%s] filter_watched_zips_npi: could not fetch Supabase NPI set (%s) — proceeding without filter",
                        table_name, _fe)

    # Fix 2: Guard — abort TRUNCATE if source is empty or below floor
    floor = MIN_ROWS_THRESHOLD.get(table_name, 0)
    if not rows:
        log.warning("[%s] Full replace aborted — SQLite returned 0 rows (floor=%d)",
                    table_name, floor)
        return 0
    if len(rows) < floor:
        log.warning("[%s] Full replace aborted — expected at least %d rows, SQLite returned %d",
                    table_name, floor, len(rows))
        return 0

    log.info("[%s] Full replace: %d rows", table_name, len(rows))

    # Fix 3: check shutdown before destructive TRUNCATE
    if _shutdown_requested:
        log.warning("[%s] Shutdown requested — skipping full replace", table_name)
        return 0

    with pg_engine.begin() as conn:
        _set_statement_timeout(conn, local=True)
        conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
        if rows:
            insert_sql = _build_insert_sql(table_name, columns)
            for r in rows:
                d = _model_to_dict(r)
                conn.execute(text(insert_sql), d)

    # Fix 2: Post-sync assertion — verify Supabase actually has the rows
    expected_count = len(rows)
    with pg_engine.connect() as conn:
        _set_statement_timeout(conn)
        actual = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
    if actual < expected_count * 0.95:
        raise RuntimeError(
            f"[{table_name}] Sync verification failed: expected {expected_count} rows, "
            f"Supabase has {actual}"
        )
    if actual != expected_count:
        log.warning("[%s] Minor count mismatch after full replace: expected %d, got %d",
                    table_name, expected_count, actual)

    _update_sync_state(
        pg_engine, table_name,
        rows_synced=actual,
        sync_type="full_replace",
        last_sync_value=None,
        notes=f"Full replace: {actual} rows (verified)",
    )
    return actual


def _sync_watched_zips_only(sqlite_session, pg_engine, config):
    """Sync only practices in watched ZIPs (Chicagoland + Boston ~ 14k rows).

    Fix 1: Replaces the split-transaction pattern (TRUNCATE committed in one
    connection, INSERTs in separate per-batch connections) with a single
    atomic transaction using TRUNCATE ... CASCADE + upsert-by-NPI, all inside
    one pg_engine.begin() block.

    Why TRUNCATE CASCADE (and not DELETE):
    - Postgres TRUNCATE is fully transactional — it can be rolled back inside
      a BEGIN/COMMIT just like any other SQL. (Common myth that DDL isn't
      transactional — this is a MySQL behavior, not Postgres.)
    - The practice_changes.npi_fkey FK constraint is ON DELETE NO ACTION in
      Supabase, so a plain `DELETE FROM practices` is blocked by any referenced
      NPI. TRUNCATE ... CASCADE is the only reliable way to clear practices
      without first manually wiping every FK-referencing table.
      (Verify periodically with `python3 scrapers/verify_fk_policy.py`. If the
      FK has been altered to ON DELETE CASCADE — confdeltype='c' — this block
      can be simplified to plain DELETE; see verify_fk_policy.py for the
      `--apply-cascade` migration helper.)
    - CASCADE wipes practice_changes as a side-effect, matching the documented
      "CASCADE trap" behavior: we then reset practice_changes sync_metadata so
      the incremental sync re-sends all rows on the next dispatch.

    RISK NOTE: The single-transaction approach holds an open connection for the
    full duration of the sync (~14k rows across batches). If the Supabase pooler
    has a short idle timeout this could raise a connection error mid-batch.
    statement_timeout = '600s' is set locally to prevent runaway queries while
    still allowing the full sync window. Monitor for connection timeouts on prod.
    """
    table_name = config["table"]
    model = config["model"]
    conflict_col = config["conflict_col"]
    columns = _get_column_names(model)

    # Get the list of watched ZIP codes from SQLite
    watched = sqlite_session.query(WatchedZip.zip_code).all()
    watched_zips = [z[0] for z in watched]
    log.info("[%s] Filtering to %d watched ZIPs", table_name, len(watched_zips))

    # Fetch only practices in watched ZIPs
    rows = (
        sqlite_session.query(model)
        .filter(model.zip.in_(watched_zips))
        .all()
    )

    if not rows:
        log.warning("[%s] No practices found in watched ZIPs — aborting sync to avoid empty table",
                    table_name)
        return 0

    log.info("[%s] Syncing %d practices (watched ZIPs only) in batches of %d",
             table_name, len(rows), BATCH_SIZE)

    # Fix 3: check shutdown before destructive TRUNCATE
    if _shutdown_requested:
        log.warning("[%s] Shutdown requested — skipping watched_zips sync", table_name)
        return 0

    upsert_sql = _build_upsert_sql(table_name, columns, conflict_col)
    total_synced = 0

    # Fix 1: Single atomic transaction.
    # - SET LOCAL statement_timeout = '600s' guards against a runaway query
    #   without killing the whole session (SET LOCAL is transaction-scoped).
    # - TRUNCATE ... CASCADE wipes practices AND any FK-dependent rows
    #   (practice_changes) in one atomic operation.
    # - sync_metadata reset for practice_changes is included in the same txn so
    #   it's rolled back too if the inserts fail. Incremental sync will then
    #   re-send all practice_changes rows on the next dispatch.
    with pg_engine.begin() as conn:
        _set_statement_timeout(conn, local=True)

        # Clear existing practices. CASCADE wipes practice_changes (FK dep) too.
        # This is the documented pattern — see scrapers/CLAUDE.md "CASCADE trap".
        conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
        # Reset practice_changes sync state so incremental sync re-sends all rows
        # (CASCADE wiped the Postgres rows; SQLite still has them).
        conn.execute(text(
            "DELETE FROM sync_metadata WHERE table_name = 'practice_changes'"
        ))
        # practice_intel and practice_signals both have FK → practices.npi in Supabase,
        # so TRUNCATE TABLE practices CASCADE also wipes them. Reset their sync_metadata
        # so the subsequent full_replace calls know to re-insert all rows.
        conn.execute(text(
            "DELETE FROM sync_metadata WHERE table_name IN ('practice_intel', 'practice_signals')"
        ))
        log.info("[%s] TRUNCATE CASCADE — wiped practices + practice_changes + practice_intel + practice_signals, reset sync_metadata",
                 table_name)

        for i in range(0, len(rows), BATCH_SIZE):
            # Fix 3: honour shutdown — if signal arrives mid-load, rollback entire txn
            if _shutdown_requested:
                log.warning("[%s] Shutdown requested mid-insert (%d/%d) — rolling back",
                            table_name, total_synced, len(rows))
                raise RuntimeError("Shutdown requested — transaction rolled back")

            batch = rows[i:i + BATCH_SIZE]
            for r in batch:
                d = _model_to_dict(r)
                conn.execute(text(upsert_sql), d)
            total_synced += len(batch)
            log.info("[%s] Inserted batch %d-%d (%d/%d)",
                     table_name, i, i + len(batch), total_synced, len(rows))

        # Transaction commits here (end of `with pg_engine.begin()` block)

    log.info("[%s] Transaction committed — %d rows inserted", table_name, total_synced)

    # Fix 1: Post-sync assertion
    expected_count = len(rows)
    with pg_engine.connect() as conn:
        _set_statement_timeout(conn)
        actual = conn.execute(text("SELECT COUNT(*) FROM practices")).scalar()
    if actual < expected_count * 0.95:
        raise RuntimeError(
            f"[{table_name}] Sync verification failed: expected {expected_count} rows "
            f"in watched ZIPs, Supabase has {actual}"
        )
    if actual != expected_count:
        log.warning("[%s] Minor count mismatch: expected %d, verified %d (delta=%d)",
                    table_name, expected_count, actual, expected_count - actual)

    _update_sync_state(
        pg_engine, table_name,
        rows_synced=actual,
        sync_type="watched_zips_only",
        last_sync_value=datetime.now().isoformat(),
        notes=f"Watched ZIPs only: {actual} rows from {len(watched_zips)} ZIPs (verified)",
    )
    return actual


# ---------------------------------------------------------------------------
# Main sync orchestrator
# ---------------------------------------------------------------------------

_STRATEGY_MAP = {
    "incremental_updated_at": _sync_incremental_updated_at,
    "incremental_id": _sync_incremental_id,
    "full_replace": _sync_full_replace,
    "watched_zips_only": _sync_watched_zips_only,
}


# ---------------------------------------------------------------------------
# Reconciliation (ghost-row cleanup)
# ---------------------------------------------------------------------------
# Incremental sync is INSERT/UPDATE-only and never DELETEs. Over time, manual
# SQLite deletions, aborted historical experiments, or schema-change rewrites
# leave "ghost" rows in Supabase that no longer exist locally. They show up
# as a count drift (e.g. SQLite=2861 vs Supabase=2895). Recurring sync
# shouldn't pay this scan cost on every run, so reconciliation is gated
# behind --reconcile-deals.
GHOST_DELETE_FLOOR = 100  # refuse to delete more than this many target_name IS NOT NULL ghosts in one pass
GHOST_DELETE_FLOOR_NULL_TARGET = 50  # tighter floor for the NULL-target fallback pass — its key is fuzzier


def _null_target_key(source, platform, deal_date, source_url, raw_text):
    """Composite identity for a NULL-target deal row.

    target_name IS NULL means the partial unique index uix_deal_no_dup
    doesn't cover the row, so we have no canonical dedup key to compare
    against. Fall back to (source, platform_company, deal_date, source_url,
    md5 of raw_text head) — captures enough source identity to detect
    re-extracted-then-cleaned junk (PESP commentary fragments, GDN de-novo
    openings) without false-flagging legitimate parser output. The 500-byte
    md5 prefix keeps the key compact while still discriminating between
    distinct paragraphs that share platform/date.
    """
    raw_hash = hashlib.md5((raw_text or "").encode("utf-8", "replace")[:500]).hexdigest()[:12]
    return (source, platform, deal_date.isoformat() if deal_date else None, source_url, raw_hash)


def _reconcile_deals(sqlite_session, pg_engine, dry_run=False):
    """Two-pass ghost-row cleanup against the deals table.

    Pass 1: target_name IS NOT NULL — keyed by (platform, target, deal_date),
    same as the partial unique index uix_deal_no_dup. Bounded by
    GHOST_DELETE_FLOOR=100.

    Pass 2: target_name IS NULL — keyed by _null_target_key() because the
    partial unique index doesn't cover NULL targets. This catches rows that
    cleanup_pesp_junk.py / stricter is_deal_block filters removed locally
    but that incremental sync (which never DELETEs) left in Supabase.
    Bounded by GHOST_DELETE_FLOOR_NULL_TARGET=50.

    Each pass logs its own counts and respects its own floor independently.
    Returns total rows deleted across both passes.
    """
    log.info("=" * 60)
    log.info("RECONCILE deals: SQLite is source of truth")
    log.info("=" * 60)

    deleted_total = 0

    # ── Pass 1: target_name IS NOT NULL ──────────────────────────────────
    sqlite_keys: set = set()
    for d in sqlite_session.query(Deal.platform_company, Deal.target_name, Deal.deal_date).all():
        platform, target, dd = d
        if target is None:
            continue
        sqlite_keys.add((platform, target, dd.isoformat() if dd else None))

    log.info("[deals/with-target] SQLite has %d (platform, target, date) keys", len(sqlite_keys))

    with pg_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, platform_company, target_name, deal_date FROM deals "
                 "WHERE target_name IS NOT NULL")
        ).fetchall()
    log.info("[deals/with-target] Supabase has %d rows with target_name IS NOT NULL", len(rows))

    ghosts = []
    for row in rows:
        rid, platform, target, dd = row[0], row[1], row[2], row[3]
        key = (platform, target, dd.isoformat() if dd else None)
        if key not in sqlite_keys:
            ghosts.append((rid, platform, target, dd))

    if not ghosts:
        log.info("[deals/with-target] No ghost rows — Supabase is in sync with SQLite")
    else:
        log.warning("[deals/with-target] Found %d ghost rows in Supabase (not in SQLite)", len(ghosts))
        for rid, platform, target, dd in ghosts[:10]:
            log.warning("  ghost id=%s  %s | %s | %s", rid, platform, target, dd)
        if len(ghosts) > 10:
            log.warning("  ... and %d more", len(ghosts) - 10)

        if len(ghosts) > GHOST_DELETE_FLOOR:
            log.error(
                "[deals/with-target] %d ghosts exceeds floor (%d) — refusing to delete. "
                "Investigate manually before raising the floor.",
                len(ghosts), GHOST_DELETE_FLOOR,
            )
        elif dry_run:
            log.info("[deals/with-target] --dry-run: would delete %d ghost rows", len(ghosts))
        else:
            ghost_ids = [g[0] for g in ghosts]
            with pg_engine.begin() as conn:
                result = conn.execute(
                    text("DELETE FROM deals WHERE id = ANY(:ids)"),
                    {"ids": ghost_ids},
                )
                deleted = result.rowcount or 0
            log.info("[deals/with-target] Deleted %d ghost rows from Supabase", deleted)
            deleted_total += deleted

    # ── Pass 2: target_name IS NULL ──────────────────────────────────────
    sqlite_null_keys: set = set()
    for d in sqlite_session.query(
        Deal.source, Deal.platform_company, Deal.deal_date, Deal.source_url, Deal.raw_text
    ).filter(Deal.target_name.is_(None)).all():
        sqlite_null_keys.add(_null_target_key(*d))

    log.info("[deals/null-target] SQLite has %d unique composite keys (target_name IS NULL)", len(sqlite_null_keys))

    with pg_engine.connect() as conn:
        null_rows = conn.execute(
            text("SELECT id, source, platform_company, deal_date, source_url, raw_text "
                 "FROM deals WHERE target_name IS NULL")
        ).fetchall()
    log.info("[deals/null-target] Supabase has %d rows with target_name IS NULL", len(null_rows))

    null_ghosts = []
    for row in null_rows:
        rid = row[0]
        key = _null_target_key(row[1], row[2], row[3], row[4], row[5])
        if key not in sqlite_null_keys:
            null_ghosts.append((rid, row[1], row[2], row[3], (row[5] or "")[:80]))

    if not null_ghosts:
        log.info("[deals/null-target] No ghost rows — Supabase is in sync with SQLite")
        return deleted_total

    log.warning("[deals/null-target] Found %d ghost rows in Supabase (not in SQLite)", len(null_ghosts))
    for rid, source, platform, dd, raw_head in null_ghosts[:10]:
        log.warning("  ghost id=%s  src=%s  %s | %s | %r", rid, source, platform, dd, raw_head)
    if len(null_ghosts) > 10:
        log.warning("  ... and %d more", len(null_ghosts) - 10)

    if len(null_ghosts) > GHOST_DELETE_FLOOR_NULL_TARGET:
        log.error(
            "[deals/null-target] %d ghosts exceeds floor (%d) — refusing to delete. "
            "Investigate manually before raising the floor.",
            len(null_ghosts), GHOST_DELETE_FLOOR_NULL_TARGET,
        )
        return deleted_total

    if dry_run:
        log.info("[deals/null-target] --dry-run: would delete %d ghost rows", len(null_ghosts))
        return deleted_total

    null_ghost_ids = [g[0] for g in null_ghosts]
    with pg_engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM deals WHERE id = ANY(:ids)"),
            {"ids": null_ghost_ids},
        )
        deleted = result.rowcount or 0
    log.info("[deals/null-target] Deleted %d ghost rows from Supabase", deleted)
    deleted_total += deleted
    return deleted_total


def _check_script_integrity():
    """Compare this script's on-disk sha256 to the HEAD-committed version.

    Observability-only. Logs INFO on match, WARNING on drift. Never raises —
    git unavailable or non-repo checkouts degrade to INFO "skipped". This is
    the early-warning signal for the 2026-04-23 mirror-scraper reversion
    class of problem: a mutated local copy of the sync script running under
    cron without anyone noticing.
    """
    import hashlib
    import subprocess

    try:
        script_path = os.path.abspath(__file__)
        with open(script_path, "rb") as f:
            local_hash = hashlib.sha256(f.read()).hexdigest()

        repo_root = os.path.expanduser("~/dental-pe-tracker")
        rel_path = os.path.relpath(script_path, repo_root).replace(os.sep, "/")

        result = subprocess.run(
            ["git", "show", f"HEAD:{rel_path}"],
            cwd=repo_root,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()[:200]
            log.info("sha256 integrity check skipped (git show failed): %s", err)
            return

        head_hash = hashlib.sha256(result.stdout).hexdigest()
        if local_hash == head_hash:
            log.info("sync_to_supabase.py matches HEAD (sha256=%s)", local_hash[:12])
        else:
            log.warning(
                "sync_to_supabase.py differs from committed HEAD "
                "(local hash: %s, head hash: %s) — investigate",
                local_hash, head_hash,
            )
    except Exception as e:
        log.info("sha256 integrity check skipped: %s", e)


_SYNC_LOCK_PATH = "/tmp/dental-pe-sync.lock"
_sync_lock_handle = None


def _acquire_sync_lock():
    """Prevent concurrent sync runs from racing on TRUNCATE TABLE practices CASCADE.

    Two simultaneous syncs deadlock: the second's TRUNCATE waits for the
    first's transaction to release ACCESS EXCLUSIVE, but each holds locks the
    other needs. Postgres aborts one with `psycopg2.errors.DeadlockDetected`.

    File lock is process-local (single host); for multi-host parity we'd need
    a Postgres advisory lock, but cron + manual local runs are the only sync
    sources today.
    """
    import fcntl
    global _sync_lock_handle
    _sync_lock_handle = open(_SYNC_LOCK_PATH, "w")
    try:
        fcntl.flock(_sync_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.error("Another sync_to_supabase.py is already running (lock=%s) — aborting",
                  _SYNC_LOCK_PATH)
        sys.exit(2)
    _sync_lock_handle.write(f"pid={os.getpid()} started={datetime.now().isoformat()}\n")
    _sync_lock_handle.flush()


def run():
    """Run the full incremental sync from SQLite to Supabase Postgres."""
    _acquire_sync_lock()
    start_time = log_scrape_start("sync_to_supabase")
    log.info("=" * 60)
    log.info("SYNC TO SUPABASE — Starting")
    log.info("=" * 60)

    _check_script_integrity()

    try:
        pg_engine = _get_pg_engine()
        log.info("Postgres connection established")
    except Exception as e:
        log.error("Failed to connect to Postgres: %s", e)
        log_scrape_error("sync_to_supabase", str(e), start_time)
        return

    sqlite_session = get_session()

    try:
        # Ensure tables + sync_metadata exist in Postgres
        _ensure_pg_tables(pg_engine)
        _ensure_sync_metadata(pg_engine)

        total_synced = 0
        results = {}

        for config in SYNC_CONFIG:
            table_name = config["table"]
            strategy = config["strategy"]

            # Fix 3: stop dispatching new tables if shutdown was requested
            if _shutdown_requested:
                log.warning("Shutdown requested — skipping remaining tables")
                break

            try:
                sync_fn = _STRATEGY_MAP[strategy]
                count = sync_fn(sqlite_session, pg_engine, config)
                results[table_name] = count
                total_synced += count
                log.info("[%s] Done: %d rows synced", table_name, count)
            except Exception as e:
                log.error("[%s] FAILED: %s", table_name, e)
                results[table_name] = f"ERROR: {e}"
                # Continue with other tables — don't let one failure stop the sync

        # Fix 4: Post-sync read-after-write verification
        # For each table that reported an integer row count, query Supabase
        # directly to confirm the count matches. This catches "lying success"
        # where the INSERT loop counted rows but the transaction was silently
        # rolled back or the wrong table was targeted.
        # NOTE: incremental_updated_at and incremental_id tables report only
        # the *delta* rows synced, not the total table count — mismatch against
        # total is expected and meaningless, so we skip exact-match checks for
        # those strategies.
        verified_results = {}
        for tbl, reported in results.items():
            if not isinstance(reported, int):
                continue
            try:
                with pg_engine.connect() as conn:
                    _set_statement_timeout(conn)
                    actual = conn.execute(
                        text(f"SELECT COUNT(*) FROM {tbl}")
                    ).scalar()
                verified_results[tbl] = actual
                # Only flag mismatches for full-replace / watched_zips strategies
                # where reported == total rows in Supabase, not just the delta.
                cfg = next((c for c in SYNC_CONFIG if c["table"] == tbl), None)
                if cfg and cfg["strategy"] not in ("incremental_updated_at", "incremental_id"):
                    if actual != reported:
                        log.error(
                            "MISMATCH [%s]: sync reported %d rows but Supabase has %d",
                            tbl, reported, actual
                        )
            except Exception as ve:
                log.warning("[%s] Post-sync verification query failed: %s", tbl, ve)

        # Print summary
        log.info("")
        log.info("=" * 60)
        log.info("SYNC SUMMARY")
        log.info("=" * 60)
        for tbl, result in results.items():
            status = f"{result} rows" if isinstance(result, int) else result
            verified = verified_results.get(tbl)
            verified_str = f" (verified: {verified})" if verified is not None else ""
            log.info("  %-25s %s%s", tbl, status, verified_str)
        log.info("")
        log.info("  TOTAL ROWS SYNCED: %d", total_synced)
        log.info("=" * 60)

        # Count errors
        error_count = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("ERROR"))
        if error_count:
            log.warning("%d table(s) had sync errors", error_count)

        # Report non-zero exit if shutdown was requested mid-run
        if _shutdown_requested:
            log.warning("Sync terminated early due to shutdown signal — partial sync only")
            sys.exit(1)

        log_scrape_complete(
            "sync_to_supabase",
            start_time,
            new_records=total_synced,
            summary=f"Synced {total_synced} total rows to Supabase ({len(results)} tables, {error_count} errors)",
            extra={
                "table_results": {k: v for k, v in results.items() if isinstance(v, int)},
                "verified_row_counts": verified_results,
            },
        )

        # Sync pipeline_events from JSONL log → Supabase (dashboard System page reads this)
        try:
            import json as _json
            from scrapers.pipeline_logger import LOG_FILE as _log_file
            with pg_engine.connect() as conn:
                # Get last synced timestamp
                res = conn.execute(text("SELECT MAX(timestamp) FROM pipeline_events"))
                last_ts = res.scalar() or "1970-01-01T00:00:00"
                last_ts_str = str(last_ts).replace("+00:00", "").replace(" ", "T")[:19]
                new_count = 0
                with open(_log_file, "r") as f:
                    for line in f:
                        try:
                            ev = _json.loads(line.strip())
                            if ev.get("timestamp", "") > last_ts_str:
                                conn.execute(text(
                                    "INSERT INTO pipeline_events (timestamp, source, event, status, summary, details) "
                                    "VALUES (:ts, :src, :evt, :st, :sum, :det)"
                                ), {"ts": ev["timestamp"], "src": ev["source"], "evt": ev["event"],
                                    "st": ev["status"], "sum": ev["summary"],
                                    "det": _json.dumps(ev.get("details", {}))})
                                new_count += 1
                        except Exception as row_err:
                            log.warning("[pipeline_events] Skipping malformed row: %s", row_err)
                conn.commit()
            if new_count:
                log.info("[pipeline_events] Synced %d new events from JSONL", new_count)
        except Exception as e:
            log.warning("[pipeline_events] Could not sync: %s", e)

    except Exception as e:
        log.error("Sync failed: %s", e, exc_info=True)
        log_scrape_error("sync_to_supabase", str(e), start_time)
    finally:
        sqlite_session.close()
        pg_engine.dispose()


def _reconcile_only(dry_run=False):
    """Standalone reconciliation entrypoint (no full sync)."""
    _acquire_sync_lock()
    log.info("Reconciliation-only mode (no incremental sync will run)")
    pg_engine = _get_pg_engine()
    sqlite_session = get_session()
    try:
        _reconcile_deals(sqlite_session, pg_engine, dry_run=dry_run)
    finally:
        sqlite_session.close()
        pg_engine.dispose()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync SQLite → Supabase Postgres")
    parser.add_argument(
        "--reconcile-deals",
        action="store_true",
        help="One-shot ghost-row cleanup: delete Supabase deals not in SQLite. "
             "Skips the regular sync entirely.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --reconcile-deals: show what would be deleted without doing it.",
    )
    args = parser.parse_args()

    if args.reconcile_deals:
        _reconcile_only(dry_run=args.dry_run)
    else:
        run()
