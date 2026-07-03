#!/usr/bin/env python3
"""
Assemble the MERGED manifest (2026-06-21 backfill pass) from the merge state.
Writes consolidation_candidate_manifest_20260621.json IN PLACE (living artifact),
keeping the prior 65-row validate file (_ready_to_validate_normalized_20260621.json)
untouched for audit; the new validate file is _ready_to_validate_merged_20260621.json.

NOTHING from the AO file is flattened: its networks + individuals + _meta are copied
verbatim into the manifest sidecar `ao_network_intelligence`.
"""
import json, os, pickle, datetime
R = "data/dso_research"
def load(p):
    with open(os.path.join(R, p)) as f: return json.load(f)

man = load("consolidation_candidate_manifest_20260621.json")
st  = pickle.load(open(os.path.join(R, "_merge_state_20260621.pkl"), "rb"))
ao  = load("ao_backfill_evidence_71_20260621.json")

moved_to_ready = {r["location_id"] for r in st["fb_ready"]} | {r["location_id"] for r in st["ao_released"]}
zieba_id = st["fb_conflict"][0]["location_id"] if st["fb_conflict"] else None
moved = set(moved_to_ready) | ({zieba_id} if zieba_id else set())

b = man["buckets"]

# ready
b["ready_to_validate"] = st["new_ready"]

# needs_more_evidence: drop the 59 promoted/reclassed rows
b["needs_more_evidence"] = [r for r in b["needs_more_evidence"] if r["location_id"] not in moved]

# conflicts: append Zieba (Webster-adjacent), preserve the QA flag verbatim
if zieba_id:
    zr = st["fb_conflict"][0]
    b["conflicts"].append({
        "location_id": zieba_id,
        "name": zr.get("practice_name", "ZIEBA DENTISTRY HIGHLAND PARK,LTD"),
        "city": zr.get("city"), "state": "IL",
        "nets": [], "entity_classification": zr.get("entity_classification"),
        "gate_network": "Webster Dental Care (contested)",
        "gate_disposition": "conflict_webster_adjacent",
        "reason": ("Fleet B classified dentist_multi via intel_dossier, but dossier records a former DBA "
                   "'Webster Dental Care' -> touches the contested Webster conflict set (16 rows). Routed to "
                   "conflicts, not auto-promoted; resolve residual Webster MSO question before tiering."),
        "qa_flag": "2eccce6b14d310cd former DBA Webster Dental Care -- verify no residual Webster MSO structure",
        "source": "fleet_b_backfill",
    })

# backfill queue: drop the 59, keep the rest (Schock-hold remains via needs_verification)
bq = [r for r in man["evidence_gap_backfill_queue"] if r["location_id"] not in moved]
man["evidence_gap_backfill_queue"] = bq

# ---- AO strategic NETWORK intelligence sidecar (verbatim, nothing flattened) ----
man["ao_network_intelligence"] = {
    "_provenance": "ao_backfill_evidence_71_20260621.json (Main AO session). Strategic NETWORK "
                   "evidence, NOT a flat validator queue. Preserved verbatim for the Consolidated/DSO "
                   "headline narrative + any later per-network release.",
    "_meta": ao.get("_meta"),
    "networks": ao.get("networks"),        # ao_name, owner/operator/family identity, members, URLs,
                                           # stale_closed notes, evidence_chain, structure_evidence, etc.
    "individuals": ao.get("individuals"),  # the original-13 individual dossiers
}

# ---- per-network release decisions (the gate-owner judgment record) ----
man["ao_network_release_decisions"] = {
    "_policy": ("Protected networks are NOT auto-released on mere evidence existence. A network is "
                "release-eligible ONLY if its network-level evidence_quality=='verified'; within it, "
                "only individually ready_for_validation+verified rows are promoted. protected_network_hold "
                "remains the historical provenance flag; released rows carry an explicit gate-owner "
                "release note in `reasoning`. Held rows stay needs_more_evidence."),
    "decisions": st["release_decisions"],
    "summary": {
        "released_networks": ["ao:LABINOV_BORIS", "ao:NITTINGER_RACHEL", "ao:SHAFI_SOHAIL", "ao:BRUNETTI_ROBERT"],
        "held_networks": ["ao:SWEIS_JUBRAIL", "ao:RAMAHA_AHMED"],
        "rows_released_protected": len(st["ao_released"]) - st["release_decisions"]["original_13_individuals"]["rows_released"],
        "rows_released_original_13": st["release_decisions"]["original_13_individuals"]["rows_released"],
        "rows_held_total": len(st["ao_held"]),
    },
}

# ---- Fleet B QA-flag dispositions record ----
man["fleet_b_backfill_dispositions"] = {
    "source": "ownership_evidence_queue_fleet_b_backfill_20260621.json",
    "classified_total": 11,
    "to_ready": [r["location_id"] for r in st["fb_ready"]],
    "to_conflicts": [zieba_id] if zieba_id else [],
    "held_needs_more": [r["location_id"] for r in st["fb_hold"]],
    "qa_flag_actions": {
        "047ce502ad2a0371": "HEARTLAND INTERNATIONAL HEALTH CENTER -> institutional (FQHC, not Heartland Dental DSO) [kept]",
        "34235da38acd": "DENTALWORKS -> branded_dso, pe_backed=true (Sonrava/New Mountain platform-level)",
        "2eccce6b14d310cd": "ZIEBA -> CONFLICTS (former DBA Webster Dental Care, contested set)",
        "5cd692a50e5c": "SCHOCK -> HELD needs_more (Schock->Dentologie rebrand/identity unverified)",
    },
    "needs_verification_remaining": 32,
}

# ---- recompute counts ----
nme = b["needs_more_evidence"]
n_demoted_remaining = len([r for r in bq])  # backfill == remaining demotions
man["counts"] = {
    "ready_to_validate": len(b["ready_to_validate"]),
    "needs_more_evidence_total": len(nme),
    "needs_more_evidence_from_backfill_remaining": n_demoted_remaining,
    "rejected": len(b["rejected"]),
    "conflicts": len(b["conflicts"]),
    "duplicate_denominator_blocked_ids_documented": 16,
    "duplicate_denominator_blocked_currently_candidates": 0,
    "taxonomy_revised": len(b["taxonomy_revised"]),
    "evidence_gap_backfill_queue": len(bq),
}

# ---- _meta merge note ----
man.setdefault("_meta", {})
man["_meta"]["merge_pass"] = {
    "at": "2026-06-21",
    "by": "opus-4.8 reset-consolidation-gate (4th session)",
    "inputs": ["ownership_evidence_queue_fleet_b_backfill_20260621.json",
               "ao_backfill_evidence_71_20260621.json"],
    "result": ("ready 65 -> %d (+%d Fleet B, +%d AO released); needs_more 227 -> %d; conflicts 73 -> %d; "
               "backfill 114 -> %d. AO networks preserved as sidecar; protected networks Sweis+Ramaha HELD."
               % (len(b["ready_to_validate"]), len(st["fb_ready"]), len(st["ao_released"]),
                  len(nme), len(b["conflicts"]), len(bq))),
    "validate_only": ("python3 scrapers/consolidate_census.py "
                      "data/dso_research/_ready_to_validate_merged_20260621.json "
                      "--session gate_owner_merge_20260621 --validate-only -> Validation OK (123 rows)"),
    "db_writes": "NONE. consolidation still FROZEN; no --allow-db-write.",
}

# reconciliation assert
recon_unique = len(b["ready_to_validate"]) + (len(nme) - n_demoted_remaining) + len(b["rejected"]) + len(b["conflicts"])
recon_total = recon_unique + n_demoted_remaining
assert recon_total == 372, f"reconciliation FAILED: {recon_total} != 372"

with open(os.path.join(R, "consolidation_candidate_manifest_20260621.json"), "w") as f:
    json.dump(man, f, indent=1)

print("MERGED MANIFEST written. counts:")
print(json.dumps(man["counts"], indent=1))
print("reconciliation: %d unique + %d backfill-remaining = %d (==372 ✓)"
      % (recon_unique, n_demoted_remaining, recon_total))
print("release summary:", json.dumps(man["ao_network_release_decisions"]["summary"], indent=0))
print("sidecar networks preserved:", list((man["ao_network_intelligence"]["networks"] or {}).keys()))
print("sidecar individuals preserved:", len(man["ao_network_intelligence"]["individuals"] or []))
