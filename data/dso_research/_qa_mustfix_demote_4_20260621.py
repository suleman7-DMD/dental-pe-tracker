#!/usr/bin/env python3
"""
QA MUST-FIX (pre-Wave-3): demote 4 rows ready_to_validate -> needs_more_evidence.
QA found they self-flag as candidate / closed / operating-status-unverified
(active-door status that consolidate_census.py --validate-only cannot catch).
Preserves the full original ready row + per-location DB facts as intelligence.
NO DB writes. Regenerates the validator-native ready file.
"""
import json, os
R="data/dso_research"
def L(p):
    with open(os.path.join(R,p)) as f: return json.load(f)
def dump(p,obj):
    with open(os.path.join(R,p),"w") as f: json.dump(obj,f,indent=1)

DEMOTE={"1fa86e6647cd57c5","b184f060d46970cd","e493e4371bb5cb22","d5bc28878405a18c"}
DBFACTS={  # location_id -> (name, city, zip, entity_classification)
 "1fa86e6647cd57c5":("VALLEY VIEW DENTAL GROUP LLC","DOWNERS GROVE","60515","solo_established"),
 "b184f060d46970cd":("SPARKLE DENTAL GROUP LLC","LEMONT","60439","solo_established"),
 "e493e4371bb5cb22":("SPARKLE DENTAL GROUP LLC","DOWNERS GROVE","60515","solo_high_volume"),
 "d5bc28878405a18c":("MODERN DENTAL ON SHEFFIELD","CHICAGO","60657","solo_established"),
}
QA_REASON=("QA MUST-FIX 2026-06-21: self-flags as candidate / closed / operating-status-unverified. "
           "Active-door operating status is NOT verifiable by consolidate_census.py --validate-only "
           "(schema/DB-state only). Held in needs_more_evidence pending an operating-status corroborator "
           "(live website address match / current locator listing / phone-active confirmation).")

man=L("consolidation_candidate_manifest_20260621.json"); B=man["buckets"]
ready=B["ready_to_validate"]
demoted_rows=[r for r in ready if r["location_id"] in DEMOTE]
assert {r["location_id"] for r in demoted_rows}==DEMOTE, "not all 4 targets found in ready"

# keep ready minus the 4
B["ready_to_validate"]=[r for r in ready if r["location_id"] not in DEMOTE]

# build needs_more_evidence entries (nme schema) preserving the original ready row verbatim
nme_ids={r["location_id"] for r in B["needs_more_evidence"]}
for r in demoted_rows:
    lid=r["location_id"]; nm,city,zp,ec=DBFACTS[lid]
    if lid in nme_ids: continue
    B["needs_more_evidence"].append({
        "location_id":lid,"name":nm,"zip":zp,"city":city,"state":"IL",
        "entity_classification":ec,
        "nets":[r.get("network_id")] if r.get("network_id") else [],
        "sources":["qa_mustfix_demotion_20260621"],
        "final_tier":r.get("assigned_tier"),
        "reason":QA_REASON,
        "demoted_from_ready":True,
        "backfill_lane":"operating_status_unverified",
        "preserved_ready_row":r,   # full original 10-key row kept verbatim (future-app intelligence)
    })

# record the action
man.setdefault("qa_mustfix_actions",[]).append({
    "at":"2026-06-21","pass":"pre-wave3 QA MUST-FIX",
    "action":"demote ready_to_validate -> needs_more_evidence",
    "location_ids":sorted(DEMOTE),
    "reason":QA_REASON,
    "ready_before":len(ready),"ready_after":len(B["ready_to_validate"]),
})

# refresh counts
from collections import Counter
rdy=B["ready_to_validate"]
man["counts"]["ready_to_validate"]=len(rdy)
man["counts"]["ready_tier_mix"]=dict(Counter(r["assigned_tier"] for r in rdy))
man["counts"]["ready_basis_mix"]=dict(Counter(r["evidence_basis"] for r in rdy))
man["counts"]["needs_more_evidence"]=len(B["needs_more_evidence"])

# core-bucket mutual exclusivity re-assert
core={}
dups=[]
for bk in ("ready_to_validate","needs_more_evidence","conflicts","rejected"):
    for r in B[bk]:
        lid=r["location_id"]
        if lid in core: dups.append((lid,core[lid],bk))
        core[lid]=bk
assert not dups, f"core-bucket collisions after demote: {dups[:10]}"
man["counts"]["core_universe_distinct_locations"]=len(core)

dump("_ready_to_validate_wave2_20260621.json", {"classifications":rdy})
dump("consolidation_candidate_manifest_20260621.json", man)
print("QA MUST-FIX done. ready %d -> %d (demoted %d). needs_more_evidence -> %d"%(
    len(ready),len(rdy),len(demoted_rows),len(B["needs_more_evidence"])))
print("ready tier mix:", man["counts"]["ready_tier_mix"])
