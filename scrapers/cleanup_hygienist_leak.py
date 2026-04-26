"""
F32 — One-shot cleanup of NPPES non-1223 taxonomy leak in SQLite.

Deletes rows from `practices` (and dependents in `practice_changes`,
`practice_intel`, `practice_signals`) where:
    data_source = 'nppes' AND taxonomy_code NOT LIKE '1223%'

These are hygienists (124Q), assistants (1268), denturists (1224), labs
(1269), dental therapists (125J/125K), and oral medicinists (125Q). Per
the NPPES rule documented in scrapers/CLAUDE.md, only the 1223 prefix
counts as Dentist — these rows should not have been imported. The
downloader's parse_nppes_row() now blocks them at import, but the SQLite
DB has ~20,406 historical leaks predating that fix.

Sister-fix in sync_to_supabase.py adds a defensive filter so even
post-cleanup, any future leak is held back from Supabase.

Idempotent: running twice deletes nothing the second time. Safe.

Usage:
    python3 scrapers/cleanup_hygienist_leak.py            # dry-run (counts only)
    python3 scrapers/cleanup_hygienist_leak.py --execute  # actually delete
"""
from __future__ import annotations

import argparse
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scrapers.database import init_db, get_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run DELETEs. Without this flag, prints counts only.",
    )
    args = parser.parse_args()

    init_db()
    session = get_session()

    leak_filter_sql = (
        "data_source = 'nppes' AND (taxonomy_code IS NULL OR taxonomy_code NOT LIKE '1223%')"
    )

    counts = {}
    counts["practices_total"] = session.execute(
        __import__("sqlalchemy").text(
            f"SELECT COUNT(*) FROM practices WHERE {leak_filter_sql}"
        )
    ).scalar()
    counts["practices_watched"] = session.execute(
        __import__("sqlalchemy").text(
            f"SELECT COUNT(*) FROM practices p JOIN watched_zips w ON p.zip=w.zip_code WHERE {leak_filter_sql}"
        )
    ).scalar()
    for dep_table in ("practice_changes", "practice_intel", "practice_signals"):
        counts[f"{dep_table}_dep"] = session.execute(
            __import__("sqlalchemy").text(
                f"SELECT COUNT(*) FROM {dep_table} dep "
                f"JOIN practices p ON dep.npi = p.npi "
                f"WHERE {leak_filter_sql}"
            )
        ).scalar()

    print("F32 hygienist-leak cleanup — pre-cleanup counts")
    print("-" * 56)
    print(f"  practices (global):           {counts['practices_total']:>8,}")
    print(f"  practices (watched ZIPs):     {counts['practices_watched']:>8,}")
    print(f"  practice_changes dep rows:    {counts['practice_changes_dep']:>8,}")
    print(f"  practice_intel dep rows:      {counts['practice_intel_dep']:>8,}")
    print(f"  practice_signals dep rows:    {counts['practice_signals_dep']:>8,}")
    print()

    if not args.execute:
        print("DRY-RUN. No rows deleted. Re-run with --execute to apply.")
        return 0

    if counts["practices_total"] == 0:
        print("No leak rows found. Nothing to do.")
        return 0

    print("Executing DELETEs...")
    from sqlalchemy import text

    npis_subquery = (
        f"SELECT npi FROM practices WHERE {leak_filter_sql}"
    )
    deleted = {}
    for dep_table in ("practice_signals", "practice_intel", "practice_changes"):
        result = session.execute(
            text(f"DELETE FROM {dep_table} WHERE npi IN ({npis_subquery})")
        )
        deleted[dep_table] = result.rowcount or 0
        print(f"  {dep_table}: {deleted[dep_table]:>8,} deleted")

    result = session.execute(
        text(f"DELETE FROM practices WHERE {leak_filter_sql}")
    )
    deleted["practices"] = result.rowcount or 0
    print(f"  practices:        {deleted['practices']:>8,} deleted")

    session.commit()
    print()
    print("Cleanup complete. Recommended next steps:")
    print("  1. python3 scrapers/sync_to_supabase.py --tables practices")
    print("  2. python3 scripts/check_data_invariants.py  (F02 should now pass)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
