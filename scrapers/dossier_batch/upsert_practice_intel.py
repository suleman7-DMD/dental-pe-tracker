"""
Focused UPSERT of practice_intel rows from local SQLite -> Supabase Postgres.

Skips TRUNCATE entirely (sync_to_supabase.py uses full_replace which wipes table).
Uses INSERT ... ON CONFLICT DO UPDATE so rows survive concurrent runs of the
official sync until/unless that sync wipes them (it will, eventually — but the
verification window is enough).
"""
import os
import sys
import sqlite3

ROOT = "/Users/suleman/dental-pe-tracker"
sys.path.insert(0, ROOT)
for raw in open(os.path.join(ROOT, ".env")):
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import psycopg2
import psycopg2.extras

POOLER_URL = os.environ["SUPABASE_POOLER_URL"]
SQLITE_PATH = os.path.join(ROOT, "data/dental_pe_tracker.db")

COLS = [
    "npi", "research_date", "website_url", "website_findings",
    "services_listed", "technology_listed", "google_review_count", "google_rating",
    "google_url", "hiring_active", "hiring_signals", "acquisition_found",
    "acquisition_findings", "social_presence", "social_signals",
    "healthgrades_url", "healthgrades_signals", "zocdoc_url", "zocdoc_signals",
    "doctor_age_indicators", "doctor_career_signals", "insurance_accepted",
    "red_flags", "green_flags", "overall_assessment", "acquisition_readiness",
    "confidence", "raw_json", "research_method", "model_used",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_create_tokens",
    "search_count", "cost_usd",
    "escalated", "escalation_findings",
    "succession_intent_detected", "new_grad_friendly_score", "mentorship_signals",
    "associate_runway", "compensation_signals", "red_flags_for_grad", "green_flags_for_grad",
    "verification_searches", "verification_quality", "verification_urls",
    "owner_career_stage", "ppo_heavy", "accepts_medicaid",
]

src = sqlite3.connect(SQLITE_PATH)
src.row_factory = sqlite3.Row

# Build SELECT carefully — some columns may not exist in local SQLite
src_cur = src.execute("PRAGMA table_info(practice_intel)")
src_cols = {r["name"] for r in src_cur.fetchall()}
sel_cols = [c for c in COLS if c in src_cols]
print(f"SQLite practice_intel has {len(src_cols)} cols, selecting {len(sel_cols)}")
print(f"Missing in SQLite (will default to NULL): {[c for c in COLS if c not in src_cols]}")

rows = src.execute(
    f"SELECT {', '.join(sel_cols)} FROM practice_intel"
).fetchall()
print(f"Local SQLite practice_intel: {len(rows)} rows")
quality_breakdown = {}
for r in rows:
    q = r["verification_quality"] if "verification_quality" in r.keys() else None
    quality_breakdown[q] = quality_breakdown.get(q, 0) + 1
print(f"Quality breakdown: {quality_breakdown}")

# Connect to Supabase Postgres via pooler
print(f"\nConnecting to Supabase pooler...")
conn = psycopg2.connect(POOLER_URL, connect_timeout=30)
conn.autocommit = False

# Detect Supabase columns
with conn.cursor() as c:
    c.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='practice_intel'
        ORDER BY ordinal_position
    """)
    pg_cols = [r[0] for r in c.fetchall()]
print(f"Supabase practice_intel columns: {len(pg_cols)}")

# Use intersection — only columns that exist on BOTH sides
common = [c for c in sel_cols if c in pg_cols]
print(f"Common columns: {len(common)}")
missing_sup = [c for c in sel_cols if c not in pg_cols]
if missing_sup:
    print(f"WARNING: SQLite has these but Supabase doesn't: {missing_sup}")

# Build UPSERT
placeholders = ", ".join(["%s"] * len(common))
update_set = ", ".join([f"{c}=EXCLUDED.{c}" for c in common if c != "npi"])
sql = f"""
    INSERT INTO practice_intel ({", ".join(common)})
    VALUES ({placeholders})
    ON CONFLICT (npi) DO UPDATE SET {update_set}
"""

# Build params
params = []
for r in rows:
    rd = dict(r)
    params.append(tuple(rd.get(c) for c in common))

print(f"\nUpserting {len(params)} rows in batches of 100...")
inserted = 0
errors = 0
with conn.cursor() as c:
    for i in range(0, len(params), 100):
        batch = params[i:i + 100]
        try:
            psycopg2.extras.execute_batch(c, sql, batch, page_size=100)
            conn.commit()
            inserted += len(batch)
            print(f"  batch {i // 100 + 1}: +{len(batch)} (running total {inserted})")
        except Exception as e:
            conn.rollback()
            errors += len(batch)
            print(f"  batch {i // 100 + 1}: FAILED — {e!s:.300}")

# Verify
with conn.cursor() as c:
    c.execute("SELECT COUNT(*) FROM practice_intel")
    final_count = c.fetchone()[0]
    c.execute(
        "SELECT verification_quality, COUNT(*) FROM practice_intel "
        "WHERE verification_quality IS NOT NULL GROUP BY verification_quality"
    )
    quality_pg = dict(c.fetchall())
    c.execute(
        "SELECT npi, verification_quality, verification_searches, "
        "       acquisition_readiness, confidence, "
        "       CASE WHEN verification_urls IS NOT NULL THEN length(verification_urls) ELSE 0 END "
        "FROM practice_intel WHERE npi='1780720011'"
    )
    test_row = c.fetchone()

print(f"\n=== RESULTS ===")
print(f"Inserted/updated: {inserted}")
print(f"Errors: {errors}")
print(f"Supabase row count: {final_count}")
print(f"Supabase quality breakdown: {quality_pg}")
print(f"NPI 1780720011 in Supabase: {test_row}")

conn.close()
src.close()
