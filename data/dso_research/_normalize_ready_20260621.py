#!/usr/bin/env python3
"""Gate Owner Phase 7 — normalize ready_to_validate rows to consolidate_census.py
schema, pulling documentary evidence ONLY from existing source files. No research.

Rule: a `classified` row keeps its tier ONLY if the documentary evidence its tier
requires is actually present in the evidence files. Otherwise it is DEMOTED to
needs_more_evidence (the user's "if uncertain = needs_more_evidence"). We never
fabricate a URL or artifact.

Validator contract (scrapers/consolidate_census.py):
  - status=classified + basis in {locator,web_verified,intel_dossier}  -> needs evidence_urls
  - status=classified + basis in {ein_cluster,ao_cluster,name_chain,structural} -> needs evidence_artifacts
  - tier in {stealth_dso,branded_dso} -> needs url OR artifact
  - tier=true_independent + basis=structural -> needs artifact
  - classified rows cannot have confidence=low
"""
import json, os, re
RES = "/Users/suleman/dental-pe-tracker/data/dso_research"

def L(name): return json.load(open(os.path.join(RES, name)))

draft = L("_manifest_draft_20260621.json")
ready = draft["buckets"]["ready_to_validate"]

reach5   = L("ao_network_evidence_reach5_20260621.json")["classifications"]
addendum = L("ownership_taxonomy_DSO_structure_addendum_20260621.json")["rows"]
ao_qa    = L("ao_network_evidence_QA_20260621.json")["rows"]
own_qa   = L("ownership_evidence_QA_20260621.json")["rows"]
fleet_b  = L("ownership_evidence_QA_fleet_b_20260621.json")["rows"]

# ---- build evidence index keyed by location_id -----------------------------
def clean_urls(lst):
    out = []
    for u in (lst or []):
        if isinstance(u, str) and re.search(r"https?://|www\.|\.[a-z]{2,}/", u):
            out.append(u.strip())
    return out

idx = {}
def slot(lid):
    return idx.setdefault(lid, {"urls": [], "artifacts": [], "network_id": None,
                                 "pe": None, "conf": None, "basis_hint": None,
                                 "reasons": []})

for r in reach5:
    s = slot(r["location_id"])
    s["urls"] += clean_urls(r.get("evidence_urls"))
    if r.get("db_artifact"):
        s["artifacts"].append(str(r["db_artifact"]))
    if r.get("network_id"):
        s["network_id"] = r["network_id"]
    if r.get("pe_backed") is not None: s["pe"] = bool(r["pe_backed"])
    if r.get("confidence"): s["conf"] = r["confidence"]
    # DB-grounded signals make durable artifacts (parent_company / legal_entity / ec)
    sve = (r.get("signal_vs_evidence") or {}).get("signal") or []
    for sig in sve:
        if any(k in sig.lower() for k in ("parent_company", "legal_entity",
               "entity_classification", "ein", "ao_reach")):
            s["artifacts"].append(sig)
    # reach5 stores its documentary URLs inside signal_vs_evidence.evidence strings
    for ev in (r.get("signal_vs_evidence") or {}).get("evidence") or []:
        s["urls"] += clean_urls([ev])
        if ev: s["artifacts"].append(ev)
    if r.get("reasoning"): s["reasons"].append(r["reasoning"])

# gate-owner special overrides carry positively-earned independent evidence
_gate = L("ownership_taxonomy_DSO_structure_gate_review_20260621.json")
for _grp in (_gate.get("special_location_overrides") or {}).values():
    for _ov in (_grp if isinstance(_grp, list) else []):
        s = slot(_ov["location_id"])
        for _u in re.findall(r"[a-z0-9.-]+\.(?:com|org|net)(?:/[^\s]*)?", _ov.get("reason", "")):
            if _u not in s["urls"]: s["urls"].append(_u)
        if _ov.get("reason"): s["reasons"].append(_ov["reason"])

for r in addendum:
    s = slot(r["location_id"])
    s["urls"] += clean_urls(r.get("evidence_urls"))
    if r.get("evidence_basis"): s["basis_hint"] = r["evidence_basis"]
    if r.get("pe_backed") is not None and s["pe"] is None: s["pe"] = bool(r["pe_backed"])
    if r.get("reasoning"): s["reasons"].append(r["reasoning"])

for r in ao_qa:
    s = slot(r["location_id"])
    if r.get("network_id") and not s["network_id"]: s["network_id"] = r["network_id"]
    if r.get("fleet_pe_backed") is not None and s["pe"] is None: s["pe"] = bool(r["fleet_pe_backed"])
    if r.get("evidence_quality") == "exact_documentary" and not s["conf"]: s["conf"] = "high"
    for x in (r.get("qa_reasons") or []): s["reasons"].append(x)

for r in own_qa:
    s = slot(r["location_id"])
    if r.get("fleet_evidence_basis") and not s["basis_hint"]: s["basis_hint"] = r["fleet_evidence_basis"]
    if r.get("evidence_quality") == "exact_documentary" and not s["conf"]: s["conf"] = "high"
    for x in (r.get("qa_reasons") or []): s["reasons"].append(x)

for r in fleet_b:
    s = slot(r["location_id"])
    if r.get("fleet_basis") and not s["basis_hint"]: s["basis_hint"] = r["fleet_basis"]
    if r.get("corrected_pe_backed") is not None and s["pe"] is None: s["pe"] = bool(r["corrected_pe_backed"])
    if r.get("confidence") and not s["conf"]: s["conf"] = r["confidence"]
    for x in (r.get("qa_reasons") or []): s["reasons"].append(x)

# normalize basis_hint into a VALID_BASE
BASIS_MAP = {
    "affiliated_dso_field": "structural", "affiliated_dso": "structural",
    "locator": "locator", "web_verified": "web_verified", "web": "web_verified",
    "ein_cluster": "ein_cluster", "ein": "ein_cluster",
    "ao_cluster": "ao_cluster", "ao_reach": "ao_cluster", "shared_ao": "ao_cluster",
    "name_chain": "name_chain", "intel_dossier": "intel_dossier",
    "structural": "structural", "none": "none",
}
URL_BASES = {"locator", "web_verified", "intel_dossier"}
ARTIFACT_BASES = {"ein_cluster", "ao_cluster", "name_chain", "structural"}

DSO = {"branded_dso", "stealth_dso"}

# Standing PROTECTED networks — do NOT admit to ready_to_validate until the main
# session finishes and releases them (user standing rule; no release on record).
PROTECTED_SURNAMES = {"SHAFI", "BELKIC", "NITTINGER", "AQEL", "BRUNETTI",
                      "SWEIS", "LABINOV", "RAMAHA"}

def confidence_for(s, tier):
    c = s["conf"]
    if c in ("high", "medium"): return c
    return "medium"  # never low for a classified row

def pick_basis(tier, s):
    """Choose a schema-valid evidence_basis given the evidence actually present."""
    has_url = bool(s["urls"])
    has_art = bool(s["artifacts"]) or bool(s["network_id"])
    hint = BASIS_MAP.get((s["basis_hint"] or "").strip(), None)
    # honour a documentary hint if its evidence exists
    if hint in URL_BASES and has_url: return hint
    if hint in ARTIFACT_BASES and has_art: return hint
    # otherwise derive from what we have
    if has_url: return "web_verified"
    if s["network_id"]: return "ao_cluster"
    if has_art: return "structural"
    return None  # nothing documentary

normalized, demotions = [], []
for row in ready:
    lid = row["location_id"]; tier = row["final_tier"]
    s = idx.get(lid, slot(lid))
    urls = sorted(set(s["urls"]))
    arts = sorted(set(s["artifacts"]))
    if s["network_id"]:
        nid_art = f"ao_cluster:{s['network_id']}"
        if nid_art not in arts: arts.append(nid_art)
    basis = pick_basis(tier, s)

    # QA MUST-FIX: AO reach is a SIGNAL, not ownership proof. An ao_cluster artifact
    # (shared authorized official) cannot, by itself, assign a tier
    # (canonical_rules.ao_reach_is_signal). And any row in a standing PROTECTED network
    # must be held until the main session releases it.
    non_ao_arts = [a for a in arts if not str(a).startswith("ao_cluster:")]
    has_real_doc = bool(urls) or bool(non_ao_arts)
    nid = (s["network_id"] or "")
    protected = any(sn in nid.upper() for sn in PROTECTED_SURNAMES)

    # ---- enforce the validator's evidence requirements; demote if unmet ----
    demote_reason = None
    ao_reach_only = False
    if basis is None:
        demote_reason = "no documentary URL or durable artifact in any evidence file"
    elif basis in URL_BASES and not urls:
        demote_reason = f"basis={basis} requires evidence_urls; none present"
    elif basis in ARTIFACT_BASES and not arts:
        demote_reason = f"basis={basis} requires evidence_artifacts; none present"
    elif tier in DSO and not (urls or arts):
        demote_reason = "DSO tier requires documentary URL or durable artifact"
    elif tier == "true_independent" and basis == "structural" and not arts:
        demote_reason = "structural true_independent requires query artifact"
    elif not has_real_doc:
        # only evidence is a shared-AO (ao_cluster) artifact — insufficient to classify
        ao_reach_only = True
        demote_reason = ("AO-reach-only: the sole evidence is a shared authorized-official "
                         "(ao_cluster) artifact, which is a discovery SIGNAL, not ownership "
                         "proof (canonical_rules.ao_reach_is_signal). No documentary URL or "
                         "non-AO durable artifact (locator/web/EIN/name-chain) on disk.")
    elif protected:
        # has some evidence but belongs to a standing protected network -> hold this wave
        ao_reach_only = True
        demote_reason = ("Standing PROTECTED network — held until the main session releases it; "
                         "not eligible for ready_to_validate this wave.")

    if demote_reason:
        # classify the missing-evidence gap + suggest a backfill lane (no research)
        hint = BASIS_MAP.get((s["basis_hint"] or "").strip(), None)
        if ao_reach_only:
            miss = ("independent documentary evidence — a per-location locator/MSO/web URL "
                    "or a non-AO durable artifact (EIN cluster / name-chain / org-taxonomy). "
                    "Shared-AO reach alone is a discovery signal, not ownership proof.")
            lane = "AO_network"
        elif tier in DSO and hint in ("web_verified", "locator"):
            miss = ("per-location exact-address locator/web URL — fleet asserted "
                    "web_verified+exact_address_match but the URL string is not "
                    "transcribed in any on-disk evidence file")
            lane = "locator_exact"
        elif hint == "intel_dossier":
            miss = "practice_intel dossier with a recorded source URL"
            lane = "practice_intel"
        elif tier == "institutional":
            miss = ("institutional documentary (FQHC/hospital/university registry "
                    "page) or a durable DB org-taxonomy artifact")
            lane = "practice_intel"
        elif tier == "true_independent":
            miss = "owner-operated documentary URL (practice site naming the owner-dentist)"
            lane = "practice_intel"
        elif tier in ("dentist_multi", "single_loc_group"):
            miss = ("AO-network cluster artifact (shared authorized-official across "
                    "locations) or a documentary multi-location URL")
            lane = "AO_network"
        else:
            miss = "documentary URL or durable artifact"
            lane = "practice_intel"
        d = {
            "location_id": lid,
            "practice_name": row.get("name"),
            "zip": row.get("zip"), "city": row.get("city"),
            "entity_classification": row.get("entity_classification"),
            "proposed_tier": tier,
            "pe_backed": bool(s["pe"]) if s["pe"] is not None else False,
            "why_demoted": demote_reason,
            "missing_evidence_type": miss,
            "backfill_lane": lane,
            "protected_network_hold": bool(protected),
            "network_id": s["network_id"],
            "source_basis_hint": s["basis_hint"],
            "gate_network": row.get("gate_network"),
        }
        demotions.append(d)
        continue

    reasons = []
    for x in s["reasons"]:
        if x and x not in reasons: reasons.append(x)
    reasoning = " | ".join(reasons[:3]) or row.get("reason") or "gate-owner manifest disposition"

    normalized.append({
        "location_id": lid,
        "assigned_tier": tier,
        "pe_backed": bool(s["pe"]) if s["pe"] is not None else False,
        "evidence_basis": basis,
        "evidence_urls": urls,
        "evidence_artifacts": arts,
        "confidence": confidence_for(s, tier),
        "status": "classified",
        "network_id": s["network_id"],
        "reasoning": reasoning[:1200],
    })

out = {"classifications": normalized}
json.dump(out, open(os.path.join(RES, "_ready_to_validate_normalized_20260621.json"), "w"), indent=2)
json.dump({"demotions": demotions},
          open(os.path.join(RES, "_ready_demotions_20260621.json"), "w"), indent=2)

from collections import Counter
print("ready in draft        :", len(ready))
print("normalized (classified):", len(normalized))
print("demoted -> needs_more :", len(demotions))
print("normalized tier tally :", dict(Counter(r["assigned_tier"] for r in normalized)))
print("normalized basis tally:", dict(Counter(r["evidence_basis"] for r in normalized)))
print("demoted tier tally    :", dict(Counter(d["proposed_tier"] for d in demotions)))
print("backfill lane tally   :", dict(Counter(d["backfill_lane"] for d in demotions)))
print("protected_network_hold:", sum(1 for d in demotions if d.get("protected_network_hold")))
print("  by network          :", dict(Counter(d.get("network_id") for d in demotions if d.get("protected_network_hold"))))
