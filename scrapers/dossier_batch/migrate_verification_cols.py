"""
One-shot: ALTER TABLE practice_intel on Supabase to add 3 anti-hallucination
verification columns. Idempotent — uses ADD COLUMN IF NOT EXISTS.
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
    "ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS verification_searches INTEGER",
    "ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS verification_quality VARCHAR(20)",
    "ALTER TABLE practice_intel ADD COLUMN IF NOT EXISTS verification_urls TEXT",
    "CREATE INDEX IF NOT EXISTS ix_practice_intel_verification_quality "
    "ON practice_intel(verification_quality)",
]

with engine.begin() as conn:
    conn.execute(text("SET statement_timeout = '60s'"))
    for sql in ALTERS:
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
    print(f"\nVerified {len(rows)}/3 columns now exist:")
    for r in rows:
        print(f"  {r[0]:<30} {r[1]}")
