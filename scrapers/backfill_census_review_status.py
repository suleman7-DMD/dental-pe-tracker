"""
Backfill `practice_locations.census_review_status` (2026-07-04) from the two
local truth files that define the census review queue:

  data/dso_research/_lane_a_triage_wave1_20260702.json   (649 rows)
      _triage_reason == 'undetermined_by_agent'  -> 'undetermined'  (477)
      every other _triage_reason                 -> 'held'          (172)
  data/dso_research/_census_holds_20260702.json          (7 PM holds)
      all                                        -> 'held'
      (1 overlaps the triage file; 6 are additive -> expected held = 178)

Expected result: 477 undetermined + 178 held = 655 non-NULL rows.

Guards:
  - NEVER touches ownership_tier, entity_classification, or any other column
    except census_review_status + updated_at.
  - Skips (and reports) any target row whose ownership_tier IS NOT NULL —
    tier wins; status is only meaningful on untiered rows.
  - Skips (and reports) location_ids missing from practice_locations.
  - Idempotent: re-running produces the same end state.
  - Evidence JSON written to
    data/dso_research/census_review_status_backfill_20260704.json

SQLite only. Supabase receives the column via the leg-1 ORM full_replace
(`python3 -m scrapers._sync_floor_tables_only`) — run that after this script
(human-gated), then read back.
"""
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
TRIAGE = os.path.join(ROOT, "data", "dso_research", "_lane_a_triage_wave1_20260702.json")
HOLDS = os.path.join(ROOT, "data", "dso_research", "_census_holds_20260702.json")
EVIDENCE = os.path.join(ROOT, "data", "dso_research",
                        "census_review_status_backfill_20260704.json")

triage = json.load(open(TRIAGE))
holds_raw = json.load(open(HOLDS))["holds"]

status_by_id = {}
reason_by_id = {}
for row in triage:
    lid = row["location_id"]
    reason = row.get("_triage_reason") or "unknown"
    status = "undetermined" if reason == "undetermined_by_agent" else "held"
    status_by_id[lid] = status
    reason_by_id[lid] = f"triage:{reason}"
for h in holds_raw:
    lid = h["location_id"]
    # PM hold outranks a triage-derived status
    status_by_id[lid] = "held"
    reason_by_id[lid] = f"pm_hold:{h.get('hold_reason', 'unspecified')}"

planned = Counter(status_by_id.values())
print(f"Planned: {dict(planned)}  (total {len(status_by_id)})")

conn = sqlite3.connect(DB)
ids = list(status_by_id)
ph = ",".join("?" * len(ids))
db_rows = {r[0]: r[1] for r in conn.execute(
    f"SELECT location_id, ownership_tier FROM practice_locations "
    f"WHERE location_id IN ({ph})", ids).fetchall()}

missing = [i for i in ids if i not in db_rows]
tiered = [i for i in ids if db_rows.get(i) is not None]
targets = [i for i in ids if i in db_rows and db_rows[i] is None]
print(f"DB check: {len(targets)} writable / {len(tiered)} skipped-tiered / "
      f"{len(missing)} missing")
if missing:
    print("  MISSING:", missing[:10])
if tiered:
    print("  SKIPPED (already tiered):", tiered[:10])

now = datetime.now(timezone.utc).isoformat()
applied = Counter()
with conn:
    for lid in targets:
        conn.execute(
            "UPDATE practice_locations SET census_review_status = ?, "
            "updated_at = ? WHERE location_id = ? AND ownership_tier IS NULL",
            (status_by_id[lid], now, lid))
        applied[status_by_id[lid]] += 1

# Post-write verification straight from the DB
final = dict(conn.execute(
    "SELECT census_review_status, COUNT(*) FROM practice_locations "
    "WHERE census_review_status IS NOT NULL GROUP BY 1").fetchall())
cross = conn.execute(
    "SELECT COUNT(*) FROM practice_locations "
    "WHERE census_review_status IS NOT NULL AND ownership_tier IS NOT NULL"
).fetchone()[0]
tier_count = conn.execute(
    "SELECT COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL"
).fetchone()[0]
floor = conn.execute(
    "SELECT COUNT(*) FROM practice_locations WHERE entity_classification IN "
    "('dso_regional','dso_national')").fetchone()[0]
print(f"Applied: {dict(applied)}")
print(f"DB now:  {final}  | status∧tier rows (must be 0): {cross}")
print(f"Untouched checks: tiered locations {tier_count} (expect 3180) | "
      f"detector floor {floor} (expect 268)")

evidence = {
    "_meta": {
        "script": "scrapers/backfill_census_review_status.py",
        "run_at": now,
        "sources": {
            "triage": os.path.relpath(TRIAGE, ROOT),
            "pm_holds": os.path.relpath(HOLDS, ROOT),
        },
        "value_contract": "held | undetermined | NULL "
                          "(ownership-truth.ts deriveSourceClass)",
        "planned": dict(planned),
        "applied": dict(applied),
        "skipped_already_tiered": tiered,
        "missing_from_db": missing,
        "db_final_tallies": final,
        "invariants": {
            "status_and_tier_overlap": cross,
            "tiered_locations": tier_count,
            "detector_floor_corp_locations": floor,
        },
    },
    "rows": [
        {"location_id": lid, "census_review_status": status_by_id[lid],
         "reason": reason_by_id[lid]}
        for lid in sorted(status_by_id)
    ],
}
json.dump(evidence, open(EVIDENCE, "w"), indent=1)
print(f"Evidence written: {os.path.relpath(EVIDENCE, ROOT)}")

ok = (cross == 0 and not missing and tier_count == 3180 and floor == 268)
print("RESULT:", "OK" if ok else "CHECK FAILED — do not sync")
sys.exit(0 if ok else 1)
