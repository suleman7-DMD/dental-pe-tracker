#!/usr/bin/env python3
"""Build the consolidated census-candidate file (PM normalization, 2026-07-02).

Merges four PM-accepted sources into ONE validator-schema candidate file plus a
holds companion. FILES-ONLY: no DB writes, no ledger writes. The output must
pass `consolidate_census.py <out> --session ... --validate-only` with 0 errors
before it is even ELIGIBLE for the (user-gated) --allow-db-write step.

Sources (all previously PM-reviewed this session — see SESSION_PROTOCOL):
  1. the 310 ready file (URL hygiene repaired; weak-68 verdicts applied)
  2. Wave-4 partition-1 merge_eligible_new (19)
  3. Lane-2 partition: 1 corporate + 12 corroborations + 2 true_independent
  4. Lane-3 51-100 merge_eligible_new (5, minus Archer rank-83 -> holds per QA)

Deterministic URL hygiene (same rules everywhere):
  - valid http(s) URL string          -> evidence_urls
  - dict with a valid 'url' key       -> url extracted to evidence_urls; whole
                                         dict preserved in evidence_artifacts
  - glued 'https://x  (prose)' string -> leading token to evidence_urls if it
                                         validates; original string preserved
                                         in evidence_artifacts
  - bare domain ('example.com/path')  -> 'https://'+domain to evidence_urls
                                         (mechanical scheme normalization);
                                         original preserved in artifacts
  - anything else (prose, notes)      -> evidence_artifacts

No evidence is dropped — entries that stop being URLs become artifacts.
"""
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from urllib.parse import urlsplit

ROOT = "/Users/suleman/dental-pe-tracker"
DSO = os.path.join(ROOT, "data", "dso_research")
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
W4 = os.path.join(DSO, "_wave4_20260621")

SRC_310 = os.path.join(DSO, "_ready_to_validate_wave3_fixed_20260621.json")
SRC_WEAK68 = os.path.join(DSO, "weak_dso_row_review_20260702.json")
SRC_W4P1 = os.path.join(W4, "wave4_gate_normalized_partition_20260621.json")
SRC_LANE2 = os.path.join(W4, "wave4_gate_normalized_lane2_partition_20260622.json")
SRC_LANE3 = os.path.join(W4, "wave4_gate_normalized_lane3_51_100_20260702.json")

OUT_MAIN = os.path.join(DSO, "_census_candidate_consolidated_20260702.json")
OUT_HOLDS = os.path.join(DSO, "_census_holds_20260702.json")

ARCHER_LANE3_HOLD = "8d81d4516f493d1e"  # rank 83 — QA: ownership unconfirmed
# rank 100 "Advanced Family Dental" (Shorewood 60404): DA_ synthetic NPI
# remnant (DA_c396391041ac, no phone) — the fail-closed validator refuses DA_
# rows as final. The real practice row 0d376204167d44a6 (ADVANCED FAMILY
# DENTAL OF SHOREWOOD, P.C., federal NPI 1932386810, house number 150, same
# ZIP) is ALREADY dso_regional — the GLDP/Shore evidence corroborates an
# already-counted corporate practice, NOT net-new floor lift. Route to the
# scope-correction queue (da_unverified-style reclass + possible
# duplicate_location vs 0d376204167d44a6).
DA_SYNTH_LANE3_HOLD = "6c31d482e9a63431"
R4_NETWORKS = ("NITTINGER", "SHAFI", "LABINOV")

# ── PM decisions 2026-07-02 (user delegated: "make the best answers to the
#    decisions ... then proceed") — full record in
#    RESEARCH_HOME/DECISIONS_PM_20260702.md ──────────────────────────────────
# R1 RATIFIED: ADI stays in the GP denominator, tier T5 branded_dso — the 3
# Affordable policy holds are reinstated as classified.
R1_RATIFIED = True
# R4 RATIFIED (procedure) + named networks decided: NITTINGER ACCEPT T5,
# LABINOV ACCEPT T5, SHAFI ACCEPT T3. Rows keep r4_flag for audit trail.
R4_DECIDED = {"NITTINGER": "ACCEPT_T5", "LABINOV": "ACCEPT_T5",
              "SHAFI": "ACCEPT_T3"}
# R5 RATIFIED: the census must not classify a row sitting in the closure
# queue's mark_likely_closed set UNLESS that closure item is adjudicated.
# Cross-check is enforced below. Two candidates hit the set; both closure
# flags are contradicted by stronger direct evidence — adjudicated ACTIVE:
SRC_CLOSURE = os.path.join(DSO, "closure_candidates_review_20260702.json")
R5_ADJUDICATED_ACTIVE = {
    "8acd52381e465e57": (
        "Geneva Dental Ltd: the closure evidence itself states the CLOSED "
        "Yelp listing is the PRIOR address (401 Williamsburg Ave) and the "
        "practice relocated TO this row's address (2172 Blackberry Dr); the "
        "2026-04-26 intel dossier + live practice website (drtingzon.com) "
        "confirm an active solo practice at the new address."),
    "b2445373c7020d73": (
        "MetroSmiles Archer Heights: the closure flag cites BBB complaints "
        "and negative reviews — reputation evidence, not operating-status "
        "evidence; the address is confirmed on the brand's own current "
        "locator page (metrosmiles official site)."),
}

BARE_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(/[^\s]*)?$", re.I)


def is_http_url(value):
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or re.search(r"\s", v):
        return False
    try:
        parts = urlsplit(v)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and "." in (parts.netloc or "")


def repair_url_entries(entries):
    """Split a mixed evidence_urls list into (valid_urls, artifacts, notes)."""
    urls, artifacts, notes = [], [], []
    for e in entries or []:
        if isinstance(e, dict):
            u = e.get("url") or e.get("source_url")
            if is_http_url(u):
                urls.append(u.strip())
                notes.append("dict entry: url extracted, dict kept as artifact")
            else:
                notes.append("dict entry without valid url moved to artifacts")
            if e:
                artifacts.append(e)
            continue
        if not isinstance(e, str) or not e.strip():
            continue
        s = e.strip()
        if is_http_url(s):
            urls.append(s)
            continue
        first = s.split()[0].rstrip(").,;")
        if is_http_url(first):
            urls.append(first)
            artifacts.append(s)
            notes.append("glued URL+prose: leading URL extracted, original kept")
            continue
        if BARE_DOMAIN_RE.match(s):
            urls.append("https://" + s)
            artifacts.append(s)
            notes.append(f"bare domain {s!r} scheme-normalized to https://")
            continue
        artifacts.append(s)
        notes.append("prose entry moved to artifacts")
    # dedupe, order-preserving
    seen = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))]
    return urls, artifacts, notes


def repair_row_urls(row):
    urls, extra_arts, notes = repair_url_entries(row.get("evidence_urls"))
    arts = [a for a in (row.get("evidence_artifacts") or [])
            if (isinstance(a, dict) and a) or (isinstance(a, str) and a.strip())]
    arts.extend(extra_arts)
    row["evidence_urls"] = urls
    row["evidence_artifacts"] = arts
    if notes:
        row.setdefault("normalization_notes", []).extend(sorted(set(notes)))
    return row


def parse_tier(proposed):
    """'dentist_multi (T3)' -> 'dentist_multi'; passthrough for clean values."""
    return re.sub(r"\s*\(T\d\)\s*$", "", str(proposed or "")).strip()


def compose_reasoning(parts):
    return " | ".join(p.strip() for p in parts if p and str(p).strip())


def convert_partition_row(r, provenance):
    """Convert a gate-partition row to validator schema."""
    ev = r.get("evidence") or {}
    pool = []
    pool.extend(ev.get("evidence_urls") or [])
    for k in ("evidence_source", "pe_backed_citation"):
        if ev.get(k):
            pool.append(ev[k])
    urls, extra_arts, notes = repair_url_entries(pool)
    artifacts = [ev] if ev else []
    artifacts.extend(a for a in extra_arts if isinstance(a, dict))

    if urls:
        basis = "web_verified"
    elif "lane1" in (r.get("source_lane") or ""):
        basis = "ao_cluster"
    else:
        basis = "name_chain"

    reasoning = compose_reasoning([
        r.get("dso_structure_rationale"),
        r.get("operating_status_check") and
        f"operating status: {r['operating_status_check']}",
        r.get("same_door_check") and f"same-door: {r['same_door_check']}",
        r.get("gate_note") or r.get("annotation"),
        f"[{provenance}; converted to validator schema by PM normalizer "
        f"2026-07-02; PM-accepted per SESSION_PROTOCOL_FABLE_PM_20260702]",
    ])
    out = {
        "location_id": r["location_id"],
        "practice_name": r.get("practice_name"),
        "city": r.get("city"),
        "zip": r.get("zip"),
        "assigned_tier": parse_tier(r.get("proposed_tier")),
        "pe_backed": bool(r.get("pe_backed")),
        "evidence_basis": basis,
        "confidence": "medium",
        "status": "classified",
        "reasoning": reasoning,
        "evidence_urls": urls,
        "evidence_artifacts": artifacts,
        "source_partition": provenance,
    }
    net = r.get("network") or (
        r.get("candidate_types") if isinstance(r.get("candidate_types"), str)
        else None)
    if net:
        out["network_id"] = net
    if notes:
        out["normalization_notes"] = sorted(set(notes))
    return out


def tag_r4(row):
    hay = " ".join(str(row.get(k) or "") for k in
                   ("network_id", "reasoning", "practice_name"))
    for name in R4_NETWORKS:
        if name in hay.upper():
            row["r4_flag"] = ("protected_network_pending_user_signoff:"
                              + name)
            return


def main():
    ready = json.load(open(SRC_310))["classifications"]
    weak = json.load(open(SRC_WEAK68))["rows"]
    verdicts = {w["location_id"]: w for w in weak}
    w4p1 = json.load(open(SRC_W4P1))["buckets"]
    lane2 = json.load(open(SRC_LANE2))["buckets"]
    lane3 = json.load(open(SRC_LANE3))["buckets"]

    classifications, holds = [], []

    # ---- 1. the 310: apply weak-68 verdicts, repair URLs -------------------
    stats = Counter()
    for row in ready:
        lid = row["location_id"]
        v = verdicts.get(lid)
        verdict = v["verdict"] if v else None
        if verdict == "DOWNGRADE_TO_HOLD":
            holds.append({
                "location_id": lid, "practice_name": row.get("practice_name"),
                "hold_reason": "weak68_downgrade_to_hold",
                "detail": v.get("rationale"),
                "original_tier": row.get("assigned_tier"),
                "source": "ready310 + weak_dso_row_review_20260702",
            })
            stats["310_to_hold_weak68"] += 1
            continue
        if verdict == "HOLD_PENDING_POLICY":
            if R1_RATIFIED:
                row["reasoning"] = compose_reasoning([
                    row.get("reasoning"),
                    "[GP_SCOPE_POLICY R1 RATIFIED 2026-07-02 (user-delegated "
                    "PM decision, DECISIONS_PM_20260702.md): ADI stays in the "
                    "GP denominator, tier T5 branded_dso — policy hold "
                    "released, row reinstated.]"])
                stats["310_R1_reinstated"] += 1
            else:
                holds.append({
                    "location_id": lid,
                    "practice_name": row.get("practice_name"),
                    "hold_reason": "weak68_policy_hold_affordable_R1",
                    "detail": v.get("rationale"),
                    "original_tier": row.get("assigned_tier"),
                    "source": "ready310 + weak_dso_row_review_20260702",
                    "reinstate_on": "user ratifies GP_SCOPE_POLICY R1 "
                                    "(ADI=T5)",
                })
                stats["310_to_hold_policy_R1"] += 1
                continue
        if verdict == "DOWNGRADE_TO_T3":
            row["assigned_tier"] = "dentist_multi"
            row["reasoning"] = compose_reasoning([
                row.get("reasoning"),
                f"[weak-68 PM review 2026-07-02: retiered branded_dso->"
                f"dentist_multi — {v.get('rationale')}]"])
            stats["310_retier_T3"] += 1
        repair_row_urls(row)
        tag_r4(row)
        row["source_partition"] = "ready310_20260621"
        classifications.append(row)
    stats["310_kept"] = len([c for c in classifications])

    # ---- 2. Wave-4 partition-1 merge-eligible (19) -------------------------
    for r in w4p1["merge_eligible_new"]:
        row = convert_partition_row(
            r, "wave4_gate_normalized_partition_20260621 bucket "
               "merge_eligible_new")
        tag_r4(row)
        classifications.append(row)
        stats["w4p1_merge"] += 1

    # ---- 3. Lane-2 (1 corporate + 12 corroborations + 2 independent) -------
    for bucket in ("merge_eligible_new_corporate",
                   "corroborates_existing_corporate_no_lift",
                   "true_independent_confirmation"):
        for r in lane2[bucket]:
            row = convert_partition_row(
                r, f"wave4_gate_normalized_lane2_partition_20260622 "
                   f"bucket {bucket}")
            tag_r4(row)
            classifications.append(row)
            stats[f"lane2_{bucket}"] += 1

    # ---- 4. Lane-3 51-100 merge-eligible (5 minus Archer minus DA_ row) ----
    for r in lane3["merge_eligible_new"]:
        if r["location_id"] == DA_SYNTH_LANE3_HOLD:
            holds.append({
                "location_id": r["location_id"],
                "practice_name": r.get("practice_name"),
                "hold_reason": "da_synthetic_npi_scope_correction_queue",
                "detail": ("PM catch 2026-07-02 via fail-closed validator: "
                           "row carries DA_ synthetic NPI DA_c396391041ac "
                           "(Data-Axle remnant, no phone). Real practice row "
                           "0d376204167d44a6 (ADVANCED FAMILY DENTAL OF "
                           "SHOREWOOD, P.C., NPI 1932386810, same house "
                           "number/ZIP) is ALREADY dso_regional. GLDP/Shore "
                           "evidence = corroboration of an already-counted "
                           "corporate practice; NOT net-new floor lift. "
                           "Route: scope-correction queue (da_unverified "
                           "reclass + possible duplicate_location merge)."),
                "original_tier": parse_tier(r.get("proposed_tier")),
                "source": "wave4_gate_normalized_lane3_51_100_20260702 + "
                          "PM validator run 2026-07-02",
            })
            stats["lane3_to_hold_da_synthetic"] += 1
            continue
        if r["location_id"] == ARCHER_LANE3_HOLD:
            holds.append({
                "location_id": r["location_id"],
                "practice_name": r.get("practice_name"),
                "hold_reason": "lane3_pending_ownership_confirmation",
                "detail": ("QA verdict PASS_WITH_HOLDS (2026-07-02): "
                           "'dentist-owned' claim for Archer Dentistry not "
                           "confirmed by independent evidence; do not count "
                           "toward coverage/floor until ownership resolved."),
                "original_tier": parse_tier(r.get("proposed_tier")),
                "source": "wave4_gate_normalized_lane3_51_100_20260702 + "
                          "VERDICT_QA_WAVE4_LANE3_51_100_20260702",
            })
            stats["lane3_to_hold_archer"] += 1
            continue
        row = convert_partition_row(
            r, "wave4_gate_normalized_lane3_51_100_20260702 bucket "
               "merge_eligible_new (QA PASS_WITH_HOLDS)")
        tag_r4(row)
        classifications.append(row)
        stats["lane3_merge"] += 1

    # ---- R5 operating-status cross-check (ratified 2026-07-02) -------------
    # No candidate may be classified while sitting in the closure queue's
    # mark_likely_closed set, unless the closure item is PM-adjudicated.
    closure_rows = None
    for v in json.load(open(SRC_CLOSURE)).values():
        if (isinstance(v, list) and v and isinstance(v[0], dict)
                and "location_id" in v[0]):
            closure_rows = v
            break
    likely_closed = {r["location_id"] for r in closure_rows
                     if r.get("proposed_action") == "mark_likely_closed"}
    kept = []
    for c in classifications:
        lid = c["location_id"]
        if lid in likely_closed:
            adjudication = R5_ADJUDICATED_ACTIVE.get(lid)
            if adjudication:
                c["reasoning"] = compose_reasoning([
                    c.get("reasoning"),
                    "[R5 closure-flag adjudicated ACTIVE by PM 2026-07-02: "
                    + adjudication + "]"])
                stats["R5_closure_flag_adjudicated_active"] += 1
            else:
                holds.append({
                    "location_id": lid,
                    "practice_name": c.get("practice_name"),
                    "hold_reason": "R5_operating_status_hold",
                    "detail": ("Row is in the closure queue's "
                               "mark_likely_closed set and has no PM "
                               "adjudication; per ratified R5 the census "
                               "does not classify likely-closed sites."),
                    "original_tier": c.get("assigned_tier"),
                    "source": "closure_candidates_review_20260702 + R5",
                })
                stats["R5_to_hold_operating_status"] += 1
                continue
        kept.append(c)
    classifications = kept

    # ---- integrity: no duplicate location_ids anywhere ---------------------
    ids = [c["location_id"] for c in classifications]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    overlap = set(ids) & {h["location_id"] for h in holds}
    if dupes or overlap:
        print("FATAL: duplicate ids", dupes, "| classified∩holds", overlap)
        sys.exit(1)

    # ---- floor-lift split vs current DB ------------------------------------
    conn = sqlite3.connect(DB)
    ec = dict(conn.execute(
        "SELECT location_id, entity_classification FROM practice_locations "
        "WHERE location_id IN (%s)" % ",".join("?" * len(ids)), ids))
    lift = Counter()
    for c in classifications:
        tier = c["assigned_tier"]
        cur = ec.get(c["location_id"])
        already = cur in ("dso_national", "dso_regional")
        if tier in ("stealth_dso", "branded_dso"):
            lift["T4T5_net_new_floor_lift" if not already
                 else "T4T5_corroborates_already_corporate"] += 1
        elif tier == "dentist_multi":
            lift["T3_consolidated_no_dso_headline"] += 1
        elif tier in ("single_loc_group",):
            lift["T2_consolidated"] += 1
        elif tier == "true_independent":
            lift["T1_independent_coverage"] += 1
        elif tier == "institutional":
            lift["T6_institutional_coverage"] += 1
        else:
            lift[f"other_{tier}"] += 1

    meta = {
        "generated_by": "Fable PM — _normalize_census_candidates_20260702.py",
        "date": "2026-07-02",
        "mode": "FILES-ONLY generator (no DB writes here). Must pass "
                "consolidate_census.py --validate-only with 0 errors. "
                "--allow-db-write AUTHORIZED 2026-07-02 by user delegation "
                "('make the best answers to the decisions ... then proceed') "
                "— decision record: RESEARCH_HOME/DECISIONS_PM_20260702.md.",
        "pm_decisions_20260702": {
            "authority": "user delegated 2026-07-02: 'make the best answers "
                         "to the decisions. you have answering abilities. "
                         "then proceed'",
            "R1": "RATIFIED — ADI in GP denominator, T5 branded_dso; 3 held "
                  "Affordable rows reinstated (pe_backed=true, Harvest "
                  "Partners evidence in-row)",
            "R2": "RATIFIED — ClearChoice rows are scope-correction items, "
                  "never tiered while mis-scoped; 0 found in candidate set",
            "R3": "RATIFIED — T6 institutional = coverage only, never "
                  "consolidated, never DSO/PE",
            "R4": "RATIFIED procedure; named networks decided: NITTINGER "
                  "ACCEPT T5 (11), LABINOV ACCEPT T5 (7), SHAFI ACCEPT T3 "
                  "(18); r4_flag kept on rows for audit",
            "R5": "RATIFIED — closure-flagged rows held unless adjudicated; "
                  "cross-check enforced in this generator; 2 candidates "
                  "adjudicated ACTIVE (Geneva Dental, MetroSmiles Archer "
                  "Heights — closure flags contradicted by direct evidence)",
        },
        "sources": {
            "ready310": os.path.basename(SRC_310),
            "weak68_review": os.path.basename(SRC_WEAK68),
            "wave4_partition1": os.path.basename(SRC_W4P1),
            "lane2_partition": os.path.basename(SRC_LANE2),
            "lane3_51_100": os.path.basename(SRC_LANE3),
        },
        "counts": dict(stats),
        "total_classifications": len(classifications),
        "total_holds": len(holds),
        "floor_lift_split": dict(lift),
        "r4_flagged_rows": sum(1 for c in classifications if c.get("r4_flag")),
        "notes": [
            "R4-flagged rows (NITTINGER/SHAFI/LABINOV) are DECIDED "
            "2026-07-02 under user-delegated PM authority (see "
            "pm_decisions_20260702.R4); the r4_flag stays on each row as an "
            "audit trail of the protected-network review.",
            "Converted partition rows get confidence=medium uniformly "
            "(conservative); upgrade only with per-row PM review.",
            "Coverage != floor lift: see floor_lift_split.",
        ],
    }
    json.dump({"_meta": meta, "classifications": classifications},
              open(OUT_MAIN, "w"), indent=1)
    json.dump({"_meta": meta, "holds": holds}, open(OUT_HOLDS, "w"), indent=1)

    print("classifications:", len(classifications), "| holds:", len(holds))
    print("counts:", json.dumps(dict(stats), indent=1))
    print("floor_lift_split:", json.dumps(dict(lift), indent=1))
    print("r4_flagged:", meta["r4_flagged_rows"])
    print("wrote:", OUT_MAIN)
    print("wrote:", OUT_HOLDS)


if __name__ == "__main__":
    main()
