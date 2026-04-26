"""
Fast sync: Push ONLY watched-ZIP practices + all small tables to Supabase.
This gets the Next.js app working with correct data in ~5 minutes
while the full 400k sync runs in parallel.

Usage: python3 scrapers/fast_sync_watched.py
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
from sqlalchemy.orm import sessionmaker

from scrapers.database import (
    get_session, Practice, Deal, PracticeChange,
    ZipScore, WatchedZip, DSOLocation, ADAHPIBenchmark,
    ZipQualitativeIntel, PracticeIntel, Base,
)
from scrapers.logger_config import get_logger

log = get_logger("fast_sync")

BATCH_SIZE = 500  # Smaller batches = faster individual commits


def get_pg_engine():
    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("No Postgres URL. Set SUPABASE_DATABASE_URL.")
    return create_engine(url, pool_size=3, pool_pre_ping=True, echo=False)


def model_to_dict(instance):
    mapper = inspect(type(instance))
    result = {}
    for col in mapper.columns:
        val = getattr(instance, col.key)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif isinstance(val, date):
            val = val.isoformat()
        result[col.key] = val
    return result


def get_column_names(model_class):
    mapper = inspect(model_class)
    return [col.key for col in mapper.columns]


def upsert_batch(pg_engine, table_name, columns, conflict_col, dicts):
    """Upsert a batch of dicts into Postgres using execute_values (single round-trip)."""
    if not dicts:
        return
    from psycopg2.extras import execute_values
    col_list = ", ".join(columns)
    update_cols = [c for c in columns if c != conflict_col]
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    sql = (
        f"INSERT INTO {table_name} ({col_list}) "
        f"VALUES %s "
        f"ON CONFLICT ({conflict_col}) DO UPDATE SET {update_set}"
    )
    rows = [tuple(d.get(c) for c in columns) for d in dicts]
    raw = pg_engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SET statement_timeout = 0")
        execute_values(cur, sql, rows, page_size=100)
        raw.commit()
        cur.close()
    finally:
        raw.close()


def full_replace(pg_engine, table_name, model, sqlite_session):
    """Truncate + insert all rows for a small table using execute_values."""
    from psycopg2.extras import execute_values
    columns = get_column_names(model)
    rows = sqlite_session.query(model).all()
    dicts = [model_to_dict(r) for r in rows]

    col_list = ", ".join(columns)
    insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES %s"
    tuples = [tuple(d.get(c) for c in columns) for d in dicts]

    raw = pg_engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SET statement_timeout = 0")
        cur.execute(f"TRUNCATE TABLE {table_name} CASCADE")
        if tuples:
            execute_values(cur, insert_sql, tuples, page_size=100)
        raw.commit()
        cur.close()
    finally:
        raw.close()

    log.info("[%s] Full replace: %d rows", table_name, len(dicts))
    return len(dicts)


def main():
    pg_engine = get_pg_engine()
    sqlite_session = get_session()

    # Ensure tables exist
    Base.metadata.create_all(pg_engine)
    log.info("Tables ensured in Postgres")

    # Step 1: Sync small reference tables first (full replace)
    log.info("=" * 60)
    log.info("STEP 1: Syncing reference tables...")
    log.info("=" * 60)

    small_tables = [
        ("watched_zips", WatchedZip),
        ("zip_scores", ZipScore),
        ("dso_locations", DSOLocation),
        ("ada_hpi_benchmarks", ADAHPIBenchmark),
        ("zip_qualitative_intel", ZipQualitativeIntel),
        ("practice_intel", PracticeIntel),
    ]

    for tname, model in small_tables:
        try:
            full_replace(pg_engine, tname, model, sqlite_session)
        except Exception as e:
            log.error("[%s] Failed: %s", tname, e)

    # Step 2: Sync watched-ZIP practices (the critical 14k)
    log.info("=" * 60)
    log.info("STEP 2: Syncing watched-ZIP practices...")
    log.info("=" * 60)

    watched_zips = [r.zip_code for r in sqlite_session.query(WatchedZip).all()]
    log.info("Found %d watched ZIPs", len(watched_zips))

    practices = (
        sqlite_session.query(Practice)
        .filter(Practice.zip.in_(watched_zips))
        .all()
    )
    log.info("Found %d practices in watched ZIPs", len(practices))

    columns = get_column_names(Practice)
    total = 0
    for i in range(0, len(practices), BATCH_SIZE):
        batch = practices[i:i + BATCH_SIZE]
        dicts = [model_to_dict(r) for r in batch]
        upsert_batch(pg_engine, "practices", columns, "npi", dicts)
        total += len(batch)
        log.info("[practices] Batch %d-%d committed (%d/%d)",
                 i, i + len(batch), total, len(practices))

    log.info("[practices] Watched-ZIP sync complete: %d rows", total)

    # Step 3: Sync deals (2,500 rows — small)
    log.info("=" * 60)
    log.info("STEP 3: Syncing deals...")
    log.info("=" * 60)

    deals = sqlite_session.query(Deal).all()
    columns = get_column_names(Deal)
    total = 0
    for i in range(0, len(deals), BATCH_SIZE):
        batch = deals[i:i + BATCH_SIZE]
        dicts = [model_to_dict(r) for r in batch]
        upsert_batch(pg_engine, "deals", columns, "id", dicts)
        total += len(batch)
    log.info("[deals] Synced %d rows", total)

    # Step 4: Sync practice_changes
    log.info("=" * 60)
    log.info("STEP 4: Syncing practice changes...")
    log.info("=" * 60)

    changes = sqlite_session.query(PracticeChange).all()
    columns = get_column_names(PracticeChange)
    total = 0
    for i in range(0, len(changes), BATCH_SIZE):
        batch = changes[i:i + BATCH_SIZE]
        dicts = [model_to_dict(r) for r in batch]
        upsert_batch(pg_engine, "practice_changes", columns, "id", dicts)
        total += len(batch)
    log.info("[practice_changes] Synced %d rows", total)

    log.info("=" * 60)
    log.info("FAST SYNC COMPLETE")
    log.info("=" * 60)

    sqlite_session.close()


if __name__ == "__main__":
    main()
