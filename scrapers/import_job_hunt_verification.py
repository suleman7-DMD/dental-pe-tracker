"""Recreate/update the Supabase job_hunt_verification table from the seed file.

The 48-row job-hunt verification layer (what each practice's own website says:
public name, current doctors, owner statement, hiring page) lives in Supabase
and drives the frontend job-hunt lanes and display-name precedence. This script
makes it durable: the table can be dropped and rebuilt from the repo alone.

Artifacts:
  scrapers/job_hunt_verification_schema.sql  -- DDL (CREATE TABLE IF NOT EXISTS)
  data/job_hunt_verification_seed.json       -- full-row export, source of truth
  JOB_HUNT_VERIFICATION_RUNBOOK.md           -- commands + expected counts

Contract (same shape as consolidate_census.py): validate first, write only
when explicitly asked.

  python3 -m scrapers.import_job_hunt_verification              # validate seed only
  python3 -m scrapers.import_job_hunt_verification --allow-db-write
      # apply DDL if the table is missing, then upsert every seed row
      # (INSERT ... ON CONFLICT (location_id) DO UPDATE)
  python3 -m scrapers.import_job_hunt_verification --verify
      # live counts by verification_status must equal the seed's counts
  python3 -m scrapers.import_job_hunt_verification --export
      # refresh the seed file from the live table (run after new rows land)

Baseline (Codex QA, 2026-07-09): 48 rows -- hiring_page_found 2,
roster_verified 28, ownership_conflict 4, call_required 2,
no_usable_website 12. --verify compares live vs seed (hard fail) and
reports drift from this baseline (informational once the layer grows).
"""
import argparse
import json
import os
import sys
from collections import Counter

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

from sqlalchemy import create_engine, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_PATH = os.path.join(ROOT, "data", "job_hunt_verification_seed.json")
SCHEMA_PATH = os.path.join(ROOT, "scrapers", "job_hunt_verification_schema.sql")

BASELINE_2026_07_09 = {
    "hiring_page_found": 2,
    "roster_verified": 28,
    "ownership_conflict": 4,
    "call_required": 2,
    "no_usable_website": 12,
}

VERIFICATION_STATUSES = {
    "roster_verified", "hiring_page_found", "call_required",
    "no_usable_website", "ownership_conflict", "stale_recheck",
}
WEBSITE_STATUSES = {"live", "dead", "parked", "social_only", "none_found"}
OWNERSHIP_EVIDENCE_STATUSES = {"consistent", "conflict", "no_statement"}
JSONB_COLS = ("doctors", "openings", "evidence_urls")

COLUMNS = (
    "location_id", "public_practice_name", "website_url", "website_status",
    "doctors", "provider_count_website", "owner_operator_stated",
    "ownership_evidence_status", "careers_page_url", "has_hiring_page",
    "openings", "verification_status", "evidence_urls", "notes",
    "last_checked_at", "checked_by", "created_at", "updated_at",
)

UPSERT_SQL = text(f"""
    INSERT INTO job_hunt_verification ({', '.join(COLUMNS)})
    VALUES ({', '.join(
        f'CAST(:{c} AS jsonb)' if c in JSONB_COLS else f':{c}' for c in COLUMNS
    )})
    ON CONFLICT (location_id) DO UPDATE SET
        {', '.join(f'{c} = EXCLUDED.{c}' for c in COLUMNS if c not in ('location_id', 'created_at'))}
""")


def load_seed():
    with open(SEED_PATH) as f:
        rows = json.load(f)
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"FAIL: seed {SEED_PATH} is not a non-empty list")
    return rows


def validate(rows):
    problems = []
    seen = set()
    for i, r in enumerate(rows):
        loc = r.get("location_id")
        if not loc:
            problems.append(f"row {i}: missing location_id")
            continue
        if loc in seen:
            problems.append(f"row {i}: duplicate location_id {loc}")
        seen.add(loc)
        missing = [c for c in COLUMNS if c not in r]
        if missing:
            problems.append(f"{loc}: missing keys {missing}")
        if r.get("verification_status") not in VERIFICATION_STATUSES:
            problems.append(f"{loc}: bad verification_status {r.get('verification_status')!r}")
        if r.get("website_status") not in WEBSITE_STATUSES:
            problems.append(f"{loc}: bad website_status {r.get('website_status')!r}")
        if r.get("ownership_evidence_status") not in OWNERSHIP_EVIDENCE_STATUSES:
            problems.append(f"{loc}: bad ownership_evidence_status {r.get('ownership_evidence_status')!r}")
        for c in JSONB_COLS:
            if not isinstance(r.get(c), list):
                problems.append(f"{loc}: {c} is not a list")
    return problems


def tally(rows):
    return dict(Counter(r["verification_status"] for r in rows))


def report_tally(label, counts, total):
    print(f"{label}: {total} rows")
    for status, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status:22s} {n}")


def get_engine():
    url = os.environ.get("SUPABASE_POOLER_URL") or os.environ.get("SUPABASE_DATABASE_URL")
    if not url:
        raise SystemExit("FAIL: no Postgres URL. Set SUPABASE_POOLER_URL in .env.")
    return create_engine(url, pool_size=3, pool_pre_ping=True)


def write(rows):
    engine = get_engine()
    with engine.begin() as conn:
        exists = conn.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='job_hunt_verification'")).fetchone()
        if not exists:
            print("Table missing -- applying scrapers/job_hunt_verification_schema.sql")
            with open(SCHEMA_PATH) as f:
                conn.execute(text(f.read()))
        for r in rows:
            params = {c: r[c] for c in COLUMNS}
            for c in JSONB_COLS:
                params[c] = json.dumps(params[c])
            conn.execute(UPSERT_SQL, params)
    print(f"Upserted {len(rows)} rows.")


def verify(rows):
    engine = get_engine()
    with engine.connect() as conn:
        live = dict(conn.execute(text(
            "SELECT verification_status, count(*) FROM job_hunt_verification "
            "GROUP BY 1")).fetchall())
        live = {k: int(v) for k, v in live.items()}
        live_total = sum(live.values())
    seed_counts = tally(rows)
    report_tally("Seed", seed_counts, len(rows))
    report_tally("Live", live, live_total)
    if live != seed_counts or live_total != len(rows):
        print("FAIL: live table does not match the seed. "
              "Run --export (live is truth) or --allow-db-write (seed is truth).")
        return 1
    if seed_counts != BASELINE_2026_07_09:
        print("Note: counts have drifted from the 2026-07-09 Codex baseline "
              f"({sum(BASELINE_2026_07_09.values())} rows) -- expected as the layer grows.")
    print("OK: live matches seed.")
    return 0


def export():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(
            f"SELECT {', '.join(COLUMNS)} FROM job_hunt_verification ORDER BY location_id"))
        rows = []
        for row in result.mappings():
            r = dict(row)
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
            rows.append(r)
    with open(SEED_PATH, "w") as f:
        json.dump(rows, f, indent=1, default=str)
        f.write("\n")
    report_tally("Exported", tally(rows), len(rows))
    print(f"Wrote {SEED_PATH}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--allow-db-write", action="store_true",
                    help="upsert every seed row into Supabase (creates table if missing)")
    ap.add_argument("--verify", action="store_true",
                    help="compare live counts by verification_status against the seed")
    ap.add_argument("--export", action="store_true",
                    help="refresh the seed file from the live table")
    args = ap.parse_args()

    if args.export:
        export()
        return

    rows = load_seed()
    problems = validate(rows)
    if problems:
        for p in problems:
            print(f"  {p}")
        raise SystemExit(f"FAIL: {len(problems)} seed validation problem(s).")
    report_tally("Seed valid", tally(rows), len(rows))

    if args.allow_db_write:
        write(rows)
    if args.verify:
        raise SystemExit(verify(rows))
    if not args.allow_db_write and not args.verify:
        print("Validate-only (no DB access). Use --allow-db-write, --verify, or --export.")


if __name__ == "__main__":
    main()
