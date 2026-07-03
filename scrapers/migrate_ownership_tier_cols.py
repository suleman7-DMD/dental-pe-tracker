"""
Phase 2 (Chicagoland Ownership Census) — add the ownership-axis columns to
BOTH `practices` and `practice_locations`, on BOTH databases (Supabase + SQLite).
Idempotent on both. ADDITIVE ONLY — does not touch entity_classification or any
existing value; every new column defaults NULL.

Why a new column family (not new entity_classification enum values):
  entity_classification encodes SIZE (solo/small/large/family). Ownership is a
  separate axis (who owns it, how many locations, PE-backed or not). The census
  needs both. See data/dso_research/RESEARCH_HOME/README.md.

New columns (both tables):
  ownership_tier            text  — true_independent | single_loc_group |
                                    dentist_multi | stealth_dso | branded_dso |
                                    institutional | undetermined
  pe_backed                 bool  — orthogonal PE/MSO badge (NULL = unknown)
  ownership_evidence_basis  text  — locator | web_verified | ein_cluster |
                                    ao_cluster | name_chain | intel_dossier |
                                    structural | none
  ownership_evidence_urls   text  — JSON array of source URLs (>=1 for any
                                    non-structural classification)
  ownership_confidence      text  — high | medium | low
  network_id                text  — groups locations under one owner/brand
                                    (e.g. "ao:SHAFI_SOHAIL")

  Postgres uses ADD COLUMN IF NOT EXISTS (native idempotency).
  SQLite introspects via PRAGMA table_info and skips columns that exist
  (SQLite has no ADD COLUMN IF NOT EXISTS — a re-run would raise "duplicate
  column name" without the introspect step).
"""
import os
import sys

ROOT = "/Users/suleman/dental-pe-tracker"
env_path = os.path.join(ROOT, ".env")
if os.path.exists(env_path):
    for raw in open(env_path):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import sqlite3
from sqlalchemy import create_engine, text

TABLES = ["practices", "practice_locations"]

# (column_name, postgres_type, sqlite_type)
COLS = [
    ("ownership_tier",           "TEXT",        "TEXT"),
    ("pe_backed",                "BOOLEAN",     "BOOLEAN"),
    ("ownership_evidence_basis", "TEXT",        "TEXT"),
    ("ownership_evidence_urls",  "TEXT",        "TEXT"),
    ("ownership_confidence",     "VARCHAR(10)", "VARCHAR(10)"),
    ("network_id",               "TEXT",        "TEXT"),
]

# ── Supabase (Postgres) ──────────────────────────────────────────────────
url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    print("WARN: SUPABASE_DATABASE_URL / DATABASE_URL not set — SKIPPING Supabase leg.")
    print("      Re-run with the env var set to migrate Supabase before any sync.")
else:
    engine = create_engine(url, pool_pre_ping=True)
    print("== Supabase (Postgres) ==")
    with engine.begin() as conn:
        conn.execute(text("SET statement_timeout = '120s'"))
        for table in TABLES:
            for col, pg_type, _ in COLS:
                sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {pg_type}"
                print(f"  -> {sql}")
                conn.execute(text(sql))
            idx = (f"CREATE INDEX IF NOT EXISTS ix_{table}_ownership_tier "
                   f"ON {table}(ownership_tier)")
            print(f"  -> {idx}")
            conn.execute(text(idx))
    with engine.connect() as conn:
        for table in TABLES:
            rows = conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = :t AND column_name = ANY(:cols)
                ORDER BY column_name
            """), {"t": table, "cols": [c[0] for c in COLS]}).fetchall()
            print(f"  Supabase {table}: {len(rows)}/{len(COLS)} ownership cols present")

# ── SQLite (local pipeline DB) ───────────────────────────────────────────
print("\n== SQLite ==")
sqlite_path = os.path.join(ROOT, "data", "dental_pe_tracker.db")
if not os.path.exists(sqlite_path):
    print(f"SKIP: {sqlite_path} not found")
    sys.exit(0)

with sqlite3.connect(sqlite_path) as conn:
    for table in TABLES:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, _, sq_type in COLS:
            if col in existing:
                print(f"  -> {table}.{col} already exists, skipping")
                continue
            sql = f"ALTER TABLE {table} ADD COLUMN {col} {sq_type}"
            print(f"  -> {sql}")
            conn.execute(sql)
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_ownership_tier "
            f"ON {table}(ownership_tier)"
        )
    conn.commit()
    for table in TABLES:
        final = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        have = sum(1 for c in COLS if c[0] in final)
        print(f"  SQLite {table}: {have}/{len(COLS)} ownership cols present")

print("\nDone. ADDITIVE migration complete — no existing data modified.")
