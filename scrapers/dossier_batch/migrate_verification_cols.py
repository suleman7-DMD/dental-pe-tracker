"""
ALTER TABLE practice_intel — add the 3 anti-hallucination verification columns
on BOTH databases (Supabase + SQLite). Idempotent on both.

- Supabase: uses `ADD COLUMN IF NOT EXISTS` (Postgres native idempotency).
- SQLite: introspects via PRAGMA table_info and skips columns that exist.
  SQLite has no `ADD COLUMN IF NOT EXISTS` syntax, so without the introspect
  step a re-run raises "duplicate column name".
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

# ── Supabase (Postgres) ──────────────────────────────────────────────────

url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    print("FATAL: SUPABASE_DATABASE_URL not set", file=sys.stderr)
    sys.exit(1)

engine = create_engine(url, pool_pre_ping=True)

PG_ALTERS = [
    "ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS verification_searches INTEGER",
    "ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS verification_quality VARCHAR(20)",
    "ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS verification_urls TEXT",
    "CREATE INDEX IF NOT EXISTS ix_practice_intel_verification_quality "
    "ON practice_intel(verification_quality)",
]

print("== Supabase (Postgres) ==")
with engine.begin() as conn:
    conn.execute(text("SET statement_timeout = '60s'"))
    for sql in PG_ALTERS:
        print(f"  -> {sql[:80]}...")
        conn.execute(text(sql))
    print("OK — verification columns added (or already existed).")

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'practice_intel'
          AND column_name IN ('verification_searches','verification_quality','verification_urls')
        ORDER BY column_name
    """))
    rows = result.fetchall()
    print(f"\nVerified {len(rows)}/3 columns now exist on Supabase:")
    for r in rows:
        print(f"  {r[0]:<30} {r[1]}")

# ── SQLite (local pipeline DB) ───────────────────────────────────────────

print("\n== SQLite ==")
sqlite_path = os.path.join(ROOT, "data", "dental_pe_tracker.db")
if not os.path.exists(sqlite_path):
    print(f"SKIP: {sqlite_path} not found (running in environment without local DB)")
    sys.exit(0)

SQLITE_COLS = [
    ("verification_searches", "INTEGER"),
    ("verification_quality", "VARCHAR(20)"),
    ("verification_urls", "TEXT"),
]

with sqlite3.connect(sqlite_path) as conn:
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(practice_intel)").fetchall()}
    for col_name, col_type in SQLITE_COLS:
        if col_name in existing_cols:
            print(f"  -> {col_name} already exists, skipping")
            continue
        sql = f"ALTER TABLE practice_intel ADD COLUMN {col_name} {col_type}"
        print(f"  -> {sql}")
        conn.execute(sql)
    # Idempotent index — SQLite's CREATE INDEX IF NOT EXISTS works fine.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_practice_intel_verification_quality "
        "ON practice_intel(verification_quality)"
    )
    conn.commit()
    final_cols = {r[1] for r in conn.execute("PRAGMA table_info(practice_intel)").fetchall()}
    have = sum(1 for col_name, _ in SQLITE_COLS if col_name in final_cols)
    print(f"\nVerified {have}/3 columns now exist on SQLite.")
