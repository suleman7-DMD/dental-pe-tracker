#!/usr/bin/env python3
"""Gate Owner Phase 7 — assemble the canonical consolidation candidate manifest.
READ-ONLY: reads the draft + normalized ready + demotions + denominator review and
writes consolidation_candidate_manifest_20260621.json. No DB writes, no research."""
import json, os
RES = "/Users/suleman/dental-pe-tracker/data/dso_research"
def L(n): return json.load(open(os.path.join(RES, n)))

draft   = L("_manifest_draft_20260621.json")
ready   = L("_ready_to_validate_normalized_20260621.json")["classifications"]
demoted = L("_ready_demotions_20260621.json")["demotions"]
dr      = L("evidence_denominator_review_20260621.json")
gate    = L("ownership_taxonomy_DSO_structure_gate_review_20260621.json")

B = draft["buckets"]
nme_original = B["needs_more_evidence"]            # 113 from the gate disposition pass
rejected     = B["rejected"]                       # 7
conflicts    = B["conflicts"]                      # 73
taxrev       = draft["taxonomy_revised_index"]     # 14

# the 56 demoted rows are needs_more_evidence too (tagged) AND the backfill queue
nme_demoted = [dict(d, from_ready_demotion=True) for d in demoted]
needs_more_evidence = nme_original + nme_demoted

# duplicate-door denominator hazard (documented; 0 are current candidates)
dup_rows = dr["tier_contradictions_at_dup_addresses"]["rows"]
dup_ids = sorted({i for r in dup_rows for i in r.get("location_ids", [])})
cand_ids = {r["location_id"] for r in ready} | {r["location_id"] for r in needs_more_evidence} \
         | {r["location_id"] for r in rejected} | {r["location_id"] for r in conflicts}
dup_in_candidates = sorted(set(dup_ids) & cand_ids)

manifest = {
    "_meta": {
        "title": "Consolidation Candidate Manifest — Gate Owner canonical",
        "date": "2026-06-21",
        "author_role": "Reset + Consolidation Gate Owner (4th session)",
        "consolidation_status": ("FROZEN — validate-only only. consolidate_census.py "
            "--allow-db-write is NOT authorized until the user explicitly says "
            "'consolidate approved manifest'."),
        "scope": "Chicagoland / IL watched ZIPs ONLY. Boston/MA PARKED — not touched.",
        "no_research_attestation": ("Built only from evidence files already on disk. "
            "No agents, no web search, no new evidence. Rows lacking the documentary "
            "evidence their tier requires were demoted to needs_more_evidence rather "
            "than rescued with inferred/fabricated name-chain/AO/locator artifacts."),
        "inputs": [
            "ownership_evidence_QA_20260621.json",
            "ao_network_evidence_QA_20260621.json",
            "ownership_evidence_QA_fleet_b_20260621.json",
            "ao_network_evidence_reach5_20260621.json",
            "ownership_taxonomy_DSO_structure_addendum_20260621.json (QA file; read, not overwritten)",
            "evidence_denominator_review_20260621.json",
        ],
        "taxonomy_authority": "ownership_taxonomy_DSO_structure_gate_review_20260621.json",
        "canonical_rules": gate.get("canonical_rule"),
        "headline_rules": {
            "consolidated": "T2 single_loc_group + T3 dentist_multi + T4 stealth_dso + T5 branded_dso",
            "dso_pe": "T4 stealth_dso + T5 branded_dso only",
            "no_anchor": "consolidation % is computed FROM the census ledger with coverage; "
                         "never anchored to ADA 14.6% or the 5% detector floor.",
        },
        "bucket_definitions": {
            "ready_to_validate": "Documentary URL or durable artifact on disk; tier+evidence "
                "satisfy consolidate_census.py validate-only; no cross-source conflict.",
            "needs_more_evidence": "Disposition uncertain OR demoted from a ready tier for "
                "lack of on-disk documentary evidence. Includes the evidence_gap_backfill_queue rows.",
            "rejected": "Out of scope / excluded class / specialist-only / QA should_NOT_consolidate.",
            "conflicts": "Cross-source equivalence-class disagreement at the same location_id "
                "(e.g. addendum=DSO vs reach5/ao_QA=dentist_multi). Gate does NOT unilaterally resolve.",
            "duplicate_denominator_blocked": "Named HIGH duplicate-door tier contradictions "
                "(shared phone/owner, different tiers). Documented denominator hazard.",
            "taxonomy_revised": "Tier changed under the corrected DSO=structure taxonomy "
                "(e.g. Dental Dreams/KOS → branded_dso; pe_backed orthogonal).",
            "evidence_gap_backfill_queue": "The needs_more_evidence subset that was demoted "
                "from a ready tier — each row carries the missing-evidence type + suggested backfill lane.",
        },
        "overlap_note": ("evidence_gap_backfill_queue == the %d needs_more_evidence rows tagged "
                         "from_ready_demotion=true. They are listed in both places by design; "
                         "do not double-count." % len(nme_demoted)),
        "validate_only_target": "buckets.ready_to_validate (normalized schema in "
                                "_ready_to_validate_normalized_20260621.json)",
    },
    "counts": {
        "ready_to_validate": len(ready),
        "needs_more_evidence_total": len(needs_more_evidence),
        "needs_more_evidence_gate_disposition": len(nme_original),
        "needs_more_evidence_from_ready_demotion": len(nme_demoted),
        "rejected": len(rejected),
        "conflicts": len(conflicts),
        "duplicate_denominator_blocked_ids_documented": len(dup_ids),
        "duplicate_denominator_blocked_currently_candidates": len(dup_in_candidates),
        "taxonomy_revised": len(taxrev),
        "evidence_gap_backfill_queue": len(demoted),
    },
    "buckets": {
        "ready_to_validate": ready,
        "needs_more_evidence": needs_more_evidence,
        "rejected": rejected,
        "conflicts": conflicts,
        "duplicate_denominator_blocked": {
            "note": ("These %d location_ids (8 HIGH duplicate-door pairs) carry conflicting "
                     "ownership_tier on duplicate rows of the SAME physical door. NONE are in the "
                     "current candidate set (their tiers came from the now-reset wave-1 census), so "
                     "0 were blocked out of ready_to_validate — listed here as a denominator hazard "
                     "any future wave must resolve before consolidating these addresses."
                     % len(dup_ids)),
            "currently_in_candidate_set": dup_in_candidates,
            "pairs": dup_rows,
        },
        "taxonomy_revised": taxrev,
    },
    "evidence_gap_backfill_queue": demoted,
    "denominator_caveat": draft.get("collapse_note"),
}

path = os.path.join(RES, "consolidation_candidate_manifest_20260621.json")
json.dump(manifest, open(path, "w"), indent=2)
print("WROTE", path)
print(json.dumps(manifest["counts"], indent=2))
