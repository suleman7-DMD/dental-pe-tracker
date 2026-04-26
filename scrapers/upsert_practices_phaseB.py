"""
Phase B commit: per-batch upsert of watched-ZIP practices to Supabase.

Why this exists: sync_to_supabase.py::_sync_watched_zips_only wraps TRUNCATE
+ all 14k inserts in one atomic pg_engine.begin() block. Direct connection
(port 5432) drops after ~4-5 min of sustained inserts, rolling back the whole
transaction. This script uses the fast_sync_watched.py resilience pattern:

  - per-batch transactions (each 500-row batch in its own connect+commit)
  - pool_pre_ping=True (auto-reconnect on stale connection)
  - upsert ON CONFLICT(npi) DO UPDATE (no TRUNCATE — survives partial completion)
  - 500-row batches (smaller than the 2000-row default in sync_to_supabase.py)

Usage: python3 scrapers/upsert_practices_phaseB.py
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
from scrapers.database import get_session, Practice, WatchedZip
from scrapers.logger_config import get_logger

log = get_logger("upsert_practices_phaseB")
BATCH_SIZE = 500


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


def upsert_batch(pg_engine, columns, dicts):
    if not dicts:
        return
    col_list = ", ".join(columns)
    param_list = ", ".join(f":{c}" for c in columns)
    update_cols = [c for c in columns if c != "npi"]
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    sql = (
        f"INSERT INTO practices ({col_list}) "
        f"VALUES ({param_list}) "
        f"ON CONFLICT (npi) DO UPDATE SET {update_set}"
    )
    with pg_engine.connect() as conn:
        for d in dicts:
            conn.execute(text(sql), d)
        conn.commit()


def main():
    pg_engine = get_pg_engine()
    sqlite_session = get_session()

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
    failed_batches = 0
    for i in range(0, len(practices), BATCH_SIZE):
        batch = practices[i:i + BATCH_SIZE]
        dicts = [model_to_dict(r) for r in batch]
        try:
            upsert_batch(pg_engine, columns, dicts)
            total += len(batch)
            log.info("Batch %d-%d committed (%d/%d)",
                     i, i + len(batch), total, len(practices))
        except Exception as e:
            failed_batches += 1
            log.error("Batch %d-%d FAILED: %s", i, i + len(batch), e)
            if failed_batches >= 3:
                log.error("3+ batch failures, aborting")
                break

    log.info("=" * 60)
    log.info("UPSERT COMPLETE: %d/%d rows, %d failed batches",
             total, len(practices), failed_batches)
    log.info("=" * 60)
    sqlite_session.close()


if __name__ == "__main__":
    main()
