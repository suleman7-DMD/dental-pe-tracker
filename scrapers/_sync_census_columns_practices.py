"""Surgical Supabase sync: push the 6 census columns on `practices`.

After a census consolidation (`consolidate_census.py --allow-db-write`),
SQLite `practices` carries ownership_tier + companions on the mirrored NPIs
(1,037 rows after the 2026-07-02 run). The two existing surgical paths don't
carry these columns (`_sync_practices_changed_rows.py` pushes only the
entity_classification set), and the full `watched_zips_only` path is a
destructive TRUNCATE CASCADE. This script per-row UPDATEs exactly the 6
census columns for every SQLite row where ownership_tier IS NOT NULL.

`practice_locations` census columns are NOT handled here — they ride the
full_replace in `scrapers/_sync_floor_tables_only.py` (ORM-serialized, so the
columns are included since the 2026-07-02 ORM mapping).

Pre-flight: asserts the columns exist in Supabase (they were migrated +
verified 2026-07-02, PROOF_ORM_SYNC_MIGRATION_20260702.md).
Idempotent — re-pushing an already-synced row is a no-op UPDATE.

Usage: python3 -m scrapers._sync_census_columns_practices
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

log = get_logger("sync_census_columns_practices")
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "dental_pe_tracker.db")
BATCH = 200

CENSUS_COLS = ("ownership_tier", "pe_backed", "ownership_evidence_basis",
               "ownership_evidence_urls", "ownership_confidence", "network_id")

UPDATE_SQL = text("""
    UPDATE practices SET
        ownership_tier           = :tier,
        pe_backed                = :pe,
        ownership_evidence_basis = :basis,
        ownership_evidence_urls  = :urls,
        ownership_confidence     = :conf,
        network_id               = :net,
        updated_at               = :ua
    WHERE npi = :npi
""")


def main():
    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("No Postgres URL. Set SUPABASE_DATABASE_URL.")
    pg = create_engine(url, pool_size=3, pool_pre_ping=True)

    # pre-flight: all 6 columns must exist in Supabase practices
    with pg.connect() as conn:
        have = {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='practices'"))}
    missing_cols = [col for col in CENSUS_COLS if col not in have]
    if missing_cols:
        raise RuntimeError(f"Supabase practices missing columns: {missing_cols} "
                           "— run the census column migration first.")

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("""
        SELECT npi, ownership_tier tier, pe_backed pe,
               ownership_evidence_basis basis, ownership_evidence_urls urls,
               ownership_confidence conf, network_id net, updated_at ua
        FROM practices WHERE ownership_tier IS NOT NULL""").fetchall()
    log.info("SQLite practices rows with ownership_tier: %d", len(rows))

    params = [dict(r) for r in rows]
    for p in params:  # Supabase pe_backed is boolean; SQLite yields 0/1
        p["pe"] = bool(p["pe"]) if p["pe"] is not None else None
    updated = missing = 0
    for i in range(0, len(params), BATCH):
        batch = params[i:i + BATCH]
        with pg.begin() as conn:
            for p in batch:
                res = conn.execute(UPDATE_SQL, p)
                if res.rowcount:
                    updated += 1
                else:
                    missing += 1
        log.info("  ...%d/%d", min(i + BATCH, len(params)), len(params))
    log.info("Updated %d rows in Supabase (%d not present there)", updated, missing)

    # read-back verification: count + tier tally must match SQLite exactly
    with pg.connect() as conn:
        live_n = conn.execute(text(
            "SELECT COUNT(*) FROM practices WHERE ownership_tier IS NOT NULL"
        )).scalar()
        live_tally = dict(conn.execute(text(
            "SELECT ownership_tier, COUNT(*) FROM practices "
            "WHERE ownership_tier IS NOT NULL GROUP BY 1")).all())
    truth_n = c.execute(
        "SELECT COUNT(*) FROM practices WHERE ownership_tier IS NOT NULL"
    ).fetchone()[0]
    truth_tally = dict(c.execute(
        "SELECT ownership_tier, COUNT(*) FROM practices "
        "WHERE ownership_tier IS NOT NULL GROUP BY 1"))
    ok = live_n == truth_n and live_tally == truth_tally
    print(f"VERIFY census NPIs: Supabase={live_n}  SQLite truth={truth_n}  "
          f"{'MATCH' if ok else 'MISMATCH'}")
    print(f"  Supabase tally: {live_tally}")
    print(f"  SQLite  tally: {truth_tally}")
    c.close()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
