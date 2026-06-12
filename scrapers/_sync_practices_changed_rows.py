"""Surgical Supabase sync: push recently-changed `practices` rows only.

Pushes the classification-bearing columns (entity_classification,
classification_reasoning, ownership_status, affiliated_dso,
affiliated_pe_sponsor, updated_at) for watched-ZIP rows whose SQLite
updated_at >= a cutoff. Avoids the heavy watched_zips_only TRUNCATE CASCADE
path (which also wipes/repopulates practice_changes) when only a few hundred
rows changed — e.g. the 2026-06-12 false-corporate demotions (52 NPIs),
the Data-Axle junk purge (179 DA_ rows -> da_unverified), and the junk
affiliated_dso label NULLing.

Idempotent — re-pushing an already-synced row is a no-op UPDATE.

Usage: python3 -m scrapers._sync_practices_changed_rows [--since 2026-06-09]
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

import sqlite3
from sqlalchemy import create_engine, text
from scrapers.logger_config import get_logger

log = get_logger("sync_practices_changed_rows")
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "dental_pe_tracker.db")
BATCH = 200

UPDATE_SQL = text("""
    UPDATE practices SET
        entity_classification    = :ec,
        classification_reasoning = :reason,
        ownership_status         = :os,
        affiliated_dso           = :dso,
        affiliated_pe_sponsor    = :pe,
        updated_at               = :ua
    WHERE npi = :npi
""")


def main(since="2026-06-09"):
    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("No Postgres URL. Set SUPABASE_DATABASE_URL.")
    pg = create_engine(url, pool_size=3, pool_pre_ping=True)

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("""
        SELECT p.npi, p.entity_classification ec, p.classification_reasoning reason,
               p.ownership_status os, p.affiliated_dso dso,
               p.affiliated_pe_sponsor pe, p.updated_at ua
        FROM practices p JOIN watched_zips w ON p.zip = w.zip_code
        WHERE p.updated_at >= ?""", (since,)).fetchall()
    log.info("Rows changed since %s: %d", since, len(rows))

    params = [{"npi": r["npi"], "ec": r["ec"], "reason": r["reason"],
               "os": r["os"], "dso": r["dso"], "pe": r["pe"], "ua": r["ua"]}
              for r in rows]
    updated = missing = 0
    for i in range(0, len(params), BATCH):
        batch = params[i:i + BATCH]
        with pg.begin() as conn:
            for p in batch:
                res = conn.execute(UPDATE_SQL, p)
                if res.rowcount:
                    updated += 1
                else:
                    missing += 1  # DA_ synthetic rows may not exist in Supabase
        log.info("  ...%d/%d", min(i + BATCH, len(params)), len(params))
    log.info("Updated %d rows in Supabase (%d not present there)", updated, missing)

    # read-back verification
    with pg.connect() as conn:
        live = conn.execute(text("""
            SELECT COUNT(*) FROM practices
            WHERE entity_classification IN ('dso_regional','dso_national')""")).scalar()
    truth = c.execute("""
        SELECT COUNT(*) FROM practices p JOIN watched_zips w ON p.zip=w.zip_code
        WHERE p.entity_classification IN ('dso_regional','dso_national')""").fetchone()[0]
    print(f"VERIFY corp NPIs: Supabase={live}  SQLite truth={truth}  "
          f"{'MATCH' if live == truth else 'MISMATCH'}")
    c.close()


if __name__ == "__main__":
    since = "2026-06-09"
    if "--since" in sys.argv:
        since = sys.argv[sys.argv.index("--since") + 1]
    main(since)
