"""
Push backfilled entity_classification + classification_reasoning from SQLite
practices to Supabase. Focused script — only updates 2 columns, much faster
than full-row upsert via fast_sync_watched.py.

Strategy: read SQLite, group NPIs by (entity_classification, reasoning),
issue one UPDATE per group with a 1000-NPI WHERE IN clause. There are only
~11 distinct classifications, so the entire backfill is ~11-50 updates total.

Idempotent.

Usage: python3 scrapers/sync_practice_classification.py
"""

import os
import sys

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

from collections import defaultdict
from sqlalchemy import create_engine, text
from scrapers.database import get_session, Practice, WatchedZip
from scrapers.logger_config import get_logger

log = get_logger("sync_practice_classification")
WHERE_IN_BATCH = 1000


def get_pg_engine():
    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("No Postgres URL. Set SUPABASE_DATABASE_URL.")
    return create_engine(url, pool_size=3, pool_pre_ping=True, echo=False)


def main():
    pg_engine = get_pg_engine()
    sqlite_session = get_session()

    try:
        watched = [r.zip_code for r in sqlite_session.query(WatchedZip).all()]
        log.info("Watched ZIPs: %d", len(watched))

        rows = (
            sqlite_session.query(
                Practice.npi,
                Practice.entity_classification,
                Practice.classification_reasoning,
            )
            .filter(Practice.zip.in_(watched))
            .all()
        )
        log.info("Read %d watched-ZIP practices from SQLite", len(rows))

        # Group NPIs by (classification, reasoning) so we issue one UPDATE per group.
        groups = defaultdict(list)
        for npi, ec, reason in rows:
            groups[(ec, reason)].append(npi)
        log.info("Distinct (classification, reasoning) groups: %d", len(groups))

        # Issue UPDATEs
        total_updated = 0
        with pg_engine.connect() as conn:
            for (ec, reason), npis in groups.items():
                # Sub-batch the WHERE IN to keep the SQL statement small
                for j in range(0, len(npis), WHERE_IN_BATCH):
                    sub = npis[j:j + WHERE_IN_BATCH]
                    placeholders = ", ".join(f":n{i}" for i in range(len(sub)))
                    params = {f"n{i}": n for i, n in enumerate(sub)}
                    params["ec"] = ec
                    params["reason"] = reason
                    sql = (
                        f"UPDATE practices SET entity_classification = :ec, "
                        f"classification_reasoning = :reason, "
                        f"updated_at = NOW() "
                        f"WHERE npi IN ({placeholders})"
                    )
                    result = conn.execute(text(sql), params)
                    total_updated += result.rowcount or 0
                conn.commit()
                log.info("  %-25s -> %d rows", ec or "NULL", len(npis))

        log.info("=" * 60)
        log.info("DONE: %d practices rows updated in Supabase", total_updated)
        log.info("=" * 60)

        # Verify distribution
        with pg_engine.connect() as conn:
            r = conn.execute(text(
                "SELECT entity_classification, COUNT(*) AS n "
                "FROM practices "
                "WHERE zip IN (SELECT zip_code FROM watched_zips) "
                "GROUP BY entity_classification "
                "ORDER BY n DESC"
            )).fetchall()
            log.info("Supabase practices distribution (watched ZIPs):")
            for ec, n in r:
                log.info("  %-25s %d", ec or "NULL", n)

    finally:
        sqlite_session.close()
        pg_engine.dispose()


if __name__ == "__main__":
    main()
