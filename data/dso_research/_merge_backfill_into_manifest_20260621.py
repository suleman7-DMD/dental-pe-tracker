#!/usr/bin/env python3
"""
Gate Owner merge pass (2026-06-21): fold BOTH backfill outputs into the next manifest.

  - Fleet B non-AO backfill  -> ownership_evidence_queue_fleet_b_backfill_20260621.json
  - Main AO network evidence -> ao_backfill_evidence_71_20260621.json   (STRATEGIC SIDECAR)

Rules honored (verbatim from user):
  * Treat the Main AO file as strategic NETWORK evidence, not a direct validator queue.
    Its `networks` + `individuals` + `_meta` are copied into a manifest SIDECAR section
    `ao_network_intelligence` -- NOTHING flattened (ao_name, owner/family identity, members,
    URLs, stale/closed notes, evidence_chain all preserved verbatim).
  * The 58 protected rows still carry protected_network_hold=true. Do NOT auto-release just
    because evidence exists -> per-network DELIBERATE decision below.
  * Re-run validate-only ONLY on rows that become clean validator-native ready rows.
  * No DB writes. (This script writes JSON artifacts only; validate-only is run separately.)

PER-NETWORK DECISION (the gate-owner judgment, higher bar than the AO file's own row gate):
  A protected network is RELEASED only if its network-level evidence_quality == 'verified'
  AND, within it, only rows that are individually row_gate_status=='ready_for_validation'
  AND evidence_quality=='verified' are promoted. Partial-only networks are HELD whole.
"""
import json, os

R = "data/dso_research"
def load(p):
    with open(os.path.join(R, p)) as f:
        return json.load(f)

manifest = load("consolidation_candidate_manifest_20260621.json")
ready65  = load("_ready_to_validate_normalized_20260621.json")
ready65  = ready65["classifications"] if isinstance(ready65, dict) else ready65
fleetb   = load("ownership_evidence_queue_fleet_b_backfill_20260621.json")
ao       = load("ao_backfill_evidence_71_20260621.json")

CANON = ["location_id","assigned_tier","pe_backed","evidence_basis","evidence_urls",
         "evidence_artifacts","confidence","status","network_id","reasoning"]
def canon(rec):
    return {k: rec.get(k) for k in CANON}

def aslist(x):
    if x is None: return []
    return x if isinstance(x, list) else [x]

# ---------------------------------------------------------------- Fleet B (non-AO)
# 11 classified rows. QA-flag dispositions:
#   2eccce6b14d3 ZIEBA  -> CONFLICTS  (former DBA 'Webster Dental Care'; touches contested Webster set)
#   5cd692a50e5c SCHOCK -> HOLD       (name/identity ambiguity Schock->Dentologie rebrand unverified)
#   34235da38acd DENTALWORKS -> ready, pe_backed=True (Sonrava/New Mountain platform-level PE)
#   047ce502ad2a HEARTLAND INTL -> already institutional (FQHC, not Heartland Dental) -- kept
FB_TO_CONFLICT = {"2eccce6b14d310cd"}
FB_TO_HOLD     = {"5cd692a50e5c"}  # prefix-safe match below
fb_classified = [r for r in fleetb["classifications"] if r.get("status") == "classified"]

def lid_match(lid, shortset):
    return any(lid.startswith(s) or s.startswith(lid) for s in shortset)

fb_ready, fb_conflict, fb_hold = [], [], []
for r in fb_classified:
    lid = r["location_id"]
    if lid_match(lid, FB_TO_CONFLICT):
        fb_conflict.append(r)
    elif lid_match(lid, FB_TO_HOLD):
        fb_hold.append(r)
    else:
        rec = {
            "location_id": lid,
            "assigned_tier": r.get("assigned_tier"),
            "pe_backed": True if lid.startswith("34235da38acd") else bool(r.get("pe_backed", False)),
            "evidence_basis": r.get("evidence_basis"),
            "evidence_urls": aslist(r.get("evidence_urls")),
            "evidence_artifacts": aslist(r.get("evidence_artifacts")),
            "confidence": r.get("confidence"),
            "status": "classified",
            "network_id": r.get("network_id"),
            "reasoning": "[fleet_b backfill] " + (r.get("reasoning") or ""),
        }
        fb_ready.append(rec)

# ---------------------------------------------------------------- Main AO
nets = ao["networks"]
rows = ao["rows"]
indiv_by_lid = {i["location_id"]: i for i in ao["individuals"]}

# network release eligibility = network-level verified
RELEASE_NETS = {nid for nid, n in nets.items() if n.get("evidence_quality") == "verified"}
HOLD_NETS    = {nid for nid, n in nets.items() if n.get("evidence_quality") != "verified"}

def row_releasable(r):
    return r.get("row_gate_status") == "ready_for_validation" and r.get("evidence_quality") == "verified"

ao_released, ao_held = [], []
release_decisions = {}

for nid, n in nets.items():
    net_rows = [r for r in rows if r.get("network_id") == nid]
    arts = aslist(n.get("durable_non_ao_artifact"))
    urls = aslist(n.get("key_documentary_urls"))
    rel_n, held_n = 0, 0
    for r in net_rows:
        if nid in RELEASE_NETS and row_releasable(r):
            rec = {
                "location_id": r["location_id"],
                "assigned_tier": r.get("evidence_tier"),
                "pe_backed": bool(r.get("pe_backed", False)),
                "evidence_basis": "name_chain",  # durable cross-location structural artifact
                "evidence_urls": urls,
                "evidence_artifacts": arts,
                "confidence": "high",
                "status": "classified",
                "network_id": nid,
                "reasoning": ("[AO network %s | RELEASED from protected_network_hold by gate owner] "
                              % nid) + (n.get("tier_rationale") or ""),
            }
            ao_released.append(rec)
            rel_n += 1
        else:
            ao_held.append({"location_id": r["location_id"], "network_id": nid,
                            "row_gate_status": r.get("row_gate_status"),
                            "evidence_quality": r.get("evidence_quality"),
                            "evidence_tier": r.get("evidence_tier"),
                            "protected_network_hold": True})
            held_n += 1
    release_decisions[nid] = {
        "network_evidence_quality": n.get("evidence_quality"),
        "decision": "release_eligible" if nid in RELEASE_NETS else "hold_whole_network",
        "rows_total": len(net_rows), "rows_released": rel_n, "rows_held": held_n,
        "tier": n.get("evidence_tier"), "pe_backed": n.get("pe_backed"),
        "rationale": (
            ("RELEASED: network-level documentary structure/owner evidence is VERIFIED (%s). "
             "Only individually verified+ready rows promoted; partial/candidate rows held." % n.get("evidence_quality"))
            if nid in RELEASE_NETS else
            ("HELD: network evidence_quality=%s (no verified rows) + stale/closed false-positive caveats "
             "-> stays needs_more_evidence, protected_network_hold preserved." % n.get("evidence_quality"))
        ),
        "stale_closed_notes": n.get("stale_closed_false_positive_notes"),
    }

# original-13 (network_id is None, protected_network_hold False) -- not protected, release verified+ready
o13 = [r for r in rows if not r.get("protected_network_hold")]
o13_released = 0
for r in o13:
    lid = r["location_id"]
    ind = indiv_by_lid.get(lid, {})
    if row_releasable(r):
        u = aslist(ind.get("documentary_urls"))
        a = aslist(ind.get("durable_non_ao_artifact"))
        basis = "web_verified" if u else ("name_chain" if a else "structural")
        rec = {
            "location_id": lid,
            "assigned_tier": r.get("evidence_tier"),
            "pe_backed": bool(r.get("pe_backed", False)),
            "evidence_basis": basis,
            "evidence_urls": u,
            "evidence_artifacts": a,
            "confidence": "high",
            "status": "classified",
            "network_id": None,
            "reasoning": "[AO original_13 individual] " + (ind.get("reasoning") or r.get("practice_name","")),
        }
        ao_released.append(rec)
        o13_released += 1
    else:
        ao_held.append({"location_id": lid, "network_id": None,
                        "row_gate_status": r.get("row_gate_status"),
                        "evidence_quality": r.get("evidence_quality"),
                        "evidence_tier": r.get("evidence_tier"),
                        "protected_network_hold": False})
release_decisions["original_13_individuals"] = {
    "decision": "release_verified_ready_only", "rows_total": len(o13),
    "rows_released": o13_released, "rows_held": len(o13) - o13_released,
    "rationale": "Not protected; promoted only rows that are ready_for_validation AND verified.",
}

# ---------------------------------------------------------------- assemble new ready set + dedupe
new_ready = [canon(r) for r in ready65] + fb_ready + [canon(r) for r in ao_released]
seen, deduped, dups = set(), [], []
for r in new_ready:
    if r["location_id"] in seen:
        dups.append(r["location_id"]); continue
    seen.add(r["location_id"]); deduped.append(r)
new_ready = deduped

# collision check vs conflicts/rejected
conflict_ids = {c["location_id"] for c in manifest["buckets"]["conflicts"]}
rejected_ids = {c["location_id"] for c in manifest["buckets"]["rejected"]}
overlap_conf = [r["location_id"] for r in new_ready if r["location_id"] in conflict_ids]
overlap_rej  = [r["location_id"] for r in new_ready if r["location_id"] in rejected_ids]

# ---------------------------------------------------------------- write merged validate file
out_ready = os.path.join(R, "_ready_to_validate_merged_20260621.json")
with open(out_ready, "w") as f:
    json.dump({"classifications": new_ready}, f, indent=1)

# ---------------------------------------------------------------- report
from collections import Counter
print("=== FLEET B ===")
print("  ready:", len(fb_ready), "conflict(Zieba):", len(fb_conflict), "hold(Schock):", len(fb_hold))
print("=== MAIN AO ===")
print("  release-eligible nets:", sorted(RELEASE_NETS))
print("  hold nets:", sorted(HOLD_NETS))
print("  AO released rows:", len(ao_released), "(protected:", len(ao_released)-o13_released,
      "+ original_13:", o13_released, ")")
print("  AO held rows:", len(ao_held))
for nid, d in release_decisions.items():
    print(f"    {nid:28} {d['decision']:24} released={d.get('rows_released')} held={d.get('rows_held')}")
print("=== NEW READY SET ===")
print("  total ready:", len(new_ready), "(65 +", len(fb_ready), "fleetB +", len(ao_released), "AO; dupes dropped:", len(dups), ")")
print("  tier mix:", dict(Counter(r["assigned_tier"] for r in new_ready)))
print("  basis mix:", dict(Counter(r["evidence_basis"] for r in new_ready)))
print("  collisions w/ conflicts:", overlap_conf, "| w/ rejected:", overlap_rej, "| internal dupes:", dups)
print("  wrote", out_ready)

# stash computed pieces for the assembler step
import pickle
with open(os.path.join(R, "_merge_state_20260621.pkl"), "wb") as f:
    pickle.dump({
        "new_ready": new_ready, "fb_ready": fb_ready, "fb_conflict": fb_conflict,
        "fb_hold": fb_hold, "ao_released": ao_released, "ao_held": ao_held,
        "release_decisions": release_decisions,
    }, f)
print("  stashed merge state for assembler")
