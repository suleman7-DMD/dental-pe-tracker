#!/usr/bin/env python3
"""Gate-Owner normalization generator (GATE-001), files-only, ZERO mutations.
Reads the two Wave-4 evidence files + the reconciled stricter bar and emits the
9-bucket partition. Decision map is explicit and auditable. No DB/manifest/ready
file is written or mutated; this script only READS those for cross-checks."""
import json, hashlib, os

BASE = os.path.dirname(os.path.abspath(__file__))
DSO = os.path.dirname(BASE)
L1 = json.load(open(os.path.join(BASE, "wave4_lane1_conflicts_ao_backfill_evidence_20260621.json")))
L3 = json.load(open(os.path.join(BASE, "wave4_lane3_phasec_top50_evidence_20260621.json")))

# ---- 310 membership (read-only cross-check) -------------------------------
ready310 = json.load(open(os.path.join(DSO, "_ready_to_validate_wave3_fixed_20260621.json")))
ids310 = set()
def _collect(o):
    if isinstance(o, dict):
        v = o.get("location_id")
        if isinstance(v, str): ids310.add(v)
        for x in o.values(): _collect(x)
    elif isinstance(o, list):
        for x in o: _collect(x)
_collect(ready310)

PROTECTED = ["SHAFI","BELKIC","NITTINGER","AQEL","BRUNETTI","SWEIS","LABINOV","RAMAHA"]

def protflags(row):
    blob = json.dumps(row).upper()
    return [p for p in PROTECTED if p in blob]

BUCKETS = {k: [] for k in [
    "merge_eligible_new","corroborates_existing_ready","qa_attention_current_ready",
    "hold_protected_network","hold_scope_specialist","hold_operating_status_or_same_door",
    "hold_needs_more_evidence","rejected","refuted"]}

def emit(bucket, row, source_lane, proposed_tier, gate_tier_status, disposition,
         hold_reason, ab_hb_rules, evidence, extra=None):
    r = {
        "location_id": row.get("location_id"),
        "practice_name": row.get("practice_name"),
        "city": row.get("city"), "zip": row.get("zip"), "state": row.get("state","IL"),
        "source_lane": source_lane,
        "candidate_types": row.get("candidate_types") or row.get("gate_network") or row.get("network"),
        "proposed_tier": proposed_tier,
        "gate_tier_status": gate_tier_status,   # endorsed | held_unresolved | n/a
        "pe_backed": row.get("pe_backed"),
        "in_current_310": row.get("location_id") in ids310,
        "operating_status_check": row.get("operating_status_check") or row.get("operating_status"),
        "same_door_check": row.get("same_door_check"),
        "protected_network_status": ", ".join(protflags(row)) or "none",
        "disposition": disposition,
        "hold_reason": hold_reason,
        "ab_hb_rules_cited": ab_hb_rules,
        "evidence": evidence,
        "dso_structure_rationale": row.get("dso_structure_rationale"),
    }
    if extra: r.update(extra)
    BUCKETS[bucket].append(r)

def l1_evidence(row):
    return {"durable_evidence": row.get("durable_evidence"),
            "evidence_source": row.get("evidence_source"),
            "current_nets_signals": row.get("current_nets_signals"),
            "current_sources": row.get("current_sources"),
            "current_conflict_reason": row.get("current_conflict_reason"),
            "protected_network_release_reference": row.get("protected_network_release_reference"),
            "pe_backed_citation": row.get("pe_backed_citation"),
            "row_note": row.get("row_note")}

def l3_evidence(row):
    return {"evidence_urls": row.get("evidence_urls"),
            "exact_address_match": row.get("exact_address_match"),
            "parent_mso_platform_evidence": row.get("parent_mso_platform_evidence"),
            "qa_flags": row.get("qa_flags"),
            "search_queries": row.get("search_queries"),
            "pe_sponsor_cited": row.get("pe_sponsor_cited"),
            "confidence": row.get("confidence"),
            "sidecar": row.get("sidecar"),
            "rationale": row.get("rationale"),
            "agent_disposition": row.get("disposition")}

# ============================ LANE 1 ======================================
na = L1["network_adjudications"]

# 1st Family Dental (BELKIC) -> all hold_protected_network
for row in na["1st Family Dental"]["rows"]:
    emit("hold_protected_network", row, "lane1_conflicts", row.get("proposed_tier"),
         "held_unresolved", "hold_protected_network",
         "BELKIC protected network (AB9) — no release this sprint (user default #1).",
         ["AB9"], l1_evidence(row))

# Brite Dental (Fadi Aqel) -> hold_protected_network (AQEL + AB10)
for row in na["Brite Dental (Fadi Aqel)"]["rows"]:
    emit("hold_protected_network", row, "lane1_conflicts", row.get("proposed_tier"),
         "held_unresolved", "hold_protected_network",
         "AQEL protected network (AB9) AND Webster contested set (AB10) — no release this sprint.",
         ["AB9","AB10"], l1_evidence(row))

# Webster Dental -> refuted | closed | AB10 held
for row in na["Webster Dental"]["rows"]:
    op = (row.get("operating_status_check") or "")
    if row.get("disposition") == "refuted":
        emit("refuted", row, "lane1_conflicts", row.get("proposed_tier"), "n/a", "refuted",
             "Refuted Webster membership — not a Webster door (whole-network adjudication).",
             ["AB10"], l1_evidence(row))
    elif op.startswith("CLOSED"):
        emit("hold_operating_status_or_same_door", row, "lane1_conflicts", row.get("proposed_tier"),
             "held_unresolved", "hold_operating_status_or_same_door",
             "Subject door self-flagged CLOSED (Webster Cicero 60804); ALSO AB10 Webster contested.",
             ["AB7","AB10"], l1_evidence(row))
    else:
        emit("hold_protected_network", row, "lane1_conflicts", row.get("proposed_tier"),
             "held_unresolved", "hold_protected_network",
             "AB10 Webster contested-network HOLD — needs documented MAIN-SESSION whole-network "
             "adjudication artifact before any release (NOT one of the 8 protected surnames).",
             ["AB10"], l1_evidence(row), {"network_policy_hold": "AB10_webster_contested"})

# Webster Dental Care (contested) -> AB10 held (decoupled membership)
for row in na["Webster Dental Care (contested)"]["rows"]:
    emit("hold_protected_network", row, "lane1_conflicts", row.get("proposed_tier"),
         "held_unresolved", "hold_protected_network",
         "AB10 Webster contested — membership decoupled/unresolved; held pending whole-network adjudication.",
         ["AB10"], l1_evidence(row), {"network_policy_hold": "AB10_webster_contested"})

# Dental Town (Razzak) -> merge_eligible_new (T3 dentist_multi, own-locator transcribed)
for row in na["Dental Town (Razzak)"]["rows"]:
    emit("merge_eligible_new", row, "lane1_conflicts", "dentist_multi (T3)", "endorsed",
         "merge_eligible_new",
         None,
         ["AB1","AB2","AB3"], l1_evidence(row),
         {"gate_note": "Dentist-owned multi-location (Dr. Razzak); own-locator dentaltownchicago.com/locations/ "
                       "transcribed in Wave4 (AB3). No MSO => T3 (consolidated, NOT DSO/PE). Razzak NOT protected. "
                       "Not in current 310."})

# Precision Dental Care -> merge_eligible_new (T3 dentist_multi)
for row in na["Precision Dental Care"]["rows"]:
    emit("merge_eligible_new", row, "lane1_conflicts", "dentist_multi (T3)", "endorsed",
         "merge_eligible_new",
         None,
         ["AB1","AB2","AB3"], l1_evidence(row),
         {"gate_note": "Dentist-owned multi (Dr. Randy Chang; Precision + Advantage Dental Care LLC same owner); "
                       "own-locator precisiondentalchicago.com/our-locations transcribed (AB3). No MSO => T3. "
                       "Chang NOT protected. Not in current 310."})

# Sonrisa / CDCA orphans -> admin HQ rejected (AB7); 4 doors GATE-HELD (stricter than agent 'ready')
for row in na["__orphans__ (Sonrisa/CDCA)"]["rows"]:
    if row.get("disposition") == "held":  # admin HQ 1354bc2b8dff1d69
        emit("rejected", row, "lane1_conflicts", row.get("proposed_tier"), "n/a", "rejected",
             "AB7 non-clinical administrative HQ (SONRISA ROGERS PARK INC) — excluded from GP/active-door "
             "denominator. NOT a membership refutation; entity is real but non-clinical.",
             ["AB7"], l1_evidence(row), {"gate_note": "rejected = excluded from GP floor as non-clinical, per agent + AB7."})
    else:
        emit("hold_needs_more_evidence", row, "lane1_conflicts", row.get("proposed_tier") + " (agent-proposed)",
             "held_unresolved", "hold_needs_more_evidence",
             "GATE OVERRIDE of agent 'ready_for_validation': (1) durable artifact is a management-company domain "
             "(cdcoa.org) + DESCRIBED-not-transcribed IL SOS friendly-PC entity names + 'Becker's coverage' with no "
             "URL -> fails AB3/AH3 (no transcribed exact-address durable artifact harvested in Wave 4); (2) agent "
             "itself punts an UNRESOLVED FQHC institutional (T6) vs stealth_dso (T4) tier question to Gate. As "
             "coordinator I may not research it nor manufacture a URL. Needs: transcribed CDCA own-locator/IL-SOS "
             "registry URL for THIS exact address + a T4-vs-T6 scope ruling.",
             ["AB3","AH3","HB6"], l1_evidence(row),
             {"missing_evidence_type": "transcribed_exact_address_locator_or_registry_url + FQHC_T6_vs_stealth_T4_scope_ruling",
              "gate_overrode_agent_ready": True})

# AO backfill 22 -> all hold_needs_more_evidence (AB1 AO-reach-only); annotate protected
for row in L1["ao_backfill_dispositions"]["rows"]:
    pf = protflags(row)
    hr = ("AO-reach co-occurrence ONLY — no durable documentary artifact at the subject door => fails AB1 "
          "(AO reach is a discovery signal, never proof).")
    if pf:
        hr += f" ALSO protected network ({', '.join(pf)}; AB9) — no release this sprint (user default #1)."
    emit("hold_needs_more_evidence", row, "lane2_ao_backfill", row.get("proposed_tier"),
         "held_unresolved", "hold_needs_more_evidence", hr,
         ["AB1"] + (["AB9"] if pf else []),
         {"durable_evidence": row.get("durable_evidence"), "evidence_source": row.get("evidence_source"),
          "current_nets_signals": row.get("current_nets_signals"), "row_note": row.get("row_note")},
         {"missing_evidence_type": "durable_documentary_artifact_at_subject_door (locator_exact / EIN / parent / db_field)",
          "double_hold_protected": bool(pf)})

# ============================ LANE 3 ======================================
RANK = {L["rank"]: L for L in L3["leads"]}
SCOPE_RANKS = {21,42,43,45,47,48,49}     # Affordable/ClearChoice NEW (not in 310) -> scope hold
QA_ATTN = {2:  ("AB9 LABINOV protected (release required) AND operating_status=closed_or_relocated_per_agent. "
                "Current-ready (in 310) via prior manifest handling — flag for QA, DO NOT count as net-new; "
                "QA should confirm the LABINOV release basis and re-scan the counted door for closure.", ["AB9","AB7"]),
           32: ("Affordable Dentures (tooth-replacement specialist scope) AND current-ready (in 310). Per user "
                "default #2, Affordable/ClearChoice are held OUT of the GP floor pending a user scope decision — "
                "flag for QA rather than silently retaining in the 310.", ["AB6_scope"]),
           40: ("Affordable Dentures (specialist scope) AND current-ready (in 310). Same as r32 — flag for QA "
                "re: GP-floor scope; do not silently retain.", ["AB6_scope"])}
CORROB = {6,17,27}
MERGE_NEW = {35:"branded_dso (T5)", 41:"branded_dso (T5)"}
PROT_HOLD = {15:("AB9 AQEL (Dental 360 / Family Dental Group) — exact-address own-locator match present, but "
                 "protected network with no release this sprint (user default #1). NOT in 310.", ["AB9"])}
OPS_HOLD = {5:  "same_door nuance: 350 N Clark Ste 600 is BOTH Dental Dreams corporate HQ and a patient clinic "
                "(possible_same_door_or_suite_nuance) — hold pending same-door resolution (user default #4).",
            10: "operating_status=closed_or_relocated_per_agent (now 'Advanced Family Dental') AND same_door nuance "
                "— hold pending resolution (user default #4).",
            11: "same_door nuance (College Drive/GLDP/Shore) possible_same_door_or_suite — hold pending resolution. "
                "(Otherwise strong: GLDP own-locator exact match, Shore Capital PE.)",
            44: "same_door nuance (Familia Schaumburg Ste 610) AND exact-address rests ONLY on referral directories "
                "(Yelp/Yahoo/WebMD/BBB) which the durable_evidence_whitelist EXCLUDES -> AB3 weak. Hold."}

for rk, L in sorted(RANK.items()):
    disp = L.get("disposition")
    if rk in MERGE_NEW:
        emit("merge_eligible_new", L, "lane3_phasec", MERGE_NEW[rk], "endorsed", "merge_eligible_new", None,
             ["AB1","AB2","AB3","AB4"], l3_evidence(L),
             {"gate_note": "Clean: DSO's OWN locator exact-address match (AB3) + named structure (AB4); "
                           "active; no same-door/scope/AB9/medium blocker; not in 310."})
    elif rk in QA_ATTN:
        hr, rules = QA_ATTN[rk]
        emit("qa_attention_current_ready", L, "lane3_phasec", L.get("proposed_tier"), "held_unresolved",
             "qa_attention_current_ready", hr, rules, l3_evidence(L))
    elif rk in CORROB:
        emit("corroborates_existing_ready", L, "lane3_phasec", L.get("proposed_tier"), "corroborated",
             "corroborates_existing_ready",
             "Already in current 310; Fleet-B exact-address evidence corroborates the existing ready row "
             "(user default #3: corroboration/dedupe, NOT a net-new addition). Clean: active, no same-door, AB3.",
             ["AB3"], l3_evidence(L))
    elif rk in PROT_HOLD:
        hr, rules = PROT_HOLD[rk]
        emit("hold_protected_network", L, "lane3_phasec", L.get("proposed_tier"), "held_unresolved",
             "hold_protected_network", hr, rules, l3_evidence(L))
    elif rk in SCOPE_RANKS:
        emit("hold_scope_specialist", L, "lane3_phasec", L.get("proposed_tier"), "held_unresolved",
             "hold_scope_specialist",
             "Affordable Dentures / ClearChoice = tooth-replacement / implant specialist scope. Per user default #2 "
             "held OUT of the GP floor pending a user scope decision (NOT added to GP ready). "
             f"(Agent disposition was '{disp}'.)",
             ["AB6_scope"], l3_evidence(L))
    elif rk in OPS_HOLD:
        emit("hold_operating_status_or_same_door", L, "lane3_phasec", L.get("proposed_tier"), "held_unresolved",
             "hold_operating_status_or_same_door", OPS_HOLD[rk], ["AB7","AB3"], l3_evidence(L))
    elif rk == 50:
        emit("hold_needs_more_evidence", L, "lane3_phasec", L.get("proposed_tier"), "held_unresolved",
             "hold_needs_more_evidence",
             "MEDIUM confidence + same_door nuance; exact-address rests on a Heartland JOBS posting (not a patient "
             "locator). Agent flag 'ready_but_medium_confidence_recommend_locator_confirmation'. Hold (user default #4).",
             ["AB3"], l3_evidence(L), {"missing_evidence_type": "own_patient_locator_exact_address_confirmation"})
    elif disp == "needs_more_evidence":
        emit("hold_needs_more_evidence", L, "lane3_phasec", L.get("proposed_tier"), "held_unresolved",
             "hold_needs_more_evidence",
             "Agent disposition needs_more_evidence — no durable exact-address structural artifact clears AB1-AB3 yet.",
             ["AB1","AB3"], l3_evidence(L), {"missing_evidence_type": "transcribed_exact_address_durable_artifact"})
    elif disp == "rejected":
        emit("rejected", L, "lane3_phasec", L.get("proposed_tier"), "n/a", "rejected",
             "Agent rejected — confirmed not a qualifying consolidation member (e.g., true_independent / single-loc / "
             "duplicate / not a chain). Recorded, not promoted.",
             ["AH-tier"], l3_evidence(L))
    else:
        emit("hold_needs_more_evidence", L, "lane3_phasec", L.get("proposed_tier"), "held_unresolved",
             "hold_needs_more_evidence", f"Unmapped disposition '{disp}' — defaulted to hold (no partial credit).",
             ["AB1"], l3_evidence(L))

# ============================ RECONCILE ===================================
counts = {k: len(v) for k, v in BUCKETS.items()}
total = sum(counts.values())
l1_total = 74 + len(L1["ao_backfill_dispositions"]["rows"])
l3_total = len(L3["leads"])
all_ids = [r["location_id"] for v in BUCKETS.values() for r in v]
from collections import Counter
cross_lane = sorted([i for i, c in Counter(all_ids).items() if c > 1])

# Freeze re-attestation (READ-ONLY)
dbmd5 = hashlib.md5(open(os.path.join(os.path.dirname(DSO), "dental_pe_tracker.db"), "rb").read()).hexdigest()
ledger_path = os.path.join(DSO, "RESEARCH_HOME", "LEDGER.jsonl")
progress_path = os.path.join(DSO, "RESEARCH_HOME", "PROGRESS.json")
ledger_lines = sum(1 for _ in open(ledger_path)) if os.path.exists(ledger_path) else "missing"
prog = json.load(open(progress_path)) if os.path.exists(progress_path) else {}
undet = prog.get("tier_tally", {}).get("undetermined_unreviewed")

out = {
  "_meta": {
    "artifact_type": "Wave 4 Gate-Owner normalized partition (GATE-001)",
    "role": "Gate Owner — coordinator/normalizer ONLY. Files-only. ZERO mutation of DB/manifest/ready/LEDGER/"
            "PROGRESS/ownership_tier/entity_classification/ownership_status. No --allow-db-write.",
    "date": "2026-06-21",
    "gate_ceiling": "ready_for_validation (NEVER final). Consolidation remains FROZEN.",
    "consolidate_authorization": "NOT AUTHORIZED — frozen until user types the explicit consolidation phrase.",
    "inputs": {
      "lane1": "wave4_lane1_conflicts_ao_backfill_evidence_20260621.json (74 conflicts + 22 AO backfill = 96)",
      "lane3": "wave4_lane3_phasec_top50_evidence_20260621.json (50 leads)",
      "bar": "wave4_criteria_reconciliation_20260621.json (AB1-AB12 + HB1-HB10 + AH1-AH7 + 12-step tree, stricter-wins)",
      "authoritative_gate": "ownership_manifest_QA_wave4_pre_criteria_20260621.json",
      "secondary_crosscheck": "ownership_manifest_QA_wave4_preQA_criteria_20260621.json"
    },
    "user_defaults_applied": [
      "#1 No protected-network releases (LABINOV/AQEL/BELKIC/SWEIS/RAMAHA/SHAFI/NITTINGER/BRUNETTI) unless already explicitly released in the existing manifest.",
      "#2 Affordable Dentures / ClearChoice held OUT of the GP floor (specialist scope) pending user decision.",
      "#3 Fleet B current-310 overlaps are corroborations/dedupes, not net-new additions.",
      "#4 Rows with closed/relocated, same-door nuance, medium confidence, AB9, or scope flag = HOLD unless Gate resolves with evidence."
    ],
    "gate_judgment_calls": [
      "Sonrisa/CDCA 4 FQHC doors: agent proposed 'ready_for_validation' (stealth_dso). GATE HELD them "
      "(hold_needs_more_evidence) — AB3/AH3 (durable artifact described-not-transcribed) + unresolved FQHC "
      "T6-vs-stealth_dso-T4 scope question the agent itself punted to Gate. Stricter-wins.",
      "Sonrisa admin HQ (1354bc2b8dff1d69): AB7 non-clinical exclusion -> 'rejected' bucket (NOT a membership refutation).",
      "Webster contested set (AB10): 9 active Webster Dental rows + 1 Webster Dental Care (contested) -> hold_protected_network "
      "annotated AB10 (network-policy hold; NOT one of the 8 protected surnames). Closed Cicero -> operating-status bucket. "
      "6 nonmembers -> refuted.",
      "fd93e6934ac6c59c (Lane3 r02): per Gate instructions -> qa_attention_current_ready (AB9 LABINOV + closed flag); not counted as new.",
      "Affordable rows already in 310 (bd77120df3018393 r32, 199841c7ee233c17 r40) -> qa_attention_current_ready (scope flag on current-ready)."
    ],
    "freeze_attestation_readonly": {
      "db_md5": dbmd5, "db_md5_expected": "0dec26135bb4d6ee490dc16cfe892ca6",
      "db_md5_match": dbmd5 == "0dec26135bb4d6ee490dc16cfe892ca6",
      "LEDGER_lines": ledger_lines, "PROGRESS.tier_tally.undetermined_unreviewed": undet,
      "verdict": "FROZEN — intact" if (dbmd5 == "0dec26135bb4d6ee490dc16cfe892ca6" and ledger_lines == 1 and undet == 4439) else "CHECK"
    }
  },
  "reconciliation": {
    "lane1_input_rows": l1_total, "lane3_input_rows": l3_total,
    "total_input_rows": l1_total + l3_total,
    "total_partitioned_rows": total,
    "balanced": total == l1_total + l3_total,
    "bucket_counts": counts,
    "distinct_location_ids": len(set(all_ids)),
    "cross_lane_duplicate_ids": cross_lane,
    "cross_lane_note": "f3959b4a9ac8e139 (SILVA DENTAL CENTER LTD, 60804) appears in BOTH Lane-1 AO-backfill and "
                       "Lane-3 r16; both dispositions are needs_more_evidence, so both touches land in "
                       "hold_needs_more_evidence. Counted once per lane (2 rows, 1 distinct location)."
                       if "f3959b4a9ac8e139" in cross_lane else "none"
  },
  "qa_attention_summary": [
    "fd93e6934ac6c59c — current-ready, now AB9 LABINOV-protected + door self-flagged closed_or_relocated. Confirm release basis & door status.",
    "bd77120df3018393 — current-ready, Affordable Dentures specialist scope. Decide GP-floor inclusion.",
    "199841c7ee233c17 — current-ready, Affordable Dentures specialist scope. Decide GP-floor inclusion."
  ],
  "headline_effect_if_QA_passes": {
    "net_new_merge_eligible": counts["merge_eligible_new"],
    "composition": "Lane1 DentalTown 9 (T3 dentist_multi) + Precision 8 (T3 dentist_multi) + Lane3 r35 (T5 branded_dso, "
                   "Midwest Dental/Smile Brands/Gryphon) + r41 (T5 branded_dso, Dental Dreams/KOS MSO).",
    "note": "These are PROPOSED ready_for_validation only. Nothing is merged; consolidation stays FROZEN. T3 rows are "
            "'consolidated' but NOT DSO/PE (headline dso_pe = T4+T5 only)."
  },
  "buckets": BUCKETS
}

outpath = os.path.join(BASE, "wave4_gate_normalized_partition_20260621.json")
with open(outpath, "w") as f:
    json.dump(out, f, indent=2)

print("WROTE", outpath)
print("balanced:", out["reconciliation"]["balanced"], "| total:", total,
      "= L1", l1_total, "+ L3", l3_total)
print("counts:", json.dumps(counts))
print("distinct_ids:", len(set(all_ids)), "| cross_lane dupes:", cross_lane)
print("freeze:", out["_meta"]["freeze_attestation_readonly"]["verdict"],
      "| md5_match:", out["_meta"]["freeze_attestation_readonly"]["db_md5_match"],
      "| LEDGER:", ledger_lines, "| undetermined:", undet)
