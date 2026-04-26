"""
Fast focused sync: practice_locations + zip_scores → Supabase.

Why this exists: after `reclassify_locations.py` + `merge_and_score.py` run,
only these two tables change. The full sync_to_supabase.py path takes 5+ min
because of the practices watched_zips_only step we don't actually need here.

practice_locations: idempotent UPSERT keyed on location_id (no TRUNCATE).
zip_scores: TRUNCATE + INSERT (small enough to wipe cleanly).
Both use 200-row batches with per-batch commits to avoid Supabase statement
timeouts. pool_pre_ping=True handles SSL drops.

Usage: python3 scrapers/fast_sync_locations_and_scores.py
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
    if os.path.isfile(_env_file):
        with open(_env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine, text, inspect
from scrapers.database import get_session, PracticeLocation, ZipScore
from scrapers.logger_config import get_logger

log = get_logger("fast_sync_locations_and_scores")
BATCH_SIZE = 200


def get_pg_engine():
    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("No Postgres URL. Set SUPABASE_DATABASE_URL.")
    return create_engine(url, pool_size=3, pool_pre_ping=True, echo=False)


def model_to_dict(instance, allowed_columns=None):
    mapper = inspect(type(instance))
    result = {}
    for col in mapper.columns:
        if allowed_columns is not None and col.key not in allowed_columns:
            continue
        val = getattr(instance, col.key)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif isinstance(val, date):
            val = val.isoformat()
        result[col.key] = val
    return result


def get_remote_columns(pg_engine, table_name):
    """Return the set of column names in the Supabase table."""
    with pg_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :tbl AND table_schema = 'public'"
        ), {"tbl": table_name}).fetchall()
    return {r[0] for r in rows}


def upsert_batches(pg_engine, table_name, columns, dicts, pk_col, truncate_first=False):
    """Insert in batches with per-batch commits.

    If pk_col is provided, uses INSERT ... ON CONFLICT (pk_col) DO UPDATE
    so re-runs are idempotent (handles partial-failure recovery).

    truncate_first: only set to True for tables small enough to wipe (zip_scores).
    """
    if not dicts:
        log.warning("No rows to insert for %s", table_name)
        return 0

    col_list = ", ".join(columns)
    param_list = ", ".join(f":{c}" for c in columns)

    if pk_col and not truncate_first:
        # Build ON CONFLICT DO UPDATE clause
        update_cols = [c for c in columns if c != pk_col]
        update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        insert_sql = (
            f"INSERT INTO {table_name} ({col_list}) VALUES ({param_list}) "
            f"ON CONFLICT ({pk_col}) DO UPDATE SET {update_set}"
        )
        log.info("Using UPSERT (no TRUNCATE) keyed on %s", pk_col)
    else:
        insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({param_list})"

    if truncate_first:
        with pg_engine.connect() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
            conn.commit()
        log.info("TRUNCATEd %s", table_name)

    total = 0
    failed_batches = 0
    for i in range(0, len(dicts), BATCH_SIZE):
        batch = dicts[i:i + BATCH_SIZE]
        try:
            with pg_engine.connect() as conn:
                # executemany via list of dicts
                conn.execute(text(insert_sql), batch)
                conn.commit()
            total += len(batch)
            if (i // BATCH_SIZE) % 5 == 0:
                log.info("  %s: %d/%d committed", table_name, total, len(dicts))
        except Exception as e:
            failed_batches += 1
            log.error("Batch %d-%d FAILED: %s", i, i + len(batch), e)
            if failed_batches >= 3:
                log.error("3+ batch failures, aborting")
                return total

    log.info("DONE %s: %d/%d rows committed (%d failed batches)",
             table_name, total, len(dicts), failed_batches)
    return total


def sync_table(pg_engine, sqlite_session, model_class, table_name, pk_col, truncate_first=False):
    log.info("=== Syncing %s ===", table_name)

    # Determine allowed columns by intersecting local model with remote schema
    local_cols = {c.key for c in inspect(model_class).columns}
    remote_cols = get_remote_columns(pg_engine, table_name)
    allowed = local_cols & remote_cols
    skipped_local = local_cols - remote_cols
    skipped_remote = remote_cols - local_cols
    if skipped_local:
        log.warning("Skipping local-only columns: %s", sorted(skipped_local))
    if skipped_remote:
        log.warning("Remote has columns we don't write: %s", sorted(skipped_remote))

    # Read all rows from SQLite
    rows = sqlite_session.query(model_class).all()
    log.info("%s: %d rows in SQLite", table_name, len(rows))

    columns = sorted(allowed)
    dicts = [model_to_dict(r, allowed_columns=allowed) for r in rows]

    return upsert_batches(pg_engine, table_name, columns, dicts,
                          pk_col=pk_col, truncate_first=truncate_first)


def main():
    pg_engine = get_pg_engine()
    sqlite_session = get_session()

    try:
        # 1. practice_locations (5,732 rows) — UPSERT on location_id, idempotent
        loc_count = sync_table(pg_engine, sqlite_session, PracticeLocation,
                                "practice_locations", pk_col="location_id",
                                truncate_first=False)

        # 2. zip_scores (290 rows) — small table, TRUNCATE+INSERT is fine
        zip_count = sync_table(pg_engine, sqlite_session, ZipScore,
                                "zip_scores", pk_col=None,
                                truncate_first=True)

        log.info("=" * 60)
        log.info("FAST SYNC COMPLETE: practice_locations=%d zip_scores=%d",
                 loc_count, zip_count)
        log.info("=" * 60)

        # 3. Verify Supabase has the new corporate counts
        with pg_engine.connect() as conn:
            r = conn.execute(text(
                "SELECT entity_classification, COUNT(*) AS n "
                "FROM practice_locations "
                "WHERE zip IN (SELECT zip_code FROM watched_zips) "
                "  AND is_likely_residential = false "
                "GROUP BY entity_classification "
                "ORDER BY n DESC"
            )).fetchall()
            log.info("Supabase practice_locations watched-ZIP distribution:")
            for ec, n in r:
                log.info("  %-20s %d", ec or "NULL", n)

            r = conn.execute(text(
                "SELECT SUM(total_gp_locations) AS gp, SUM(corporate_location_count) AS corp "
                "FROM zip_scores WHERE zip_code IN (SELECT zip_code FROM watched_zips)"
            )).fetchone()
            if r and r[0]:
                pct = 100.0 * (r[1] or 0) / r[0]
                log.info("Supabase zip_scores rollup: %d corporate / %d total = %.2f%%",
                         r[1] or 0, r[0], pct)

    finally:
        sqlite_session.close()
        pg_engine.dispose()


if __name__ == "__main__":
    main()
