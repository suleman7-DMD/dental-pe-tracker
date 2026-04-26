"""
F28 — Data invariant check.

Runs the verification queries from IMPLEMENTATION_PLAN_2026_04_26.md against
Supabase and exits non-zero if any invariant is violated. Designed to be run
as a weekly GitHub Actions cron.

Auth: hits Supabase via PostgREST with the anon key (sufficient for read-only
count + select queries on the public schema). Endpoints that need service_role
(e.g. reading pg_constraint for F11) are skipped here and called out in the
report header — verify those manually.

Each invariant has:
  - id (matches the F## from the plan)
  - description (human-readable)
  - query (PostgREST URL fragment)
  - threshold (how many rows count as "broken")

Output is a markdown report on stdout PLUS a non-zero exit code on any FAIL.
WARN-level invariants (data not yet shipped per the plan) print but don't
fail the job — the workflow downstream surfaces them as ::warning:: lines.
"""
from __future__ import annotations

import os
import sys
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("FATAL: SUPABASE_URL and SUPABASE_ANON_KEY must be set", file=sys.stderr)
    sys.exit(2)


@dataclass
class Invariant:
    id: str
    description: str
    path: str            # PostgREST path + query string (no leading slash)
    expect_max: int      # max rows allowed; 0 means "must be empty"
    severity: str        # "fail" or "warn"
    note: str = ""


# Each invariant uses PostgREST `count=exact` via the `Prefer` header so we
# get a Content-Range count without pulling row bodies.
INVARIANTS: list[Invariant] = [
    Invariant(
        id="F02",
        description="No NPPES rows with non-1223 taxonomy_code (hygienist leak guard)",
        path="practices?taxonomy_code=not.like.1223%25&data_source=eq.nppes&select=npi",
        expect_max=0,
        severity="fail",
    ),
    Invariant(
        id="F07a",
        description="practice_intel.verification_quality is in {verified,partial,insufficient,NULL}",
        # We can't easily express "NOT IN" in PostgREST URL syntax across all
        # drivers, so query non-null + non-canonical values and expect 0.
        # Use `verification_quality=not.is.null` plus three "neq" filters.
        path=(
            "practice_intel?"
            "verification_quality=not.is.null&"
            "verification_quality=neq.verified&"
            "verification_quality=neq.partial&"
            "verification_quality=neq.insufficient&"
            "select=npi"
        ),
        expect_max=0,
        severity="fail",
    ),
    Invariant(
        id="F01",
        description="practice_locations.entity_classification is never NULL after dc18d24 dedup",
        path="practice_locations?entity_classification=is.null&select=location_id",
        expect_max=0,
        severity="fail",
    ),
    Invariant(
        id="F06",
        description="zip_signals is populated in Supabase (290 watched ZIPs)",
        path="zip_signals?select=zip_code",
        expect_max=99999,  # we want >= 1; encoded below as min check
        severity="warn",
        note="WARN: as of 2026-04-26 zip_signals=0 in Supabase (sync gap). Re-run sync when fixed.",
    ),
    Invariant(
        id="F05",
        description="DA_-prefix synthetic NPI dossiers all have verification_searches",
        path=(
            "practice_intel?npi=like.DA%5C_%25&verification_searches=is.null&select=npi"
        ),
        expect_max=0,
        severity="warn",
        note="WARN: until F05 batch lands, the 186 DA_-prefix rows are unverified by design.",
    ),
    Invariant(
        id="watched_zips",
        description="watched_zips contains 290 rows (269 IL + 21 MA)",
        path="watched_zips?select=zip_code",
        expect_max=99999,
        severity="warn",
        note="Reports actual count; flags only if dramatically off (handled in driver below).",
    ),
]


def fetch_count(path: str) -> tuple[int, Optional[str]]:
    """Run a PostgREST query with count=exact. Returns (row_count, error)."""
    url = f"{SUPABASE_URL}/rest/v1/{path}&limit=1"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Prefer": "count=exact",
            "Range-Unit": "items",
            "Range": "0-0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range:
                total = content_range.split("/")[-1]
                if total.isdigit():
                    return int(total), None
            return 0, f"unexpected Content-Range: {content_range!r}"
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", errors="replace")
        return -1, f"HTTP {e.code}: {body}"
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def main() -> int:
    print("# F28 Data Invariant Report")
    print(f"\nSupabase URL: `{SUPABASE_URL}`\n")
    print("| ID | Status | Severity | Count | Description |")
    print("|----|--------|----------|------:|-------------|")

    failures = 0
    warnings = 0

    for inv in INVARIANTS:
        count, err = fetch_count(inv.path)
        if err:
            status = "ERROR"
            display_count = "—"
            failures += 1
        elif inv.id in ("F06", "watched_zips") and count == 0:
            status = "WARN" if inv.severity == "warn" else "FAIL"
            display_count = str(count)
            if inv.severity == "fail":
                failures += 1
            else:
                warnings += 1
        elif inv.severity == "warn" and count > inv.expect_max:
            status = "WARN"
            display_count = str(count)
            warnings += 1
        elif count > inv.expect_max:
            status = "FAIL"
            display_count = str(count)
            failures += 1
        else:
            status = "PASS"
            display_count = str(count)

        print(f"| {inv.id} | {status} | {inv.severity} | {display_count} | {inv.description} |")
        if err:
            print(f"|    | (error) | | | `{err}` |")
        if inv.note and status != "PASS":
            print(f"|    | (note) | | | {inv.note} |")

    print()
    print(f"**Summary:** {failures} failure(s), {warnings} warning(s)")
    print()
    print(
        "Note: F11 (`practice_changes_npi_fkey ON DELETE` policy) requires "
        "`service_role` access to `pg_constraint` and is NOT checked here. "
        "Verify manually in the Supabase SQL editor."
    )

    return 1 if failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
