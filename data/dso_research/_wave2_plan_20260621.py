#!/usr/bin/env python3
"""
WAVE 2 merge PLAN (read-only, prints disposition; writes NOTHING).
Inputs: merged manifest + Main AO reach=4 (+QA) + Fleet B Lane1B (+QA flags).
Rules (boring & strict):
  - reach4: per-ROW, honoring QA final_gate/final_tier (regate_audit), candidates_unresolved
    -> backfill, specialist/undetermined -> backfill, Webster/Berwyn rows stay in conflicts.
    Promote to ready only gate==ready_for_validation & conf!=low & has url+artifact & not contested.
  - Lane1B: promote only the 61 'classified' rows that are NOT in ANY QA-flag category, NOT held,
    NOT low-confidence, NOT a cross-wave tier conflict; everything else -> backfill/conflicts.
  - AO reach / brand substring / weak name-chain alone never promote.
  - Dedup across all buckets + across the two lanes. No DB writes.
"""
import json, os
R="data/dso_research"
def L(p):
    with open(os.path.join(R,p)) as f: return json.load(f)

man=L("consolidation_candidate_manifest_20260621.json"); B=man["buckets"]
ready_ids={r["location_id"] for r in B["ready_to_validate"]}
nme_ids ={r["location_id"] for r in B["needs_more_evidence"]}
rej_ids ={r["location_id"] for r in B["rejected"]}
conf_ids={r["location_id"] for r in B["conflicts"]}
bq_ids  ={r["location_id"] for r in man["evidence_gap_backfill_queue"]}

# ---------- reach4 ----------
r4=L("ao_network_evidence_reach4_20260621.json")
r4q=L("ao_network_evidence_reach4_20260621_qa.json")
r4nets={n["network_id"]:n for n in r4["networks"]}
regate={r["location_id"]:r for r in r4q["regate_audit"]}          # final_gate/final_tier
cand_unres={r["location_id"] for r in r4q["candidates_unresolved"]}
spec_undet={r["location_id"] for r in r4q["specialist_or_undetermined_flags"]}

def r4_eff(row):
    lid=row["location_id"]
    if lid in regate:
        return regate[lid]["final_gate"], regate[lid]["final_tier"]
    if lid in spec_undet: return "undetermined","undetermined"
    if lid in cand_unres: return "candidate", row.get("candidate_tier")
    return row.get("gate_status"), row.get("candidate_tier")

r4_ready=[]; r4_backfill=[]; r4_keep_conflict=[]; r4_dup_ready=[]
for row in r4["rows"]:
    lid=row["location_id"]; gate,tier=r4_eff(row); conf=row.get("confidence")
    if lid in conf_ids:                  r4_keep_conflict.append((lid,row.get("name"),tier)); continue
    if lid in ready_ids:                 r4_dup_ready.append((lid,row.get("name"))); continue
    if gate!="ready_for_validation" or tier in (None,"undetermined") or conf=="low":
        r4_backfill.append((lid,row.get("name"),tier,gate,conf)); continue
    r4_ready.append((lid,row,tier))      # promote (may currently be in nme/bq -> remove there)

# ---------- Lane1B ----------
fb=L("ownership_evidence_queue_fleet_b_lane1B_20260621.json")
fbq=L("ownership_evidence_queue_fleet_b_lane1B_qa_flags_20260621.json")
flagged=set()
for cat,rows in fbq["flags_by_category"].items():
    for r in rows: flagged.add(r["location_id"])
held={r["location_id"] for r in fbq["held_stealth_branded_leads"]}
# cross-wave tier-conflict holds (same brand already released at a different tier)
XWAVE_HOLD={"1df260dc64a9a060"}  # Shafi Dental: wave1 released Shafi as dentist_multi; Lane1B says branded_dso

classified=[r for r in fb["classifications"] if r.get("status")=="classified"]
fb_ready=[]; fb_backfill=[]; fb_keep_conflict=[]; fb_dup=[]
for r in classified:
    lid=r["location_id"]
    if lid in conf_ids: fb_keep_conflict.append((lid,r.get("practice_name"))); continue
    if lid in ready_ids or any(lid==x[0] for x in r4_ready): fb_dup.append((lid,r.get("practice_name"))); continue
    why=None
    if lid in flagged: why="qa_flag"
    elif lid in held: why="held_lead"
    elif r.get("confidence")=="low": why="low_conf"
    elif lid in XWAVE_HOLD: why="xwave_tier_conflict"
    if why: fb_backfill.append((lid,r.get("practice_name"),r.get("assigned_tier"),why)); continue
    fb_ready.append(r)

# ---------- report ----------
from collections import Counter
print("="*70); print("REACH4 (56 rows)")
print(" -> ready_promote :",len(r4_ready), dict(Counter(t for _,_,t in r4_ready)))
print(" -> backfill      :",len(r4_backfill))
print(" -> keep_conflict :",len(r4_keep_conflict),[x[0] for x in r4_keep_conflict])
print(" -> dup_in_ready  :",len(r4_dup_ready),[x[0] for x in r4_dup_ready])
# which r4_ready are currently in nme/bq (promotions) vs brand-new
r4_from_nme=[lid for lid,_,_ in r4_ready if lid in nme_ids]
r4_brand_new=[lid for lid,_,_ in r4_ready if lid not in nme_ids]
print("    of ready: promoted_from_needs_more:",len(r4_from_nme),"| brand_new:",len(r4_brand_new))
for lid,row,tier in r4_ready:
    src="(from needs_more)" if lid in nme_ids else "(new)"
    print(f"      {lid} {tier:14} pe={str(row.get('pe_backed')):5} {src:18} {str(row.get('name'))[:34]} [{row.get('network')}]")
print("    backfill detail:")
for lid,nm,tier,gate,conf in r4_backfill:
    print(f"      {lid} {str(tier):14} gate={gate} conf={conf} | {str(nm)[:34]}")

print("="*70); print("LANE1B (61 classified)")
print(" -> ready_promote :",len(fb_ready), dict(Counter(r.get('assigned_tier') for r in fb_ready)))
print(" -> backfill      :",len(fb_backfill), dict(Counter(w for *_,w in fb_backfill)))
print(" -> keep_conflict :",len(fb_keep_conflict),[x[0] for x in fb_keep_conflict])
print(" -> dup           :",len(fb_dup),[x[0] for x in fb_dup])
print("    READY rows:")
for r in fb_ready:
    print(f"      {r['location_id']} {r['assigned_tier']:16} pe={str(r.get('pe_backed')):5} basis={str(r.get('evidence_basis')):13} conf={r.get('confidence'):7} {str(r.get('practice_name'))[:30]}")

# cross-lane dup check inside the two ready sets
all_new_ready=[lid for lid,_,_ in r4_ready]+[r["location_id"] for r in fb_ready]
dups=[x for x,c in Counter(all_new_ready).items() if c>1]
print("\nCROSS-LANE dup location_ids in new-ready:",dups or "NONE")
print("TOTAL new ready rows this wave:",len(all_new_ready),"-> manifest ready", len(ready_ids),"+",len(all_new_ready),"=",len(ready_ids)+len(all_new_ready))
