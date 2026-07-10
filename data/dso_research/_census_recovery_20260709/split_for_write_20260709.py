"""
Split the banked 1,259-row census recovery file (merged_1259_rows.json,
commit e01c741) into the two write legs of the P5 close-out:

  1. write_real_tiers_20260709.json  — rows whose assigned_tier is one of the
     six REAL tiers (512 = 488 status=classified + 24 tier-with-status=
     undetermined per DECISIONS_PM_20260709.md line 63 "valid combo; tier is
     written"). This file goes through scrapers/consolidate_census.py
     (validate-only → --allow-db-write), exactly as every prior census write.

  2. review_status_plan_20260709.json — rows whose assigned_tier ==
     'undetermined' (747 = 742 status=undetermined + 5 status=
     needs_verification). These do NOT get an ownership_tier write. Instead
     they get practice_locations.census_review_status via
     scrapers/backfill_census_review_status_20260709.py:
         status=needs_verification -> 'held'          (R4/procedural holds)
         everything else           -> 'undetermined'  (researched, inconclusive)

WHY THE SPLIT (decision record, Fable PM 2026-07-09):
  consolidate_census.py's VALID_TIERS includes 'undetermined', so passing the
  whole banked file would stamp ownership_tier='undetermined' onto 747 rows —
  a 7th tier value that has never existed in the DB. That would break the
  repo-wide convention "ownership_tier IS NOT NULL == earned a tier" used by:
    - the CENSUS CI guard (scripts/check_data_invariants.py,
      path ownership_tier=not.is.null, expect_min),
    - the drift-check claims manifest and the dental-pe skills' §2 recheck
      queries,
    - the frontend contract (ownership-truth.ts isOwnershipTier /
      OWNERSHIP_TIERS = the six real tiers; 'undetermined' would fall through
      to 'unreviewed' unless census_review_status is set anyway),
    - the plan's own stated outcome (PLAN_PRODUCT_RESET §7: "moves coverage
      3,180 → ~3,668" — only true if real tiers alone are written).
  Wave 1 (2026-07-02/04) set the precedent: undetermined research results went
  to census_review_status via a dated backfill (+ evidence JSON), never into
  ownership_tier. This split follows it exactly.

  Not persisted to the DB for the 747 (recorded in the plan file instead):
  network_id on 35 rows and pe_backed=True on 5 rows (incl. the two Aspen R4
  procedural holds). Writing network/pe facts onto tier-less rows would
  front-run the R4 one-network-one-decision rulings; the banked JSON keeps
  them recoverable.

Deterministic, read-only w.r.t. the banked file. Re-run safe.
"""
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "merged_1259_rows.json")
OUT_REAL = os.path.join(HERE, "write_real_tiers_20260709.json")
OUT_PLAN = os.path.join(HERE, "review_status_plan_20260709.json")

REAL_TIERS = {"true_independent", "single_loc_group", "dentist_multi",
              "stealth_dso", "branded_dso", "institutional"}

rows = json.load(open(SRC))
assert isinstance(rows, list) and len(rows) == 1259, f"unexpected source shape: {len(rows)}"

real = [r for r in rows if r.get("assigned_tier") in REAL_TIERS]
und = [r for r in rows if r.get("assigned_tier") == "undetermined"]
assert len(real) + len(und) == len(rows), "partition must be exhaustive"
assert len(real) == 512, f"expected 512 real-tier rows, got {len(real)}"
assert len(und) == 747, f"expected 747 undetermined rows, got {len(und)}"

json.dump(real, open(OUT_REAL, "w"), indent=1)

plan_rows = []
for r in und:
    new_status = "held" if r.get("status") == "needs_verification" else "undetermined"
    plan_rows.append({
        "location_id": r["location_id"],
        "census_review_status": new_status,
        "source_status": r.get("status"),
        "reason": ("needs_verification->held (R4/procedural or successor-practice hold)"
                   if new_status == "held" else
                   "researched via recovery protocol, evidence inconclusive"),
        # banked-not-written: kept out of the DB pending an earned tier / R4 ruling
        "banked_network_id": r.get("network_id"),
        "banked_pe_backed": r.get("pe_backed"),
        "confidence": r.get("confidence"),
        "reasoning": r.get("reasoning"),
        "evidence_urls": r.get("evidence_urls") or [],
    })

plan = {
    "_meta": {
        "source": "data/dso_research/_census_recovery_20260709/merged_1259_rows.json (e01c741)",
        "generator": "split_for_write_20260709.py",
        "partition": {"real_tier_rows": len(real), "undetermined_rows": len(und)},
        "status_map": {"needs_verification": "held", "undetermined": "undetermined"},
        "planned": dict(Counter(p["census_review_status"] for p in plan_rows)),
        "banked_not_written": {
            "network_id_rows": sum(1 for p in plan_rows if p["banked_network_id"]),
            "pe_backed_true_rows": sum(1 for p in plan_rows if p["banked_pe_backed"] is True),
            "note": "network_id/pe_backed on undetermined rows stay in this file, not the DB "
                    "(R4 one-network-one-decision; no ownership facts on tier-less rows)",
        },
    },
    "rows": plan_rows,
}
json.dump(plan, open(OUT_PLAN, "w"), indent=1)

print(f"real-tier file : {os.path.basename(OUT_REAL)}  rows={len(real)} "
      f"tiers={dict(Counter(r['assigned_tier'] for r in real))}")
print(f"status plan    : {os.path.basename(OUT_PLAN)}  rows={len(plan_rows)} "
      f"planned={plan['_meta']['planned']}")
