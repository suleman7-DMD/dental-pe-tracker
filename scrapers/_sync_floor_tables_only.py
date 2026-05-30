"""One-off surgical sync: push the corporate-FLOOR tables to Supabase.

After the 2026-05-30 IL DSO seeding + verified-corporate reclassification
(scrapers/seed_il_dso_locations.py + scrapers/reclassify_verified_corporate_il.py),
SQLite holds the new documented floor (262/4,970 = 5.27%) but the live site
still reads the old 4.02%. The headline floor + DSO overlay are driven by three
reference tables, all full_replace:

  dso_locations      — the 394-row IL DSO-office overlay (Warroom map)
  zip_scores         — corporate_location_count / corporate_share_pct (the FLOOR)
  practice_locations — location-level entity_classification (Sitrep / Market Intel
                       corporate vs independent counts)

This reuses sync_to_supabase.py's own engine + _sync_full_replace path, so each
table is synced byte-for-byte the way the weekly sync does it (TRUNCATE CASCADE
+ INSERT in one transaction, MIN_ROWS_THRESHOLD floor precheck, post-sync
read-after-write COUNT assertion). It avoids the ~40-min full sync (dominated by
the practices TRUNCATE+reinsert).

NOT synced here: `practices` (strategy watched_zips_only — heavier CASCADE that
also wipes/repopulates practice_changes). The 214 NPI-level entity_classification
flips from the reclassification are NPI-unit only (Job Market scoring) and
self-heal on the next weekly full sync, which reinserts every watched practice
row from SQLite. The headline location-level floor does not depend on them.

GATED: changes a live headline number. Run only on explicit user confirmation.

Run:  python3 -m scrapers._sync_floor_tables_only
"""
from sqlalchemy import text

from scrapers.sync_to_supabase import (
    SYNC_CONFIG,
    _get_pg_engine,
    _ensure_pg_tables,
    _ensure_sync_metadata,
    _sync_full_replace,
    _update_sync_state,
)
from scrapers.database import get_session
from scrapers.logger_config import get_logger

log = get_logger("sync_floor_tables_only")

# Order matters only for readability; each is an independent full_replace.
TABLES = ["dso_locations", "zip_scores", "practice_locations"]


def _fk_dependents(pg_engine, table_name):
    """List tables in Supabase whose FKs reference `table_name` (so the operator
    can see exactly what TRUNCATE ... CASCADE would touch). Informational only —
    the weekly sync already performs this same CASCADE."""
    q = text("""
        SELECT DISTINCT c.relname
        FROM pg_constraint con
        JOIN pg_class c   ON c.oid = con.conrelid
        JOIN pg_class rc  ON rc.oid = con.confrelid
        WHERE con.contype = 'f' AND rc.relname = :t AND c.relname <> :t
    """)
    with pg_engine.connect() as conn:
        return [r[0] for r in conn.execute(q, {"t": table_name})]


def main():
    pg_engine = _get_pg_engine()
    log.info("Postgres connection established (pooler/IPv4)")
    sqlite_session = get_session()

    results = {}
    try:
        _ensure_pg_tables(pg_engine)
        _ensure_sync_metadata(pg_engine)

        for tbl in TABLES:
            config = next(c for c in SYNC_CONFIG if c["table"] == tbl)
            assert config["strategy"] == "full_replace", (tbl, config["strategy"])

            deps = _fk_dependents(pg_engine, tbl)
            if deps:
                log.warning("[%s] TRUNCATE CASCADE will also clear FK dependents: %s "
                            "(weekly sync does the same)", tbl, deps)
            else:
                log.info("[%s] no FK dependents — CASCADE is a no-op beyond this table", tbl)

            count = _sync_full_replace(sqlite_session, pg_engine, config)
            with pg_engine.connect() as conn:
                actual = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            assert actual == count, f"[{tbl}] MISMATCH reported {count} != actual {actual}"
            results[tbl] = actual
            log.info("[%s] OK — verified %d rows in Supabase", tbl, actual)

        # Read back the live floor so we can prove the headline updated.
        with pg_engine.connect() as conn:
            gp, corp = conn.execute(text(
                "SELECT SUM(total_gp_locations), SUM(corporate_location_count) "
                "FROM zip_scores")).fetchone()
            il_seed = conn.execute(text(
                "SELECT COUNT(*) FROM dso_locations WHERE source_url LIKE 'il_seed:%'"
            )).scalar()
        pct = 100.0 * corp / gp if gp else 0.0
        log.info("LIVE floor now: %d/%d = %.2f%%  | dso_locations il_seed rows: %d",
                 corp, gp, pct, il_seed)
        print(f"\nSYNCED {results}")
        print(f"LIVE Supabase floor: {corp}/{gp} = {pct:.2f}%   il_seed DSO offices: {il_seed}")
    finally:
        sqlite_session.close()


if __name__ == "__main__":
    main()
