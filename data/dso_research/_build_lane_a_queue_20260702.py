"""Build the Lane A research queue (2026-07-02, Fable PM).

Takes the 2026-06-20 per-ZIP census batches (rich per-practice context:
AO reach, EIN reach, brand hints, intel flag) and re-filters them against
LIVE DB state after the first consolidation write:
  - drop rows already tiered (343 classified 2026-07-02)
  - drop the 6 adjudicated holds
  - drop DA_/DIR_ synthetic-NPI rows (validator refuses them as final;
    they belong to the scope-correction queue)
  - drop R5 mark_likely_closed rows (census never classifies these
    unless PM-adjudicated — GP_SCOPE_POLICY R5, ratified)
Then chunks into work units of <=16 practices for agent dispatch.

Output: data/dso_research/_lane_a_20260702/unit_NNN.json
"""
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
OUT = os.path.join(HERE, "_lane_a_20260702")
UNIT_SIZE = 16

batches = json.load(open(os.path.join(HERE, "census_batches_remaining_20260621.json")))["batches"]
holds = json.load(open(os.path.join(HERE, "_census_holds_20260702.json")))
hold_ids = {h["location_id"] for h in (holds if isinstance(holds, list) else holds.get("holds", []))}
closure = json.load(open(os.path.join(HERE, "closure_candidates_review_20260702.json")))
closed_ids = set()
for v in (closure.values() if isinstance(closure, dict) else [closure]):
    if isinstance(v, list) and v and isinstance(v[0], dict) and "location_id" in v[0]:
        closed_ids = {r["location_id"] for r in v if r.get("proposed_action") == "mark_likely_closed"}
        break

c = sqlite3.connect(DB)
tiered = {r[0] for r in c.execute(
    "SELECT location_id FROM practice_locations WHERE ownership_tier IS NOT NULL")}

kept, drop = [], {"already_tiered": 0, "hold": 0, "synthetic_npi": 0, "closure_r5": 0}
for b in batches:
    for p in b["practices"]:
        lid = p["location_id"]
        if lid in tiered:
            drop["already_tiered"] += 1
        elif lid in hold_ids:
            drop["hold"] += 1
        elif str(p.get("primary_npi") or "").startswith(("DA_", "DIR_")) or \
                str(p.get("org_npi") or "").startswith(("DA_", "DIR_")):
            drop["synthetic_npi"] += 1
        elif lid in closed_ids:
            drop["closure_r5"] += 1
        else:
            p["_zip_city"] = f"{b['zip']} {b['city']}"
            kept.append(p)

os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    os.remove(os.path.join(OUT, f))
units = [kept[i:i + UNIT_SIZE] for i in range(0, len(kept), UNIT_SIZE)]
for i, u in enumerate(units, 1):
    json.dump({"unit_id": f"laneA_{i:03d}", "practices": u},
              open(os.path.join(OUT, f"unit_{i:03d}.json"), "w"), indent=1)

print(f"kept {len(kept)} practices -> {len(units)} units of <= {UNIT_SIZE}")
print("dropped:", drop)
print("out dir:", OUT)
