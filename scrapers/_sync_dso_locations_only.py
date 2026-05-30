"""One-off surgical sync: push ONLY dso_locations to Supabase.

Reuses sync_to_supabase.py's own connection, config, and full_replace path so
it is byte-for-byte the same logic the weekly sync uses — just scoped to the
single `dso_locations` reference table (a leaf table; TRUNCATE does not cascade
to anything important). Used after a standalone ADSO scraper run so we don't pay
the ~40-min full-sync cost (dominated by the practices TRUNCATE+reinsert) just to
refresh one small overlay table.

Safe by construction: _sync_full_replace runs TRUNCATE+INSERT in one transaction
with a MIN_ROWS_THRESHOLD floor (50) precheck, so an empty/short source aborts
without wiping live data.
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

log = get_logger("sync_dso_locations_only")


def main():
    config = next(c for c in SYNC_CONFIG if c["table"] == "dso_locations")
    assert config["strategy"] == "full_replace", config

    pg_engine = _get_pg_engine()
    log.info("Postgres connection established (pooler/IPv4)")
    sqlite_session = get_session()

    try:
        _ensure_pg_tables(pg_engine)
        _ensure_sync_metadata(pg_engine)

        count = _sync_full_replace(sqlite_session, pg_engine, config)
        log.info("[dso_locations] full_replace returned %d rows", count)

        # Post-sync read-after-write verification.
        with pg_engine.connect() as conn:
            actual = conn.execute(text("SELECT COUNT(*) FROM dso_locations")).scalar()
        log.info("[dso_locations] Supabase now holds %d rows (reported %d)", actual, count)
        assert actual == count, f"MISMATCH: reported {count} != actual {actual}"

        if count > 0:
            _update_sync_state(pg_engine, "dso_locations", count, "full_replace",
                               notes="standalone dso_locations sync after ADSO scraper run")
        log.info("[dso_locations] OK — verified %d rows", actual)
    finally:
        sqlite_session.close()


if __name__ == "__main__":
    main()
