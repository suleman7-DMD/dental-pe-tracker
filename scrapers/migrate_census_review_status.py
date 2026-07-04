"""
Review Desk metadata (2026-07-04) — add `census_review_status` to
`practice_locations` on BOTH databases (Supabase + SQLite). Idempotent on both.
ADDITIVE ONLY — every row defaults NULL; no existing value is touched.

Values (frontend contract, dental-pe-nextjs/src/lib/census/ownership-truth.ts
deriveSourceClass): 'held' | 'undetermined' | NULL.
  held         — row is behind a PM/gate hold (adjudication, positive-proof
                 audit, R4 network, closure suspect, PM hold file)
  undetermined — researched by Lane A, evidence too thin to tier
  NULL         — never researched, out of scope, or already tiered
                 (ownership_tier always wins; stale status is benign)

practice_locations ONLY — NPI mirroring is a tier concept; review status is
location-level Review Desk metadata. Written by
scrapers/backfill_census_review_status.py, never by consolidate_census.py.

Postgres uses ADD COLUMN IF NOT EXISTS; SQLite introspects PRAGMA table_info
and skips existing columns (no ADD COLUMN IF NOT EXISTS in SQLite).
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

TABLE = "practice_locations"
COL = "census_review_status"
PG_TYPE = "VARCHAR(20)"
SQ_TYPE = "VARCHAR(20)"

# ── Supabase (Postgres) ──────────────────────────────────────────────────
url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    print("WARN: SUPABASE_DATABASE_URL / DATABASE_URL not set — SKIPPING Supabase leg.")
    print("      Re-run with the env var set BEFORE any full_replace sync of "
          "practice_locations, or the ORM insert will fail on the missing column.")
else:
    engine = create_engine(url, pool_pre_ping=True)
    print("== Supabase (Postgres) ==")
    with engine.begin() as conn:
        conn.execute(text("SET statement_timeout = '120s'"))
        sql = f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {COL} {PG_TYPE}"
        print(f"  -> {sql}")
        conn.execute(text(sql))
        idx = f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_{COL} ON {TABLE}({COL})"
        print(f"  -> {idx}")
        conn.execute(text(idx))
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
        """), {"t": TABLE, "c": COL}).fetchall()
        print(f"  Supabase {TABLE}.{COL}: {'PRESENT' if rows else 'MISSING'}")

# ── SQLite (local pipeline DB) ───────────────────────────────────────────
print("\n== SQLite ==")
sqlite_path = os.path.join(ROOT, "data", "dental_pe_tracker.db")
if not os.path.exists(sqlite_path):
    print(f"SKIP: {sqlite_path} not found")
    sys.exit(0)

with sqlite3.connect(sqlite_path) as conn:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})").fetchall()}
    if COL in existing:
        print(f"  -> {TABLE}.{COL} already exists, skipping")
    else:
        sql = f"ALTER TABLE {TABLE} ADD COLUMN {COL} {SQ_TYPE}"
        print(f"  -> {sql}")
        conn.execute(sql)
    conn.execute(f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_{COL} ON {TABLE}({COL})")
    conn.commit()
    final = {r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})").fetchall()}
    print(f"  SQLite {TABLE}.{COL}: {'PRESENT' if COL in final else 'MISSING'}")

print("\nDone. ADDITIVE migration complete — no existing data modified.")
