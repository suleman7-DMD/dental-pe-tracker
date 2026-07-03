#!/usr/bin/env python3
"""Gate-Owner Lane-2 normalization generator, files-only, ZERO mutations.
Reads the Lane-2 non-AO backfill evidence (25 rows) + its self-QA + the 310 ready
file (read-only cross-check) and emits a normalized partition that PRESERVES the
floor-impact distinction the user named:
  1. ready-for-ownership-census candidates
  2. legacy-floor corroborations (already corporate by entity_classification -> NO floor lift)
  3. true_independent confirmations (NOT corporate adds)
  4. net-new corporate candidate(s) (Schock Dental -> Dentologie)
  5. holds and refutations
No DB/manifest/ready/LEDGER/PROGRESS/ownership_tier/entity_classification/ownership_status
is written or mutated. This script only READS for cross-checks."""
import json, hashlib, os
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
DSO = os.path.dirname(BASE)
ROOT = os.path.dirname(DSO)

EV = json.load(open(os.path.join(BASE, "wave4_lane2_non_ao_backfill25_evidence_20260621.json")))
ROWS = EV["rows"]
assert len(ROWS) == 25, f"expected 25 rows, got {len(ROWS)}"

# ---- 310 ready-file membership (read-only) --------------------------------
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

PROTECTED = ["LABINOV","AQEL","BELKIC","SWEIS","RAMAHA","SHAFI","NITTINGER","BRUNETTI"]
def protflags(row):
    blob = json.dumps(row).upper()
    return [p for p in PROTECTED if p in blob]

# ---- explicit, auditable classification maps (by location_id) -------------
NET_NEW_CORPORATE = {"5cd692a50e5c32b7"}                       # Schock Dental -> Dentologie River North
TRUE_INDEP        = {"b7499322a2416c5d", "0a318ab399f418de"}   # Jova, Bellido-Griffin
HOLD_NME          = {"d4d827860b4132cb", "d2e5c43e4975ddb4"}   # Bloomingdale/SWEIS-collision, Midwest Dental Group
HOLD_OPS          = {"5404b210ff43f176", "499c18e0f7c7ad12"}   # Kang (Dental Dreams same-door), Obucina (operating status)
HOLD_SCOPE        = {"144d631a4c4dce2b", "d803fcfe4618e8a3", "e957561c107de91a"}  # IWS FQHC, Heartland Intl FQHC, Heartland Outreach nonprofit
REFUTED           = {"9068c4de3bbdb4b4", "7b61d1c9b5e65057", "598cc9dae498795b"}  # Warga, Batchelor, Northwestern

# legacy-corporate rows this evidence now QUESTIONS (would LOWER the floor if acted on; NOT acted on)
LEGACY_FP_SUSPECTS = {
    "598cc9dae498795b": "REFUTED: db affiliated_dso='Western Dental' is a pure substring false-positive of 'NORTHwestern'. Entity is Northwestern Dental Center P.C. (Northwestern Medicine academic). Currently entity_classification=dso_national in legacy floor -> false-positive; if acted on would REMOVE 1 from legacy corporate floor. NOT mutated (freeze).",
    "d2e5c43e4975ddb4": "HELD: 'Midwest Dental Group' generic name -> affiliated_dso='Midwest Dental' is a probable name-field collision (AH4); no exact-address match on the Midwest Dental DSO locator (HB6). Currently dso_national in legacy floor -> suspect false-positive; held, not refuted.",
    "d4d827860b4132cb": "HELD: org legal name says Heartland DPI-PC but brand 'Bloomingdale Dental' collides with the protected SWEIS network; affiliated_dso NULL. Currently dso_regional in legacy floor -> identity unresolved; held.",
}

BUCKETS = {
    "merge_eligible_new_corporate": [],          # net-new corporate (floor LIFT)
    "corroborates_existing_corporate_no_lift": [],# already corporate by entity_classification
    "true_independent_confirmation": [],         # earned T1; NOT a corporate add
    "hold_needs_more_evidence": [],
    "hold_operating_status_or_same_door": [],
    "hold_scope_specialist": [],
    "refuted": [],
}

PROTOCOL_DISPOSITION = {
    "merge_eligible_new_corporate": "merge_eligible_new",
    "corroborates_existing_corporate_no_lift": "corroborates_existing_ready",
    "true_independent_confirmation": "merge_eligible_new",
    "hold_needs_more_evidence": "hold_needs_more_evidence",
    "hold_operating_status_or_same_door": "hold_operating_status_or_same_door",
    "hold_scope_specialist": "hold_scope_specialist",
    "refuted": "refuted",
}

def bucket_for(row):
    lid = row["location_id"]
    if lid in NET_NEW_CORPORATE: return "merge_eligible_new_corporate"
    if lid in TRUE_INDEP:        return "true_independent_confirmation"
    if lid in HOLD_NME:          return "hold_needs_more_evidence"
    if lid in HOLD_OPS:          return "hold_operating_status_or_same_door"
    if lid in HOLD_SCOPE:        return "hold_scope_specialist"
    if lid in REFUTED:           return "refuted"
    # default: a ready_for_validation row already corporate in legacy entity_classification
    assert row.get("disposition") == "ready_for_validation", f"unexpected default for {lid}: {row.get('disposition')}"
    assert "already_corporate" in (row.get("legacy_floor_status") or ""), f"default corroboration but not already_corporate: {lid}"
    return "corroborates_existing_corporate_no_lift"

for row in ROWS:
    b = bucket_for(row)
    lid = row["location_id"]
    ec = (row.get("preserved_db_facts") or {}).get("entity_classification")
    gate = {
        "location_id": lid,
        "practice_name": row.get("practice_name"),
        "city": row.get("city"), "zip": row.get("zip"), "state": row.get("state"),
        "source_lane": row.get("source_lane"),
        "candidate_types": row.get("candidate_types"),
        "network": row.get("network"),
        "proposed_tier": row.get("proposed_tier"),
        "gate_bucket": b,
        "protocol_disposition": PROTOCOL_DISPOSITION[b],
        "agent_disposition": row.get("disposition"),
        "pe_backed": row.get("pe_backed"),
        "legacy_entity_classification": ec,
        "legacy_floor_status": row.get("legacy_floor_status"),
        "in_current_310_ready": lid in ids310,
        "legacy_corporate_now_questioned": lid in LEGACY_FP_SUSPECTS,
        "legacy_fp_note": LEGACY_FP_SUSPECTS.get(lid),
        "floor_impact": (
            "lifts_legacy_floor (+1 net-new corporate)" if b == "merge_eligible_new_corporate"
            else "no_lift (already corporate by entity_classification)" if b == "corroborates_existing_corporate_no_lift"
            else "no_lift (true_independent, not corporate)" if b == "true_independent_confirmation"
            else "no_lift (held)" if b.startswith("hold")
            else "no_lift (refuted)"
        ),
        "operating_status_check": row.get("operating_status_check"),
        "same_door_check": row.get("same_door_check"),
        "protected_network_status": row.get("protected_network_status"),
        "protected_surname_scan": ", ".join(protflags(row)) or "none",
        "dso_structure_rationale": row.get("dso_structure_rationale"),
        "hold_reason": row.get("hold_reason"),
        "missing_evidence_type": row.get("missing_evidence_type"),
        "proposed_reclassification": row.get("proposed_reclassification"),
        "evidence": {
            "durable_evidence": row.get("durable_evidence"),
            "evidence_urls": row.get("evidence_urls"),
            "evidence_source": row.get("evidence_source"),
            "searches_executed": row.get("searches_executed"),
            "search_queries": row.get("search_queries"),
        },
        "preserved_sidecar": row.get("preserved_db_facts"),
    }
    BUCKETS[b].append(gate)

# ---- reconcile ------------------------------------------------------------
counts = {k: len(v) for k, v in BUCKETS.items()}
total = sum(counts.values())
ready_census = counts["merge_eligible_new_corporate"] + counts["corroborates_existing_corporate_no_lift"] + counts["true_independent_confirmation"]
all_ids = [r["location_id"] for v in BUCKETS.values() for r in v]
dupes = sorted([i for i, c in Counter(all_ids).items() if c > 1])

# protected-surname defense-in-depth: every flagged row must be HELD/refuted, never ready-corporate
prot_rows = [(r["location_id"], r["gate_bucket"], r["protected_surname_scan"]) for v in BUCKETS.values() for r in v if r["protected_surname_scan"] != "none"]
prot_all_held = all(b.startswith("hold") or b == "refuted" for _, b, _ in prot_rows)

# ---- freeze re-attestation (READ-ONLY) ------------------------------------
dbmd5 = hashlib.md5(open(os.path.join(ROOT, "dental_pe_tracker.db"), "rb").read()).hexdigest()
ledger_path = os.path.join(DSO, "RESEARCH_HOME", "LEDGER.jsonl")
progress_path = os.path.join(DSO, "RESEARCH_HOME", "PROGRESS.json")
ledger_lines = sum(1 for _ in open(ledger_path)) if os.path.exists(ledger_path) else "missing"
prog = json.load(open(progress_path)) if os.path.exists(progress_path) else {}
undet = (prog.get("tier_tally") or {}).get("undetermined_unreviewed")

out = {
  "_meta": {
    "artifact_type": "Wave 4 Gate-Owner normalized partition — LANE 2 non-AO backfill (25 rows)",
    "role": "Gate Owner — coordinator/normalizer ONLY. Files-only. ZERO mutation of DB/manifest/ready/LEDGER/PROGRESS/ownership_tier/entity_classification/ownership_status. No --allow-db-write.",
    "date": "2026-06-22",
    "scope": "Chicagoland / Illinois only. Boston / MA parked (0 MA rows).",
    "gate_ceiling": "ready_for_validation (NEVER final). Consolidation remains FROZEN.",
    "consolidate_authorization": "NOT AUTHORIZED — frozen until the user types the explicit consolidation phrase.",
    "inputs": {
      "evidence": "wave4_lane2_non_ao_backfill25_evidence_20260621.json (MAIN-001, 25 rows)",
      "self_qa": "wave4_lane2_non_ao_backfill25_evidence_20260621_qa.json (16/16 bool guards pass)",
      "bar": "wave4_criteria_reconciliation_20260621.json (AB1-12 + HB1-10 + AH1-7 + 12-step tree, stricter-wins)",
      "ready_file_readonly": "_ready_to_validate_wave3_fixed_20260621.json (310 rows; NOT mutated)"
    },
    "why_separate_from_initial_partition": "This Lane-2 output (MAIN-001) was written AFTER the initial Gate partition and was NOT covered by VERDICT_QA_WAVE4_INITIAL_20260621.json (PASS_WITH_HOLDS). It needs its own QA pass.",
    "floor_impact_distinction_preserved": {
      "1_ready_for_ownership_census": "All 15 ready_for_validation rows carry a proposed census tier (merge_eligible_new_corporate 1 + corroborates_existing_corporate_no_lift 12 + true_independent_confirmation 2).",
      "2_legacy_corroborations_no_lift": "12 rows are ALREADY corporate by entity_classification (dso_national/dso_regional) -> they DO NOT lift the legacy corporate floor. 10 Heartland 'Dental Professionals of Illinois, P.C.' friendly-PC offices + 1 DCA New Lenox + 1 Aspen TAG Oral Care Center.",
      "3_true_independent_confirmations": "Jova Dental (b7499322a2416c5d) + Bellido-Griffin Dental (0a318ab399f418de) -> EARNED T1 (named sole-owner + own practice), NOT corporate adds.",
      "4_net_new_corporate": "EXACTLY ONE: Schock Dental -> Dentologie River North (5cd692a50e5c32b7), DB-mislabeled solo_established, confirmed on Dentologie's OWN locator (444 N Orleans, '13 Neighborhood Offices'). This is the only Lane-2 row that lifts the legacy corporate floor (+1).",
      "5_holds_and_refutations": "4 holds (2 needs_more_evidence, 1 same-door, 1 operating-status) + 3 hold_scope_specialist (institutional FQHC/nonprofit) + 3 refuted."
    },
    "floor_impact_summary_DO_NOT_OVERSTATE": {
      "net_new_corporate_floor_lift": "+1 (Dentologie/Schock ONLY)",
      "legacy_corroborations_adding_zero": 12,
      "true_independent_confirmations_not_corporate": 2,
      "legacy_corporate_false_positive_suspects_flagged_NOT_mutated": {
        "count": 3,
        "ids": list(LEGACY_FP_SUSPECTS.keys()),
        "effect_if_acted_on": "Would REMOVE up to 3 from the legacy corporate floor (Northwestern refuted; Midwest Dental Group + Bloomingdale held/unresolved). NOT acted on under freeze — surfaced to QA/user only.",
        "note": "These are pre-existing legacy entity_classification rows this Wave-4 evidence calls into question. Per the no-mutation rule + gate ceiling, NOTHING is changed; QA/user decide."
      },
      "honest_statement": "Lane 2 contributes at most +1 net-new corporate door (Dentologie). The other 12 ready rows corroborate already-corporate status and lift the floor by ZERO. Two ready rows are true_independent (not corporate). Separately, 3 already-corporate legacy rows are now questioned but are NOT mutated."
    },
    "key_guards_observed": [
      "DSO=STRUCTURE: branded_dso (T5) only with a documented MSO/management-company/platform/established DSO brand. Dentologie qualifies (13 branded Chicago offices, named founder, own locator).",
      "Heartland NAME-COLLISION guard preserved: Heartland International Health Center (FQHC/Tapestry 360) and Heartland Health Outreach (Heartland Alliance nonprofit) are explicitly NOT Heartland Dental -> held institutional, never DSO-promoted.",
      "Northwestern 'Western Dental' substring false-positive correctly refuted (academic Northwestern Medicine, not Sonrava/Western Dental).",
      "Protected-network: Bloomingdale Dental (d4d827860b4132cb) carries a SWEIS adjacency flag and is HELD (not released). No protected releases.",
      "true_independent rows carry EARNED positive owner-operated evidence — never defaulted."
    ],
    "freeze_attestation_readonly": {
      "db_md5": dbmd5, "db_md5_expected": "0dec26135bb4d6ee490dc16cfe892ca6",
      "db_md5_match": dbmd5 == "0dec26135bb4d6ee490dc16cfe892ca6",
      "LEDGER_lines": ledger_lines,
      "PROGRESS.tier_tally.undetermined_unreviewed": undet,
      "verdict": "FROZEN — intact" if (dbmd5 == "0dec26135bb4d6ee490dc16cfe892ca6" and ledger_lines == 1 and undet == 4439) else "CHECK"
    }
  },
  "reconciliation": {
    "input_rows": len(ROWS),
    "total_partitioned_rows": total,
    "balanced": total == len(ROWS),
    "distinct_location_ids": len(set(all_ids)),
    "duplicate_location_ids": dupes,
    "bucket_counts": counts,
    "ready_for_validation_total": ready_census,
    "ready_for_validation_expected": EV["disposition_rollup"]["ready_for_validation"],
    "ready_match": ready_census == EV["disposition_rollup"]["ready_for_validation"],
    "agent_disposition_rollup": EV["disposition_rollup"],
    "protected_surname_rows": [{"location_id": i, "bucket": b, "surnames": s} for i, b, s in prot_rows],
    "protected_rows_all_held_or_refuted": prot_all_held,
    "in_310_overlap": sorted([r["location_id"] for v in BUCKETS.values() for r in v if r["in_current_310_ready"]])
  },
  "qa_attention_summary": [
    "NET-NEW CORPORATE (+1 only): Schock Dental -> Dentologie River North (5cd692a50e5c32b7). Confirm Dentologie own-locator exact-address (444 N Orleans) and that no separate 'Dentologie River North' location_id already exists in the broader floor (agent flagged a duplicate-check).",
    "LEGACY FALSE-POSITIVE SUSPECTS (flagged, NOT mutated): Northwestern Dental Center (598cc9dae498795b, REFUTED 'NORTHwestern' substring), Midwest Dental Group (d2e5c43e4975ddb4, HELD name-collision), Bloomingdale Dental (d4d827860b4132cb, HELD SWEIS adjacency). All three are currently corporate in legacy entity_classification; QA/user to decide whether to demote later — no mutation now.",
    "PROTECTED-NETWORK ADJACENCY: Bloomingdale Dental (d4d827860b4132cb) brand collides with protected SWEIS; held. If it resolves to SWEIS it stays protected-held; if Heartland it would corroborate Heartland. No release.",
    "INSTITUTIONAL/SCOPE (3): IWS FQHC, Heartland International Health Center (FQHC), Heartland Health Outreach (nonprofit) -> T6 institutional held out of GP floor. Two carry the Heartland name-collision guard (NOT Heartland Dental).",
    "TRUE_INDEPENDENT (2, not corporate): Jova + Bellido-Griffin earned T1; confirm they are not double-counted as corporate anywhere."
  ],
  "buckets": BUCKETS
}

outpath = os.path.join(BASE, "wave4_gate_normalized_lane2_partition_20260622.json")
with open(outpath, "w") as f:
    json.dump(out, f, indent=2)

print("WROTE", outpath)
print("balanced:", out["reconciliation"]["balanced"], "| total:", total, "of", len(ROWS))
print("counts:", json.dumps(counts))
print("ready_match:", out["reconciliation"]["ready_match"], "(", ready_census, "ready )")
print("protected rows:", prot_rows, "| all_held_or_refuted:", prot_all_held)
print("in_310 overlap:", out["reconciliation"]["in_310_overlap"])
print("net_new_corporate floor lift: +%d (Dentologie)" % counts["merge_eligible_new_corporate"])
print("freeze:", out["_meta"]["freeze_attestation_readonly"]["verdict"],
      "| md5_match:", out["_meta"]["freeze_attestation_readonly"]["db_md5_match"],
      "| LEDGER:", ledger_lines, "| undetermined:", undet)
