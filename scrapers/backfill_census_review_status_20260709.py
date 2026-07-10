"""
P5 census-recovery review-status backfill (2026-07-09) — the second leg of the
split write (see data/dso_research/_census_recovery_20260709/
split_for_write_20260709.py for the decision record).

Runs AFTER consolidate_census.py has written the 512 real-tier rows.

Two moves, both on practice_locations.census_review_status only:
  1. SET   — the 747 researched-inconclusive rows from
             review_status_plan_20260709.json get 'undetermined' (742) or
             'held' (5 needs_verification / R4 holds). Guard: only where
             ownership_tier IS NULL (tier always wins).
  2. CLEAR — rows that just EARNED a tier in this write and still carry a
             stale pre-recovery status (§6n design: "count drops as rows earn
             tiers"). Guard: only where ownership_tier IS NOT NULL.

Expected end state (whole DB):
  census_review_status: undetermined=742, held=5, NULL=everything else
  status∧tier overlap = 0
  ownership_tier NOT NULL = 3,692   (3,180 + 512)
  detector floor untouched: 268 corp locations
  IL GP rows with neither tier nor status = 0 (universe fully dispositioned)

Never touches ownership_tier / entity_classification / any other column
except census_review_status + updated_at. Idempotent. Evidence JSON:
data/dso_research/census_review_status_backfill_20260709.json

SQLite only — Supabase receives the column via leg-1
(`python3 -m scrapers._sync_floor_tables_only`), then read back.
"""
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
RECOVERY = os.path.join(ROOT, "data", "dso_research", "_census_recovery_20260709")
PLAN = os.path.join(RECOVERY, "review_status_plan_20260709.json")
REAL = os.path.join(RECOVERY, "write_real_tiers_20260709.json")
EVIDENCE = os.path.join(ROOT, "data", "dso_research",
                        "census_review_status_backfill_20260709.json")

plan = json.load(open(PLAN))
set_rows = {p["location_id"]: p for p in plan["rows"]}
real_rows = json.load(open(REAL))
clear_ids = [r["location_id"] for r in real_rows]

planned = Counter(p["census_review_status"] for p in set_rows.values())
print(f"Planned SET: {dict(planned)} (total {len(set_rows)}) | "
      f"CLEAR candidates: {len(clear_ids)} (only where a stale status exists)")

conn = sqlite3.connect(DB)

def fetch(ids):
    ph = ",".join("?" * len(ids))
    return {r[0]: (r[1], r[2]) for r in conn.execute(
        f"SELECT location_id, ownership_tier, census_review_status "
        f"FROM practice_locations WHERE location_id IN ({ph})", ids)}

set_db = fetch(list(set_rows))
clear_db = fetch(clear_ids)

set_missing = [i for i in set_rows if i not in set_db]
set_tiered = [i for i in set_rows if i in set_db and set_db[i][0] is not None]
set_targets = [i for i in set_rows if i in set_db and set_db[i][0] is None]

clear_untiered = [i for i in clear_ids if i in clear_db and clear_db[i][0] is None]
clear_targets = [i for i in clear_ids
                 if i in clear_db and clear_db[i][0] is not None
                 and clear_db[i][1] is not None]

print(f"SET check: {len(set_targets)} writable / {len(set_tiered)} skipped-tiered / "
      f"{len(set_missing)} missing")
print(f"CLEAR check: {len(clear_targets)} stale statuses to clear / "
      f"{len(clear_untiered)} UNTIERED real-tier rows (must be 0 — consolidate ran?)")
if set_missing or set_tiered or clear_untiered:
    print("ABORT-LEVEL ANOMALY — every set-target must be untiered, every "
          "clear-candidate must be tiered (run consolidate first).")

now = datetime.now(timezone.utc).isoformat()
applied_set = Counter()
applied_clear = 0
prior_status = {}
with conn:
    for lid in set_targets:
        prior_status[lid] = set_db[lid][1]
        conn.execute(
            "UPDATE practice_locations SET census_review_status=?, updated_at=? "
            "WHERE location_id=? AND ownership_tier IS NULL",
            (set_rows[lid]["census_review_status"], now, lid))
        applied_set[set_rows[lid]["census_review_status"]] += 1
    for lid in clear_targets:
        prior_status[lid] = clear_db[lid][1]
        conn.execute(
            "UPDATE practice_locations SET census_review_status=NULL, updated_at=? "
            "WHERE location_id=? AND ownership_tier IS NOT NULL", (now, lid))
        applied_clear += 1

final = dict(conn.execute(
    "SELECT census_review_status, COUNT(*) FROM practice_locations "
    "WHERE census_review_status IS NOT NULL GROUP BY 1").fetchall())
cross = conn.execute(
    "SELECT COUNT(*) FROM practice_locations WHERE census_review_status IS NOT NULL "
    "AND ownership_tier IS NOT NULL").fetchone()[0]
tier_count = conn.execute(
    "SELECT COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL"
).fetchone()[0]
floor = conn.execute(
    "SELECT COUNT(*) FROM practice_locations WHERE entity_classification IN "
    "('dso_regional','dso_national')").fetchone()[0]
GP = ("solo_established", "solo_new", "solo_inactive", "solo_high_volume",
      "family_practice", "small_group", "large_group", "dso_regional", "dso_national")
undispositioned = conn.execute(
    f"SELECT COUNT(*) FROM practice_locations WHERE state='IL' "
    f"AND (is_likely_residential=0 OR is_likely_residential IS NULL) "
    f"AND entity_classification IN ({','.join('?'*len(GP))}) "
    f"AND ownership_tier IS NULL AND census_review_status IS NULL", GP).fetchone()[0]

print(f"Applied: SET {dict(applied_set)} | CLEAR {applied_clear}")
print(f"DB now: {final} | status∧tier rows (must be 0): {cross}")
print(f"Tiered locations {tier_count} (expect 3692) | detector floor {floor} (expect 268)")
print(f"IL GP rows with neither tier nor status (expect 0): {undispositioned}")

evidence = {
    "_meta": {
        "script": "scrapers/backfill_census_review_status_20260709.py",
        "run_at": now,
        "sources": {
            "plan": os.path.relpath(PLAN, ROOT),
            "real_tier_file": os.path.relpath(REAL, ROOT),
            "banked_recovery": "data/dso_research/_census_recovery_20260709/"
                               "merged_1259_rows.json (e01c741)",
        },
        "value_contract": "held | undetermined | NULL (ownership-truth.ts deriveSourceClass)",
        "planned_set": dict(planned),
        "applied_set": dict(applied_set),
        "applied_clear": applied_clear,
        "set_skipped_tiered": set_tiered,
        "set_missing": set_missing,
        "clear_candidates_untiered": clear_untiered,
        "db_final_tallies": final,
        "invariants": {
            "status_and_tier_overlap": cross,
            "tiered_locations": tier_count,
            "detector_floor_corp_locations": floor,
            "il_gp_undispositioned": undispositioned,
        },
    },
    "set_rows": [
        {"location_id": lid,
         "census_review_status": set_rows[lid]["census_review_status"],
         "prior_status": prior_status.get(lid),
         "reason": set_rows[lid]["reason"],
         "banked_network_id": set_rows[lid]["banked_network_id"],
         "banked_pe_backed": set_rows[lid]["banked_pe_backed"]}
        for lid in sorted(set_targets)
    ],
    "cleared_rows": [
        {"location_id": lid, "prior_status": prior_status.get(lid),
         "reason": "earned ownership_tier in fable_p5_census_recovery_20260709"}
        for lid in sorted(clear_targets)
    ],
}
json.dump(evidence, open(EVIDENCE, "w"), indent=1)
print(f"Evidence written: {os.path.relpath(EVIDENCE, ROOT)}")

ok = (cross == 0 and not set_missing and not set_tiered and not clear_untiered
      and tier_count == 3692 and floor == 268 and undispositioned == 0
      and dict(applied_set if applied_set else planned) is not None
      and final.get("undetermined") == 742 and final.get("held") == 5)
print("RESULT:", "OK" if ok else "CHECK FAILED — do not sync")
sys.exit(0 if ok else 1)
