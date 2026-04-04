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

import os
import sys
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
)
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error
from scrapers.logger_config import get_logger

log = get_logger("sync_to_supabase")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BATCH_SIZE = 2000

# Tables and their sync strategy
# "incremental_updated_at" — WHERE updated_at > last_sync_ts
# "incremental_id"         — WHERE id > last_max_id
# "full_replace"           — TRUNCATE + INSERT
SYNC_CONFIG = [
    # Practices: only sync rows in watched ZIPs (Chicagoland + Boston ≈ 14k rows)
    # Full 400k stays in local SQLite. This makes sync fast and keeps Supabase lean.
    {"table": "practices",        "model": Practice,        "strategy": "watched_zips_only", "conflict_col": "npi"},
    {"table": "deals",            "model": Deal,            "strategy": "incremental_id",         "conflict_col": "id"},
    {"table": "practice_changes", "model": PracticeChange,  "strategy": "incremental_id",         "conflict_col": "id", "filter_watched_zips": True},
    {"table": "zip_scores",       "model": ZipScore,        "strategy": "full_replace",           "conflict_col": None},
    {"table": "watched_zips",     "model": WatchedZip,      "strategy": "full_replace",           "conflict_col": None},
    {"table": "dso_locations",    "model": DSOLocation,     "strategy": "full_replace",           "conflict_col": None},
    {"table": "ada_hpi_benchmarks", "model": ADAHPIBenchmark, "strategy": "full_replace",         "conflict_col": None},
    {"table": "pe_sponsors",      "model": PESponsor,       "strategy": "full_replace",           "conflict_col": None},
    {"table": "platforms",        "model": Platform,        "strategy": "full_replace",           "conflict_col": None},
    {"table": "zip_overviews",    "model": ZipOverview,     "strategy": "full_replace",           "conflict_col": None},
    {"table": "zip_qualitative_intel", "model": ZipQualitativeIntel, "strategy": "full_replace", "conflict_col": None},
    {"table": "practice_intel",        "model": PracticeIntel,       "strategy": "full_replace", "conflict_col": None},
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
    """Create a SQLAlchemy engine for the Supabase Postgres database."""
    url = _get_pg_url()
    engine = create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
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


def _ensure_sync_metadata(pg_engine):
    """Create the sync_metadata table if it doesn't exist."""
    with pg_engine.connect() as conn:
        conn.execute(text(_SYNC_METADATA_DDL))
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

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        dicts = [_model_to_dict(r) for r in batch]
        with pg_engine.connect() as conn:
            for d in dicts:
                conn.execute(text(upsert_sql), d)
            conn.commit()
        total_synced += len(batch)
        log.info("[%s] Batch %d-%d committed (%d/%d)",
                 table_name, i, i + len(batch), total_synced, len(rows))

    # Track the max updated_at we synced
    max_updated_at = max(
        getattr(r, "updated_at") for r in rows if getattr(r, "updated_at") is not None
    )
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

    with pg_engine.connect() as conn:
        for r in rows:
            d = _model_to_dict(r)
            conn.execute(text(upsert_sql), d)
        conn.commit()

    max_id = max(r.id for r in rows)
    _update_sync_state(
        pg_engine, table_name,
        rows_synced=len(rows),
        sync_type="incremental_id",
        last_sync_value=str(max_id),
        notes=f"Synced {len(rows)} rows, max id={max_id}",
    )
    return len(rows)


def _sync_full_replace(sqlite_session, pg_engine, config):
    """TRUNCATE + INSERT all rows (for small reference tables)."""
    table_name = config["table"]
    model = config["model"]
    columns = _get_column_names(model)

    rows = sqlite_session.query(model).all()
    log.info("[%s] Full replace: %d rows", table_name, len(rows))

    with pg_engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
        if rows:
            insert_sql = _build_insert_sql(table_name, columns)
            for r in rows:
                d = _model_to_dict(r)
                conn.execute(text(insert_sql), d)
        conn.commit()

    _update_sync_state(
        pg_engine, table_name,
        rows_synced=len(rows),
        sync_type="full_replace",
        last_sync_value=None,
        notes=f"Full replace: {len(rows)} rows",
    )
    return len(rows)


def _sync_watched_zips_only(sqlite_session, pg_engine, config):
    """Sync only practices in watched ZIPs (Chicagoland + Boston ≈ 14k rows).

    Uses full_replace strategy scoped to watched ZIPs.
    Full 400k stays in local SQLite — Supabase only gets the practices
    that the frontend actually queries.
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
        log.info("[%s] No practices in watched ZIPs", table_name)
        return 0

    log.info("[%s] Syncing %d practices (watched ZIPs only) in batches of %d",
             table_name, len(rows), BATCH_SIZE)

    # Truncate and reload (clean slate ensures no stale out-of-region data)
    with pg_engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
        conn.commit()
    log.info("[%s] Truncated", table_name)

    upsert_sql = _build_upsert_sql(table_name, columns, conflict_col)
    total_synced = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        dicts = [_model_to_dict(r) for r in batch]
        with pg_engine.connect() as conn:
            for d in dicts:
                conn.execute(text(upsert_sql), d)
            conn.commit()
        total_synced += len(batch)
        log.info("[%s] Batch %d-%d committed (%d/%d)",
                 table_name, i, i + len(batch), total_synced, len(rows))

    _update_sync_state(
        pg_engine, table_name,
        rows_synced=total_synced,
        sync_type="watched_zips_only",
        last_sync_value=datetime.now().isoformat(),
        notes=f"Watched ZIPs only: {total_synced} rows from {len(watched_zips)} ZIPs",
    )
    return total_synced


# ---------------------------------------------------------------------------
# Main sync orchestrator
# ---------------------------------------------------------------------------

_STRATEGY_MAP = {
    "incremental_updated_at": _sync_incremental_updated_at,
    "incremental_id": _sync_incremental_id,
    "full_replace": _sync_full_replace,
    "watched_zips_only": _sync_watched_zips_only,
}


def run():
    """Run the full incremental sync from SQLite to Supabase Postgres."""
    start_time = log_scrape_start("sync_to_supabase")
    log.info("=" * 60)
    log.info("SYNC TO SUPABASE — Starting")
    log.info("=" * 60)

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

        # Print summary
        log.info("")
        log.info("=" * 60)
        log.info("SYNC SUMMARY")
        log.info("=" * 60)
        for table_name, result in results.items():
            status = f"{result} rows" if isinstance(result, int) else result
            log.info("  %-25s %s", table_name, status)
        log.info("")
        log.info("  TOTAL ROWS SYNCED: %d", total_synced)
        log.info("=" * 60)

        # Count errors
        error_count = sum(1 for v in results.values() if isinstance(v, str) and v.startswith("ERROR"))
        if error_count:
            log.warning("%d table(s) had sync errors", error_count)

        log_scrape_complete(
            "sync_to_supabase",
            start_time,
            new_records=total_synced,
            summary=f"Synced {total_synced} total rows to Supabase ({len(results)} tables, {error_count} errors)",
            extra={"table_results": {k: v for k, v in results.items() if isinstance(v, int)}},
        )

    except Exception as e:
        log.error("Sync failed: %s", e, exc_info=True)
        log_scrape_error("sync_to_supabase", str(e), start_time)
    finally:
        sqlite_session.close()
        pg_engine.dispose()


if __name__ == "__main__":
    run()
