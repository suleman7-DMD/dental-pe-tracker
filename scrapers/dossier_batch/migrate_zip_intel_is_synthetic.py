"""
One-shot: ALTER TABLE zip_qualitative_intel on Supabase to add `is_synthetic`
flag for distinguishing placeholder rows (research_method='claude_api_unknown')
from rows with real Anthropic web-search-backed research.

Idempotent — uses ADD COLUMN IF NOT EXISTS. Safe to re-run.

Companion SQLite migration is one-shot inline (SQLite has no IF NOT EXISTS
support for ALTER TABLE ADD COLUMN); see CLAUDE.md F13 entry for the run log.
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

from sqlalchemy import create_engine, text

url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not url:
    print("FATAL: SUPABASE_DATABASE_URL not set", file=sys.stderr)
    sys.exit(1)

engine = create_engine(url, pool_pre_ping=True)

ALTERS = [
    "ALTER TABLE zip_qualitative_intel ADD COLUMN IF NOT EXISTS is_synthetic BOOLEAN NOT NULL DEFAULT FALSE",
    "CREATE INDEX IF NOT EXISTS ix_zip_qualitative_intel_is_synthetic "
    "ON zip_qualitative_intel(is_synthetic)",
]

# Backfill placeholder rows: research_method='claude_api_unknown' means the row
# was inserted before the bulletproofed protocol with web_search forced.
BACKFILL = (
    "UPDATE zip_qualitative_intel "
    "SET is_synthetic = TRUE "
    "WHERE research_method = 'claude_api_unknown' AND is_synthetic = FALSE"
)

with engine.begin() as conn:
    conn.execute(text("SET statement_timeout = '60s'"))
    for sql in ALTERS:
        print(f"  -> {sql[:80]}...")
        conn.execute(text(sql))
    print("OK — is_synthetic column + index added (or already existed).")

    res = conn.execute(text(BACKFILL))
    print(f"Backfilled {res.rowcount} placeholder rows to is_synthetic=true.")

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT is_synthetic, COUNT(*) AS n
        FROM zip_qualitative_intel
        GROUP BY is_synthetic
        ORDER BY is_synthetic
    """))
    rows = result.fetchall()
    print("\nLive composition:")
    for r in rows:
        label = "synthetic placeholder" if r[0] else "real research"
        print(f"  is_synthetic={r[0]} ({label}): {r[1]} rows")
