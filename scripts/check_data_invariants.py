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
    expect_min: int = 0  # min rows REQUIRED; >0 turns this into a floor guard
                         # (FAIL/WARN when count < expect_min). Use for the
                         # corporate-floor regression guard, where the danger is
                         # a count DROPPING, not growing.


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
    Invariant(
        id="FLOOR",
        description=(
            "Confirmed corporate GP-location floor never regresses below the "
            "2026-06-19 documented 268 (dso_regional+dso_national in "
            "practice_locations). Guards the verified promotions (friendly-PC, "
            "IL-DSO-seed, Phase-4 Data-Axle) against a refresh silently "
            "reverting them, NET of the 2026-06-12 false-corporate demotions, "
            "Data-Axle junk purge, and 2026-06-19 duplicate-location cleanup."
        ),
        path="practice_locations?entity_classification=in.(dso_regional,dso_national)&select=location_id",
        expect_max=99999,         # no upper bound — growth is fine/expected
        expect_min=268,           # FAIL if it ever drops below the documented floor
        severity="fail",
        note=(
            "FLOOR GUARD: 268 (2026-06-19 locator/PC exact-match promotions; "
            "was 254 after 2026-06-12 round 2, 261 round 1 same day, "
            "285 at 2026-06-07, 262 at 2026-05-30). Round-1 -18: false-corporate "
            "DEMOTIONS (Evenly parent_iusa='000000000' placeholder linkage, "
            "landlord-name confusion, bad seed addresses; audit "
            "data/dso_research/il_false_corporate_demotions_20260612.json) plus "
            "-6 Data-Axle JUNK PURGE (cleanup_data_axle_junk.py, audit "
            "data/dso_research/da_junk_cleanup_20260612.json). Round-2 -7: "
            "web-verified false positives (franchise-name collision, PE-fund-as-"
            "landlord confusion, specialist misclass; audit "
            "data/dso_research/il_false_corporate_demotions_round2_20260612.json). "
            "reclassify_verified_corporate_il.py EXCLUDES every demoted "
            "location_id (globs il_false_corporate_demotions_*.json) from "
            "re-promotion. The 262 floor empirically survived the 2026-06-01 "
            "NPPES refresh; the 285 floor survived a full merge_and_score "
            "recompute. 2026-06-19 exact-match cleanup/promotions are audited in "
            "data/dso_research/duplicate_location_cleanup_20260619.json and "
            "data/dso_research/il_verified_locator_promotions_20260619.json. "
            "A DROP below 268 means a pipeline step reverted the "
            "promotions — re-run scrapers/reclassify_verified_corporate_il.py + "
            "re-sync floor tables. A RISE is healthy (further verified "
            "confirmations landing). A read ABOVE 268 pre-sync just means "
            "Supabase hasn't received the latest promotions yet — sync floor tables."
        ),
    ),
    Invariant(
        id="CENSUS",
        description=(
            "Hand-verified ownership-census coverage never regresses below the "
            "2026-07-04 Lane A wave-1 landing: 3,180 practice_locations rows "
            "with ownership_tier NOT NULL (T1 1,471 / T2 934 / T3 537 / T4 28 / "
            "T5 151 / T6 59; pe_backed 118)."
        ),
        path="practice_locations?ownership_tier=not.is.null&select=location_id",
        expect_max=99999,         # growth is expected as the census continues
        expect_min=3180,          # FAIL if the census layer shrinks
        severity="fail",
        note=(
            "CENSUS GUARD: ownership_tier is a SEPARATE axis from the detector "
            "floor (entity_classification) — written ONLY by "
            "scrapers/consolidate_census.py, synced by "
            "scrapers/_sync_floor_tables_only.py (practice_locations rides the "
            "ORM full_replace). A DROP below 3,180 means either (a) the census "
            "columns were un-mapped from the ORM in scrapers/database.py "
            "(the silent sync-strip bug — restore the Column definitions, see "
            "PROOF_ORM_SYNC_MIGRATION_20260702.md) or (b) a sync ran from a "
            "SQLite DB that lost the census write — restore from "
            "data/backups/dental_pe_tracker_pre_census_write_20260704.db "
            "lineage and re-run both sync legs. SQLite ground truth: LEDGER + "
            "result files under data/dso_research/RESEARCH_HOME/. A RISE is "
            "healthy (census continuation waves landing)."
        ),
    ),
    Invariant(
        id="CENSUS_NPI",
        description=(
            "Census NPI mirror never regresses below the 2026-07-04 landing: "
            "6,754 practices rows with ownership_tier NOT NULL "
            "(true_independent 1,810 / single_loc_group 2,624 / dentist_multi "
            "1,370 / stealth_dso 94 / branded_dso 604 / institutional 252)."
        ),
        path="practices?ownership_tier=not.is.null&select=npi",
        expect_max=99999,
        expect_min=6754,
        severity="fail",
        note=(
            "CENSUS NPI GUARD: the practices-side census mirror is synced by "
            "the surgical scrapers/_sync_census_columns_practices.py AND rides "
            "the weekly full sync's watched_zips_only TRUNCATE+reinsert "
            "(column list comes from the ORM model — census cols must stay "
            "mapped in scrapers/database.py). NOTE: "
            "_sync_practices_changed_rows.py does NOT carry census columns — "
            "it cannot cause a drop by itself, but it also cannot repair one. "
            "A DROP below 6,754 after a weekly sync = the ORM strip bug "
            "re-opened; fix database.py, then re-run "
            "python3 -m scrapers._sync_census_columns_practices."
        ),
    ),
    Invariant(
        id="FLOOR_NPI",
        description=(
            "Corporate NPI rows in live `practices` never regress below the "
            "2026-06-19 documented 1,152 (post false-corporate demotion "
            "rounds 1+2, Data-Axle junk purge, duplicate cleanup, and verified "
            "locator/PC promotions). "
            "Guards against the live NPI-level classification going stale "
            "relative to SQLite truth."
        ),
        path="practices?entity_classification=in.(dso_regional,dso_national)&select=npi",
        expect_max=99999,         # no upper bound — growth is fine/expected
        expect_min=1152,
        severity="fail",
        note=(
            "NPI FLOOR GUARD: 1,152 = the 268 corporate locations' underlying "
            "NPI rows (Supabase `practices` holds only the 13,818 watched rows). "
            "2026-06-12 round 1: was 1,178; demote_false_corporate_il.py flipped "
            "52 false-corporate NPIs back to independent (audit: "
            "data/dso_research/il_false_corporate_demotions_20260612.json) and "
            "cleanup_data_axle_junk.py flipped 7 more DA_-synthetic corporate "
            "rows to da_unverified (audit: "
            "data/dso_research/da_junk_cleanup_20260612.json) -> 1,119. "
            "Round 2 same day: demote_false_corporate_round2.py flipped 15 more "
            "(7 false-corporate locations' NPIs + specialist reclasses; audit: "
            "data/dso_research/il_false_corporate_demotions_round2_20260612.json) "
            "-> 1,104. 2026-06-19 duplicate cleanup + exact-match locator/PC "
            "promotions added 49 corporate NPI rows -> 1,152. History: on "
            "2026-06-10 live was found stale at 1,089 — "
            "the Phase-4 flips in reclassify_verified_corporate_il.py updated "
            "practices WITHOUT bumping updated_at (raw SQL bypasses the ORM "
            "onupdate); root-fixed the same day. A DROP below 1,152 means either "
            "a classifier reverted NPI flips (re-run "
            "scrapers/reclassify_verified_corporate_il.py) or a stale practices "
            "sync — re-sync with: python3 scrapers/sync_to_supabase.py (full "
            "weekly path). A read ABOVE 1,152 pre-sync just means Supabase "
            "hasn't received the latest promotions yet."
        ),
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
        elif inv.expect_min and 0 <= count < inv.expect_min:
            # Floor guard: a count that DROPPED below the required minimum.
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
