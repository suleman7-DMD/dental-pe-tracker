"""
F32 (Supabase side) — Delete the 235 watched-ZIP hygienist NPIs from Supabase
practices that were left orphan after the SQLite cleanup.

The fast_sync_watched.py path UPSERTs (insert-or-update) rather than
truncating, so removing rows from SQLite doesn't propagate to Supabase.
This script issues a direct DELETE for the leak rows that the F02 invariant
flags.

Idempotent: re-running deletes nothing the second time.

Pre-condition: scrapers/cleanup_hygienist_leak.py must have been run first
so the SQLite leak is already gone — otherwise the next sync would re-insert
these rows.

Usage:
    python3 scrapers/cleanup_supabase_hygienist_leak.py            # dry-run
    python3 scrapers/cleanup_supabase_hygienist_leak.py --execute  # actually delete
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Load env
_env_file = os.path.join(ROOT, ".env")
if os.path.isfile(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


LEAK_FILTER = (
    "data_source = 'nppes' AND (taxonomy_code IS NULL OR taxonomy_code NOT LIKE '1223%%')"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    db_url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("FATAL: SUPABASE_DATABASE_URL or DATABASE_URL must be set", file=sys.stderr)
        return 2

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(f"SELECT COUNT(*) FROM practices WHERE {LEAK_FILTER}")
    practices_count = cur.fetchone()[0]
    cur.execute(
        f"SELECT COUNT(*) FROM practice_changes pc "
        f"WHERE pc.npi IN (SELECT npi FROM practices WHERE {LEAK_FILTER})"
    )
    changes_count = cur.fetchone()[0]
    cur.execute(
        f"SELECT COUNT(*) FROM practice_intel pi "
        f"WHERE pi.npi IN (SELECT npi FROM practices WHERE {LEAK_FILTER})"
    )
    intel_count = cur.fetchone()[0]
    cur.execute(
        f"SELECT COUNT(*) FROM practice_signals ps "
        f"WHERE ps.npi IN (SELECT npi FROM practices WHERE {LEAK_FILTER})"
    )
    signals_count = cur.fetchone()[0]

    print("F32 Supabase hygienist-leak cleanup")
    print("-" * 56)
    print(f"  practices (Supabase):        {practices_count:>8,}")
    print(f"  practice_changes dep rows:   {changes_count:>8,}")
    print(f"  practice_intel dep rows:     {intel_count:>8,}")
    print(f"  practice_signals dep rows:   {signals_count:>8,}")
    print()

    if not args.execute:
        print("DRY-RUN. No rows deleted. Re-run with --execute to apply.")
        cur.close()
        conn.close()
        return 0

    if practices_count == 0:
        print("No leak rows in Supabase. Nothing to do.")
        cur.close()
        conn.close()
        return 0

    print("Executing DELETEs (single transaction)...")
    try:
        for tbl in ("practice_signals", "practice_intel", "practice_changes"):
            cur.execute(
                f"DELETE FROM {tbl} WHERE npi IN (SELECT npi FROM practices WHERE {LEAK_FILTER})"
            )
            print(f"  {tbl}: {cur.rowcount:>8,} deleted")
        cur.execute(f"DELETE FROM practices WHERE {LEAK_FILTER}")
        print(f"  practices:        {cur.rowcount:>8,} deleted")
        conn.commit()
        print()
        print("Cleanup complete. Now run scripts/check_data_invariants.py — F02 should PASS.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        return 1
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
