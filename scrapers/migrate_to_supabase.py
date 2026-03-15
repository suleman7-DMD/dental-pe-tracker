"""
One-time migration: SQLite → Supabase Postgres.

Reads from local SQLite via the existing get_session() helper and bulk-loads
every table into Postgres.  Uses the direct connection (port 5432), NOT the
pooler (port 6543), because bulk inserts need long-lived transactions.

Usage:
    export SUPABASE_DATABASE_URL="postgresql://postgres.<ref>:<password>@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
    python -m scrapers.migrate_to_supabase
"""

import os
import sys
import time
from datetime import datetime, date

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
)
from scrapers.logger_config import get_logger

log = get_logger("migrate_to_supabase")

# ── Configuration ────────────────────────────────────────────────────────────

BATCH_SIZE = 5_000          # rows per INSERT for practices
PROGRESS_EVERY = 10_000     # print progress for practices

# Tables in dependency order (practices first — practice_changes has FK to it)
TABLES = [
    ("practices",        Practice),
    ("deals",            Deal),
    ("practice_changes", PracticeChange),
    ("zip_scores",       ZipScore),
    ("watched_zips",     WatchedZip),
    ("dso_locations",    DSOLocation),
    ("ada_hpi_benchmarks", ADAHPIBenchmark),
    ("pe_sponsors",      PESponsor),
    ("platforms",        Platform),
    ("zip_overviews",    ZipOverview),
]

# Column lists per table — must match the Postgres schema exactly.
# Derived from SQLite PRAGMA table_info output + SQLAlchemy models.
TABLE_COLUMNS = {
    "practices": [
        "id", "npi", "practice_name", "doing_business_as", "entity_type",
        "address", "city", "state", "zip", "phone", "taxonomy_code",
        "taxonomy_description", "enumeration_date", "last_updated",
        "ownership_status", "affiliated_dso", "affiliated_pe_sponsor",
        "notes", "data_source", "latitude", "longitude",
        "year_established", "employee_count", "estimated_revenue",
        "num_providers", "location_type", "buyability_score",
        "buyability_confidence", "classification_confidence",
        "classification_reasoning", "data_axle_raw_name",
        "data_axle_import_date", "raw_record_count", "import_batch_id",
        "parent_company", "parent_iusa", "ein", "franchise_name",
        "iusa_number", "website", "provider_last_name",
        "entity_classification", "created_at", "updated_at",
    ],
    "deals": [
        "id", "deal_date", "platform_company", "pe_sponsor", "target_name",
        "target_city", "target_state", "target_zip", "deal_type",
        "deal_size_mm", "ebitda_multiple", "specialty", "num_locations",
        "source", "source_url", "notes", "raw_text", "created_at",
        "updated_at",
    ],
    "practice_changes": [
        "id", "npi", "change_date", "field_changed", "old_value",
        "new_value", "change_type", "notes", "created_at",
    ],
    "zip_scores": [
        "id", "zip_code", "city", "state", "metro_area", "total_practices",
        "pe_backed_count", "dso_affiliated_count", "independent_count",
        "unknown_count", "institutional_count", "raw_npi_count",
        "classified_count", "consolidation_pct", "consolidation_pct_of_total",
        "independent_pct_of_total", "pe_penetration_pct", "pct_unknown",
        "recent_changes_90d", "state_deal_count_12m", "score_date",
        "opportunity_score", "data_confidence", "consolidated_count",
        "unclassified_pct", "total_gp_locations", "total_specialist_locations",
        "dld_gp_per_10k", "dld_total_per_10k", "people_per_gp_door",
        "buyable_practice_count", "buyable_practice_ratio",
        "corporate_location_count", "corporate_share_pct",
        "family_practice_count", "specialist_density_flag",
        "entity_classification_coverage_pct", "data_axle_enrichment_pct",
        "metrics_confidence", "market_type", "market_type_confidence",
    ],
    "watched_zips": [
        "id", "zip_code", "city", "state", "metro_area", "notes",
        "population", "median_household_income", "population_growth_pct",
        "demographics_updated_at",
    ],
    "dso_locations": [
        "id", "dso_name", "location_name", "address", "city", "state",
        "zip", "phone", "scraped_at", "source_url",
    ],
    "ada_hpi_benchmarks": [
        "id", "data_year", "state", "career_stage", "total_dentists",
        "pct_dso_affiliated", "pct_solo_practice", "pct_group_practice",
        "pct_large_group_10plus", "source_file", "created_at",
    ],
    "pe_sponsors": [
        "id", "name", "also_known_as", "hq_city", "hq_state",
        "aum_estimate_bn", "healthcare_focus", "notes",
    ],
    "platforms": [
        "id", "name", "pe_sponsor_name", "hq_state",
        "estimated_locations", "states_active", "specialties",
        "founded_year", "notes",
    ],
    "zip_overviews": [
        "id", "zip_code", "overview_html", "created_at",
    ],
}

# Tables that have FK references pointing TO them — need CASCADE on TRUNCATE
TABLES_WITH_DEPENDENTS = {"practices"}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _row_to_dict(row, columns):
    """Convert a SQLite row (SQLAlchemy model instance) to a dict of the
    columns we need, reading attributes directly."""
    d = {}
    for col in columns:
        val = getattr(row, col, None)
        # Convert Python date/datetime to string for parameterized insert
        if isinstance(val, (datetime, date)):
            d[col] = val.isoformat()
        else:
            d[col] = val
    return d


def _read_sqlite_rows_raw(sqlite_session, table_name):
    """Read all rows from a SQLite table using raw SQL — avoids model
    attribute mismatches (e.g. buyability_confidence not on the model)."""
    columns = TABLE_COLUMNS[table_name]
    col_list = ", ".join(columns)
    result = sqlite_session.execute(text(f"SELECT {col_list} FROM {table_name}"))
    rows = result.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def _build_insert_sql(table_name, columns):
    """Build a parameterized INSERT statement for Postgres."""
    col_list = ", ".join(columns)
    param_list = ", ".join(f":{c}" for c in columns)
    return text(f"INSERT INTO {table_name} ({col_list}) VALUES ({param_list})")


def _get_pg_engine():
    """Create a Postgres engine from SUPABASE_DATABASE_URL."""
    url = os.environ.get("SUPABASE_DATABASE_URL")
    if not url:
        log.error("SUPABASE_DATABASE_URL environment variable not set.")
        sys.exit(1)
    # Ensure we're using port 5432 (direct), not 6543 (pooler)
    if ":6543/" in url:
        log.warning("URL uses pooler port 6543 — switching to direct port 5432")
        url = url.replace(":6543/", ":5432/")
    return create_engine(url, echo=False, pool_pre_ping=True)


# ── Core Migration ───────────────────────────────────────────────────────────


def migrate_table(sqlite_session, pg_engine, table_name, model_class):
    """Migrate a single table from SQLite to Postgres."""
    columns = TABLE_COLUMNS[table_name]
    insert_sql = _build_insert_sql(table_name, columns)

    # Read all rows from SQLite via raw SQL
    log.info("[%s] Reading rows from SQLite...", table_name)
    rows = _read_sqlite_rows_raw(sqlite_session, table_name)
    total = len(rows)
    log.info("[%s] Read %d rows from SQLite", table_name, total)

    if total == 0:
        log.info("[%s] No rows to migrate — skipping", table_name)
        return 0

    # Truncate target table in Postgres
    cascade = " CASCADE" if table_name in TABLES_WITH_DEPENDENTS else ""
    with pg_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table_name}{cascade}"))
        log.info("[%s] Truncated Postgres table%s", table_name, cascade)

    # Insert in batches
    if table_name == "practices":
        # Large table — batch insert with progress
        inserted = 0
        for batch_start in range(0, total, BATCH_SIZE):
            batch = rows[batch_start:batch_start + BATCH_SIZE]
            with pg_engine.begin() as conn:
                conn.execute(insert_sql, batch)
            inserted += len(batch)
            if inserted % PROGRESS_EVERY == 0 or inserted == total:
                log.info("[%s] Inserted %d / %d rows (%.1f%%)",
                         table_name, inserted, total, inserted / total * 100)
    else:
        # Small table — single batch
        with pg_engine.begin() as conn:
            conn.execute(insert_sql, rows)
        log.info("[%s] Inserted %d rows", table_name, total)

    return total


def reset_sequences(pg_engine):
    """Reset Postgres SERIAL sequences to max(id)+1 for each table."""
    log.info("Resetting Postgres sequences...")
    tables_with_serial = [
        "practices", "deals", "practice_changes", "zip_scores",
        "watched_zips", "dso_locations", "ada_hpi_benchmarks",
        "pe_sponsors", "platforms", "zip_overviews", "sync_metadata",
    ]
    with pg_engine.begin() as conn:
        for table in tables_with_serial:
            seq_name = f"{table}_id_seq"
            result = conn.execute(text(f"SELECT MAX(id) FROM {table}"))
            max_id = result.scalar()
            if max_id is not None:
                conn.execute(text(f"SELECT setval('{seq_name}', :val)"), {"val": max_id})
                log.info("  %s → %d", seq_name, max_id)
            else:
                conn.execute(text(f"SELECT setval('{seq_name}', 1, false)"))
                log.info("  %s → 1 (empty table)", seq_name)


def init_sync_metadata(pg_engine, row_counts):
    """Populate sync_metadata with current timestamps for each migrated table."""
    log.info("Initializing sync_metadata...")
    now = datetime.utcnow().isoformat()
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE sync_metadata"))
        insert_sql = text(
            "INSERT INTO sync_metadata (table_name, last_sync_at, rows_synced, sync_type, notes) "
            "VALUES (:table_name, :last_sync_at, :rows_synced, :sync_type, :notes)"
        )
        for table_name, count in row_counts.items():
            conn.execute(insert_sql, {
                "table_name": table_name,
                "last_sync_at": now,
                "rows_synced": count,
                "sync_type": "full_migration",
                "notes": f"Initial migration from SQLite on {now[:10]}",
            })
    log.info("  Wrote %d rows to sync_metadata", len(row_counts))


def verify_counts(sqlite_session, pg_engine, row_counts):
    """Compare row counts between SQLite and Postgres for each table."""
    log.info("")
    log.info("=" * 60)
    log.info("VERIFICATION: SQLite vs Postgres row counts")
    log.info("=" * 60)

    all_match = True
    for table_name, _ in TABLES:
        # SQLite count
        result = sqlite_session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        sqlite_count = result.scalar()

        # Postgres count
        with pg_engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            pg_count = result.scalar()

        match = "OK" if sqlite_count == pg_count else "MISMATCH"
        if sqlite_count != pg_count:
            all_match = False

        log.info("  %-25s SQLite=%6d  Postgres=%6d  [%s]",
                 table_name, sqlite_count, pg_count, match)

    # Also show sync_metadata
    with pg_engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM sync_metadata"))
        sm_count = result.scalar()
    log.info("  %-25s                Postgres=%6d  [NEW]", "sync_metadata", sm_count)

    log.info("=" * 60)
    if all_match:
        log.info("All table counts match. Migration verified successfully.")
    else:
        log.warning("Some table counts DO NOT match — investigate above.")
    log.info("=" * 60)
    return all_match


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    log.info("=" * 60)
    log.info("Dental PE Tracker — SQLite to Supabase Postgres Migration")
    log.info("=" * 60)

    # Connect to SQLite (existing helper)
    log.info("Connecting to SQLite...")
    sqlite_session = get_session()
    log.info("SQLite connected.")

    # Connect to Postgres
    log.info("Connecting to Postgres (Supabase)...")
    pg_engine = _get_pg_engine()
    # Quick connectivity test
    with pg_engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        pg_version = result.scalar()
    log.info("Postgres connected: %s", pg_version[:60])

    # Run DDL schema (create tables if they don't exist)
    schema_path = os.path.join(os.path.dirname(__file__), "schema_postgres.sql")
    if os.path.exists(schema_path):
        log.info("Applying schema from %s...", schema_path)
        with open(schema_path, "r") as f:
            ddl = f.read()
        # Split on semicolons and execute each statement
        statements = [s.strip() for s in ddl.split(";") if s.strip() and not s.strip().startswith("--")]
        with pg_engine.begin() as conn:
            for stmt in statements:
                try:
                    conn.execute(text(stmt))
                except Exception as e:
                    # Log but continue — some CREATE IF NOT EXISTS may warn
                    log.warning("DDL statement warning: %s", str(e)[:120])
        log.info("Schema applied.")
    else:
        log.warning("schema_postgres.sql not found at %s — assuming tables exist", schema_path)

    # Migrate each table
    log.info("")
    log.info("Starting table migration...")
    t_start = time.time()
    row_counts = {}

    for table_name, model_class in TABLES:
        t0 = time.time()
        count = migrate_table(sqlite_session, pg_engine, table_name, model_class)
        elapsed = time.time() - t0
        row_counts[table_name] = count
        log.info("[%s] Done in %.1fs (%d rows)", table_name, elapsed, count)
        log.info("")

    total_elapsed = time.time() - t_start
    total_rows = sum(row_counts.values())
    log.info("Migration complete: %d total rows in %.1fs", total_rows, total_elapsed)

    # Reset sequences
    reset_sequences(pg_engine)

    # Initialize sync_metadata
    init_sync_metadata(pg_engine, row_counts)

    # Verify
    verify_counts(sqlite_session, pg_engine, row_counts)

    sqlite_session.close()
    log.info("Done. All connections closed.")


if __name__ == "__main__":
    main()
