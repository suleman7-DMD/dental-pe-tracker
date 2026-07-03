"""Merge + PM-gate Lane A wave results into a census candidate file (2026-07-02).

Reads _lane_a_20260702/result_unit_*.json (research agents), all durable
_verdicts*.json files (Opus adversarial verdicts on every stealth/branded DSO
claim), and the complete §6h blocker adjudication rollup. Applies the
fail-closed PM gate, and emits:
  _census_candidate_lane_a_wave1_20260702.json  (classified rows only)
  _lane_a_triage_wave1_20260702.json            (undetermined + rejected, with reasons)

Gate rules (mirrors consolidate_census.py validator + census policy):
  - row must target a live, still-untiered, IL-watched, non-excluded location
  - classified rows: confidence high|medium; URL bases need >=1 real http(s)
    URL (invalid entries stripped; if none survive -> triage)
  - T4/T5 (stealth_dso/branded_dso) rows are written ONLY with a CONFIRM
    verdict from the adversarial verifier. DOWNGRADE_T3 retiers to
    dentist_multi (kept only if web evidence still present). REFUTE /
    INSUFFICIENT / missing verdict -> triage. Fail-closed.
  - Any §6h adjudication hold is excluded; accepted/corrected adjudications are
    applied before writing.
  - pe_backed forced false outside T4/T5.
  - R4 sweep: any network_id reaching >=10 locations across (this wave +
    already-tiered DB rows) is NOT auto-written -> triage as R4 candidate.
  - closure/hold/DA_ leakage rejected (should be pre-filtered upstream).
"""
import glob
import json
import os
import re
import sqlite3
from urllib.parse import urlsplit
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
LANE = os.path.join(HERE, "_lane_a_20260702")
WAVE = "wave1"

VALID_TIERS = {"true_independent", "single_loc_group", "dentist_multi",
               "stealth_dso", "branded_dso", "institutional", "undetermined"}
URL_BASES = {"locator", "web_verified", "intel_dossier"}
ARTIFACT_BASES = {"ein_cluster", "ao_cluster", "name_chain", "structural"}
VALID_BASES = URL_BASES | ARTIFACT_BASES | {"none"}
DSO_TIERS = {"stealth_dso", "branded_dso"}
VERDICT_FILES = [
    "_verdicts_wave1.json",
    "_verdicts_final_flights_20260703.json",
]
ADJUDICATION_ROLLUP = "_adjudication_rollup_complete_20260703.json"


def is_http_url(v):
    if not isinstance(v, str):
        return False
    v = v.strip()
    if not v or re.search(r"\s", v):
        return False
    try:
        parts = urlsplit(v)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and "." in (parts.netloc or "")


def load_verdicts():
    verdicts = {}
    stats = Counter()
    for name in VERDICT_FILES:
        path = os.path.join(LANE, name)
        if not os.path.exists(path):
            print(f"WARNING: no verdict file at {path}")
            stats[f"missing_{name}"] += 1
            continue
        data = json.load(open(path))
        for v in data:
            lid = v.get("location_id")
            if not lid:
                stats["verdict_blank_location_id"] += 1
                continue
            if lid in verdicts and verdicts[lid].get("verdict") != v.get("verdict"):
                raise SystemExit(f"Conflicting verifier verdicts for {lid}: {verdicts[lid]} vs {v}")
            verdicts[lid] = v
            stats[f"verdict_{v.get('verdict')}"] += 1
    return verdicts, stats


def load_adjudications():
    path = os.path.join(LANE, ADJUDICATION_ROLLUP)
    if not os.path.exists(path):
        raise SystemExit(
            f"Missing required §6h adjudication rollup at {path}; refusing to merge Lane A"
        )
    data = json.load(open(path))
    dispositions = data.get("dispositions") or []
    if data.get("summary", {}).get("total_dispositions") != 277 or len(dispositions) != 277:
        raise SystemExit(f"Adjudication rollup is incomplete at {path}")
    out = {}
    for d in dispositions:
        lid = d.get("location_id")
        if not lid:
            raise SystemExit(f"Adjudication disposition without location_id in {path}")
        if lid in out:
            raise SystemExit(f"Duplicate adjudication disposition for {lid} in {path}")
        out[lid] = d
    return out, data.get("summary", {})


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    held_ids = set()
    holds_file = os.path.join(HERE, "_census_holds_20260702.json")
    if os.path.exists(holds_file):
        held_ids = {h["location_id"] for h in json.load(open(holds_file)).get("holds", [])}

    verdicts, verdict_stats = load_verdicts()
    adjudications, adjudication_summary = load_adjudications()

    rows_by_lid = {}
    triage = []
    stats = Counter()

    def reject(row, why):
        stats[f"triage_{why}"] += 1
        triage.append({**row, "_triage_reason": why})

    for path in sorted(glob.glob(os.path.join(LANE, f"result_unit_*.json"))):
        try:
            data = json.load(open(path))
        except Exception as e:
            print(f"UNREADABLE {path}: {e}")
            stats["unreadable_files"] += 1
            continue
        for r in data.get("classifications", []):
            stats["rows_in"] += 1
            lid = r.get("location_id")
            r["_unit"] = data.get("unit_id") or os.path.basename(path)
            if not lid:
                reject(r, "blank_location_id"); continue
            if lid in rows_by_lid:
                reject(r, "duplicate_across_units"); continue
            if lid in held_ids:
                reject(r, "pm_hold_active"); continue

            loc = c.execute("""
                SELECT pl.state, pl.zip, pl.practice_name, pl.primary_npi,
                       pl.org_npi, pl.entity_classification, pl.ownership_tier,
                       wz.state AS wstate
                FROM practice_locations pl
                LEFT JOIN watched_zips wz ON wz.zip_code = substr(pl.zip,1,5)
                WHERE pl.location_id=?""", (lid,)).fetchone()
            if not loc:
                reject(r, "location_not_found"); continue
            if loc["ownership_tier"]:
                reject(r, "already_tiered"); continue
            if loc["wstate"] != "IL" or (loc["state"] or "").upper() != "IL":
                reject(r, "not_il_watched"); continue
            if loc["entity_classification"] in ("specialist", "non_clinical",
                                                "da_unverified", "org_only_npi",
                                                "duplicate_location"):
                reject(r, "excluded_gp_class"); continue
            if str(loc["primary_npi"] or "").startswith(("DA_", "DIR_")) or \
                    str(loc["org_npi"] or "").startswith(("DA_", "DIR_")):
                reject(r, "synthetic_npi"); continue
            if str(r.get("zip") or "")[:5] != (loc["zip"] or "")[:5]:
                reject(r, "zip_echo_mismatch"); continue

            status = r.get("status")
            tier = r.get("assigned_tier")
            if status == "undetermined" or tier == "undetermined":
                stats["undetermined"] += 1
                triage.append({**r, "_triage_reason": "undetermined_by_agent"})
                continue
            if status != "classified":
                reject(r, f"bad_status_{status}"); continue
            if tier not in VALID_TIERS:
                reject(r, "invalid_tier"); continue
            conf = r.get("confidence")

            adjudication = adjudications.get(lid)
            adjudication_note = ""
            if adjudication:
                action = adjudication.get("merge_action")
                disposition = adjudication.get("disposition") or "unknown"
                if action == "hold_do_not_merge":
                    stats["adjudication_hold"] += 1
                    reject({**r, "_adjudication": adjudication}, f"adjudication_{disposition}")
                    continue
                if action == "merge_corrected_tier":
                    corrected = adjudication.get("corrected_tier")
                    if corrected not in VALID_TIERS or corrected == "undetermined":
                        reject({**r, "_adjudication": adjudication}, "adjudication_invalid_corrected_tier")
                        continue
                    tier = corrected
                    conf = adjudication.get("corrected_confidence") or conf or "medium"
                    stats["adjudication_corrected"] += 1
                    adjudication_note = (
                        f" | [§6h adjudication {adjudication.get('adjudication_source')}: "
                        f"corrected to {tier}; {str(adjudication.get('rationale') or '')[:300]}]"
                    )
                elif action == "merge_original":
                    stats["adjudication_accepted"] += 1
                    adjudication_note = (
                        f" | [§6h adjudication {adjudication.get('adjudication_source')}: "
                        f"accepted; {str(adjudication.get('rationale') or '')[:300]}]"
                    )
                else:
                    reject({**r, "_adjudication": adjudication}, f"adjudication_bad_action_{action}")
                    continue

            if conf not in ("high", "medium"):
                reject(r, "low_or_bad_confidence"); continue
            basis = r.get("evidence_basis")
            if basis not in VALID_BASES or basis == "none":
                reject(r, f"bad_basis_{basis}"); continue

            urls = [u for u in (r.get("evidence_urls") or []) if is_http_url(u)]
            dropped = len(r.get("evidence_urls") or []) - len(urls)
            if dropped:
                stats["urls_stripped"] += dropped
            artifacts = [a for a in (r.get("evidence_artifacts") or [])
                         if (isinstance(a, str) and a.strip()) or (isinstance(a, dict) and a)]
            if basis in URL_BASES and not urls:
                reject(r, "url_basis_without_valid_url"); continue
            if basis in ARTIFACT_BASES and not artifacts:
                reject(r, "artifact_basis_without_artifact"); continue

            reasoning = r.get("reasoning") or ""
            if "R4_protected_network" in reasoning:
                reject(r, "r4_flag_in_reasoning"); continue
            if "closure_suspect" in reasoning:
                reject(r, "closure_suspect"); continue

            if tier in DSO_TIERS:
                if not (urls or artifacts):
                    reject(r, "dso_tier_without_evidence"); continue
                v = verdicts.get(lid)
                if not v:
                    reject(r, "dso_claim_unverified"); continue
                if v.get("verdict") == "CONFIRM":
                    reasoning += f" | [Opus adversarial verify CONFIRM: {v.get('notes','')[:300]}]"
                elif v.get("verdict") == "DOWNGRADE_T3":
                    if not urls:
                        reject(r, "downgrade_t3_without_url"); continue
                    tier = "dentist_multi"
                    conf = "medium"
                    reasoning += f" | [Opus adversarial verify DOWNGRADE_T3: {v.get('notes','')[:300]}]"
                else:
                    reject(r, f"dso_claim_{str(v.get('verdict')).lower()}"); continue

            pe = bool(r.get("pe_backed")) if tier in DSO_TIERS else False

            rows_by_lid[lid] = {
                "location_id": lid,
                "assigned_tier": tier,
                "pe_backed": pe,
                "evidence_basis": basis,
                "evidence_urls": urls,
                "evidence_artifacts": artifacts,
                "confidence": conf,
                "status": "classified",
                "network_id": r.get("network_id") or None,
                "reasoning": reasoning,
                "adjudication_note": adjudication_note or None,
                "searched": r.get("searched") or [],
                "source_partition": f"lane_a_{WAVE}_20260702",
                "source_unit": r["_unit"],
            }
            stats["classified_kept"] += 1

    # R4 sweep across the merged wave + already-tiered DB rows
    net_counts = defaultdict(int)
    for row in rows_by_lid.values():
        if row["network_id"]:
            net_counts[row["network_id"]] += 1
    for net, db_n in c.execute("""SELECT network_id, COUNT(*) FROM practice_locations
                                  WHERE network_id IS NOT NULL GROUP BY 1"""):
        if net in net_counts:
            net_counts[net] += db_n
    r4_nets = {n for n, k in net_counts.items() if k >= 10}
    if r4_nets:
        for lid in [l for l, row in rows_by_lid.items() if row["network_id"] in r4_nets]:
            row = rows_by_lid.pop(lid)
            stats["classified_kept"] -= 1
            reject(row, f"r4_network_ge10_{row['network_id']}")
        print("R4 networks routed to triage:", sorted(r4_nets))

    tally = Counter(r["assigned_tier"] for r in rows_by_lid.values())
    out = {
        "_meta": {
            "generated": "2026-07-02",
            "generator": "_merge_lane_a_results_20260702.py",
            "wave": WAVE,
            "policy": "T4/T5 require Opus CONFIRM (fail-closed); pe_backed only on T4/T5; "
                      "R4 networks >=10 routed to triage for one-network-one-decision",
            "verdict_files": VERDICT_FILES,
            "verdict_stats": dict(verdict_stats),
            "adjudication_rollup": ADJUDICATION_ROLLUP,
            "adjudication_summary": adjudication_summary,
            "stats": dict(stats),
            "tier_tally": dict(tally),
        },
        "classifications": list(rows_by_lid.values()),
    }
    cand = os.path.join(HERE, f"_census_candidate_lane_a_{WAVE}_20260702.json")
    json.dump(out, open(cand, "w"), indent=1)
    tri = os.path.join(HERE, f"_lane_a_triage_{WAVE}_20260702.json")
    json.dump(triage, open(tri, "w"), indent=1)
    print(f"classified kept: {len(rows_by_lid)}  triage: {len(triage)}")
    print("tier tally:", dict(tally))
    print("stats:", dict(stats))
    print("candidate:", cand)
    print("triage:", tri)


if __name__ == "__main__":
    main()
