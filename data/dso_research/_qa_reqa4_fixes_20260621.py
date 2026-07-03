#!/usr/bin/env python3
"""
QA RE-QA #4 MUST-FIX ONLY (no new evidence, no consolidation, no --allow-db-write).
Source verdict: ownership_manifest_QA_wave3_reqa4_20260621.json
  Fix A — demote 4 operating-status-risk ready rows -> needs_more_evidence
          (preserved_ready_row + backfill_lane='operating_status_unverified', keep network intel).
  Fix B — EXPLICIT ao:SHAFI_REEM adjudication: RELEASE as dentist_multi (Two Rivers Dental,
          Reem Shafi founder/owner; covered by the prior verified ao:SHAFI_SOHAIL/Two Rivers
          dentist_multi release AND the reach3 QA regate of 6da55130 = 'no MSO, dentist-owned
          multi only'). Correct the 2 branded_dso rows -> dentist_multi to remove the mixed-tier
          inconsistency. NOT downgraded on pe_backed=false — downgraded on absence of MSO/platform
          structure + prior-network consistency. All 3 stay in ready.
  Fix C — demote duplicate-door leak ff41419130267bd9 -> needs_more_evidence
          (backfill_lane='duplicate_door_tier_conflict'); update duplicate_denominator_blocked.
Writes _ready_to_validate_wave3_fixed_20260621.json + updates the manifest in place.
"""
import json, os, sqlite3
from collections import Counter
R="data/dso_research"
def L(p):
    with open(os.path.join(R,p)) as f: return json.load(f)
def dump(p,obj):
    with open(os.path.join(R,p),"w") as f: json.dump(obj,f,indent=1)

man=L("consolidation_candidate_manifest_20260621.json"); B=man["buckets"]
ready=B["ready_to_validate"]; ready_idx={r["location_id"]:r for r in ready}
nme_ids={r["location_id"] for r in B["needs_more_evidence"]}

con=sqlite3.connect("data/dental_pe_tracker.db")
def dbfacts(lid):
    row=con.execute("SELECT practice_name,city,zip,entity_classification FROM practice_locations WHERE location_id=?",(lid,)).fetchone()
    return row if row else (None,None,None,None)

def demote(lid, lane, reason):
    """pop lid from ready, append nme entry preserving the full original row + DB facts."""
    r=ready_idx.get(lid)
    assert r is not None, f"{lid} not in ready (cannot demote)"
    nm,city,zp,ec=dbfacts(lid)
    if lid not in nme_ids:
        B["needs_more_evidence"].append({
            "location_id":lid,"name":nm,"zip":zp,"city":city,"state":"IL",
            "entity_classification":ec,
            "nets":[r.get("network_id")] if r.get("network_id") else [],
            "sources":["qa_reqa4_mustfix_20260621"],
            "final_tier":r.get("assigned_tier"),
            "reason":reason,
            "demoted_from_ready":True,
            "backfill_lane":lane,
            "preserved_ready_row":r,
        })
        nme_ids.add(lid)
    return r

# ---------------- Fix A — operating-status demotions ----------------
A_IDS=["f6c6290c16d20224","822d3012aedf32b9","77357c36224272c8","7d1d789828351ecf"]
A_REASON=("QA RE-QA #4 MUST-FIX A (2026-06-21): operating-status risk — self-flags candidate/closed/"
          "operating-status-unverified, which consolidate_census.py --validate-only cannot catch "
          "(schema/DB-state only). Held in needs_more_evidence pending an operating-status corroborator "
          "(live website address match / current locator listing / phone-active confirmation). "
          "Network intelligence preserved (network_id retained, full original row under preserved_ready_row).")
for lid in A_IDS: demote(lid,"operating_status_unverified",A_REASON)

# ---------------- Fix C — duplicate-door tier conflict ----------------
C_ID="ff41419130267bd9"; C_TWIN="f94fb29cc7d444cd"
C_REASON=("QA RE-QA #4 MUST-FIX C (2026-06-21): duplicate-door tier conflict. Same physical door as "
          f"{C_TWIN} (CHICAGO DENTAL PROFESSIONALS INC, 2340 N Clybourn Ave, phone 773-528-2205): this "
          "row is ready as dentist_multi (Fleet B ein-015, EIN 362686478) while the twin carried a prior "
          "true_independent verdict — the door cannot carry both consolidated and independent. Held pending "
          "same-door reconciliation (collapse the duplicate, resolve to ONE tier).")
demote(C_ID,"duplicate_door_tier_conflict",C_REASON)

# rebuild ready WITHOUT the 5 demoted rows
demoted=set(A_IDS+[C_ID])
B["ready_to_validate"]=[r for r in ready if r["location_id"] not in demoted]
ready=B["ready_to_validate"]; ready_idx={r["location_id"]:r for r in ready}

# ---------------- Fix B — ao:SHAFI_REEM explicit release as dentist_multi ----------------
B_IDS=["ba663f30996016ce","fc658bf62642d908","6da55130228a9c54"]
B_CORRECTED=[]
RELEASE_NOTE=(" || GATE-OWNER RE-QA #4 RELEASE (2026-06-21): ao:SHAFI_REEM (Two Rivers Dental, Reem Shafi "
              "founder/owner/CEO) explicitly RELEASED as dentist_multi — covered by the prior VERIFIED "
              "ao:SHAFI_SOHAIL/Two Rivers network adjudication (released dentist_multi, pe_backed=false) and "
              "the reach3 QA regate of 6da55130 ('no MSO; dentist-owned multi only'). Tier set dentist_multi "
              "on absence of any MSO/management-company/platform structure + consistency with that prior "
              "network release — NOT on pe_backed=false.")
for lid in B_IDS:
    r=ready_idx.get(lid)
    assert r is not None, f"SHAFI_REEM row {lid} not in ready"
    assert r.get("network_id")=="ao:SHAFI_REEM", f"{lid} unexpected network_id {r.get('network_id')}"
    orig=r["assigned_tier"]
    if orig!="dentist_multi":
        r["assigned_tier"]="dentist_multi"
        B_CORRECTED.append({"location_id":lid,"from":orig,"to":"dentist_multi"})
    # basis: branded_dso and dentist_multi both map to name_chain (artifact-backed) -> unchanged
    if "RE-QA #4 RELEASE" not in (r.get("reasoning") or ""):
        r["reasoning"]=(r.get("reasoning") or "")+RELEASE_NOTE+(f" (tier corrected from {orig})" if orig!="dentist_multi" else "")

# record explicit release in ao_network_release_decisions
rd=man.setdefault("ao_network_release_decisions",{}).setdefault("decisions",{})
rd["ao:SHAFI_REEM"]={
    "network_evidence_quality":"verified",
    "decision":"release_eligible",
    "rows_total":len(B_IDS),"rows_released":len(B_IDS),"rows_held":0,
    "tier":"dentist_multi","pe_backed":False,
    "tier_corrections":B_CORRECTED,
    "rationale":("RE-QA #4 MUST-FIX B. ao:SHAFI_REEM = Dr. Reem Shafi (founder/owner/CEO of Two Rivers Dental, "
        "20+ Chicagoland offices under distinct local trade names: Hanover Dental, Baker Hill Dental, etc.). "
        "Released as dentist_multi, consistent with the prior VERIFIED ao:SHAFI_SOHAIL/Two Rivers adjudication "
        "(also dentist_multi, pe_backed=false; whose stale_closed_notes already reference Reem Shafi/Two Rivers) "
        "and with the reach3 QA regate_audit of 6da55130228a9c54 ('branded_dso->dentist_multi: no MSO; "
        "dentist-owned multi only'). Two branded_dso rows (ba663f30996016ce, fc658bf62642d908) corrected DOWN "
        "to dentist_multi to remove the mixed-tier inconsistency. NOT a pe_backed=false downgrade — the tier "
        "rests on absence of a documented MSO/management-company/platform structure (DSO=STRUCTURE rule) plus "
        "consistency with the prior Shafi/Two Rivers release. Artifacts retained (NPPES AO=REEM SHAFI title=OWNER "
        "across the org NPIs; myhanoverdental.com & bakerhilldental.com owner/CEO pages)."),
    "covered_by_prior_release":"ao:SHAFI_SOHAIL (wave1, network_evidence_quality=verified)",
}

# ---------------- update duplicate_denominator_blocked ----------------
ddb=B.get("duplicate_denominator_blocked")
if isinstance(ddb,dict):
    ddb["currently_in_candidate_set"]=[{
        "location_id":C_ID,"name":"Peters, Erika","address":"2340 N Clybourn Ave","phone":"773-528-2205",
        "was_ready_tier":"dentist_multi","fleet_b_artifact":"ein-015 / EIN 362686478",
        "same_door_twin":C_TWIN,"twin_name":"CHICAGO DENTAL PROFESSIONALS INC","twin_prior_tier":"true_independent",
        "status":"LEAK FOUND + FIXED 2026-06-21 — demoted ready_to_validate -> needs_more_evidence "
                 "(backfill_lane='duplicate_door_tier_conflict'); twin in NO live bucket. "
                 "Candidate set clean after fix; record retained as denominator-hazard provenance.",
    }]
    ddb.setdefault("pairs",[]).append({
        "names":["Peters, Erika","CHICAGO DENTAL PROFESSIONALS INC"],
        "location_ids":[C_ID,C_TWIN],
        "conflicting_tiers":["dentist_multi","true_independent"],
        "phones":["773-528-2205"],
        "address":"2340 N Clybourn Ave, Chicago 60614",
        "note":("RE-QA #4 Gate-Owner-confirmed real ready-row leak (9th pair). dentist_multi row "
                f"{C_ID} demoted to needs_more_evidence; resolve to ONE tier when the dup is collapsed."),
    })
    ddb["note"]=ddb.get("note","").split(" — listed here")[0] + \
        (" — listed here as a denominator hazard any future wave must resolve before consolidating these "
         "addresses. RE-QA #4 (2026-06-21): a 9th pair (Peters/Chicago Dental Professionals @ 2340 N Clybourn) "
         "DID leak into ready as dentist_multi and was demoted; currently_in_candidate_set records the fix.")

# ---------------- record action + recount + re-assert ----------------
man.setdefault("qa_mustfix_actions",[]).append({
    "at":"2026-06-21","pass":"RE-QA #4 MUST-FIX (A+B+C)","source":"ownership_manifest_QA_wave3_reqa4_20260621.json",
    "A_operating_status_demotions":A_IDS,
    "B_shafi_reem_release":{"decision":"released_as_dentist_multi","location_ids":B_IDS,"tier_corrections":B_CORRECTED},
    "C_duplicate_door_demotion":{"location_id":C_ID,"twin":C_TWIN,"lane":"duplicate_door_tier_conflict"},
    "ready_before":315,"ready_after":len(ready),
})
man["counts"]["ready_to_validate"]=len(ready)
man["counts"]["ready_tier_mix"]=dict(Counter(r["assigned_tier"] for r in ready))
man["counts"]["ready_basis_mix"]=dict(Counter(r["evidence_basis"] for r in ready))
man["counts"]["needs_more_evidence"]=len(B["needs_more_evidence"])

core={}; dups=[]
for bk in ("ready_to_validate","needs_more_evidence","conflicts","rejected"):
    for r in B[bk]:
        lid=r["location_id"]
        if lid in core: dups.append((lid,core[lid],bk))
        core[lid]=bk
assert not dups, f"core-bucket collisions: {dups[:10]}"
man["counts"]["core_universe_distinct_locations"]=len(core)
man.setdefault("_meta",{})["reqa4_fix"]={
    "at":"2026-06-21","by":"opus-4.8 reset-consolidation-gate (4th session, autonomous)",
    "applied":"RE-QA #4 MUST-FIX A (demote 4 operating-status) + B (release ao:SHAFI_REEM dentist_multi) + C (demote 1 duplicate-door)",
    "result":f"ready 315 -> {len(ready)} (SHAFI_REEM RELEASED). needs_more_evidence -> {len(B['needs_more_evidence'])}.",
    "db_writes":"NONE.",
}

dump("_ready_to_validate_wave3_fixed_20260621.json", {"classifications":ready})
dump("_ready_to_validate_wave2_20260621.json", {"classifications":ready})   # keep canonical current-ready file in sync
dump("consolidation_candidate_manifest_20260621.json", man)

print("RE-QA #4 FIXES applied (no DB writes).")
print(" Fix A demoted:", A_IDS)
print(" Fix B SHAFI_REEM released dentist_multi; tier corrections:", B_CORRECTED)
print(" Fix C demoted:", C_ID, "(twin", C_TWIN, "in no live bucket)")
print(" ready 315 ->", len(ready), "| needs_more_evidence ->", len(B["needs_more_evidence"]))
print(" ready tier mix:", man["counts"]["ready_tier_mix"])
print(" core distinct:", man["counts"]["core_universe_distinct_locations"],
      "= ready+nme+conf+rej", len(ready)+len(B["needs_more_evidence"])+len(B["conflicts"])+len(B["rejected"]))
