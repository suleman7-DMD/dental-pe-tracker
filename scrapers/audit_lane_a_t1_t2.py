#!/usr/bin/env python3
"""Lane A T1/T2 positive-proof audit.

Files-only gate before any Lane A DB write. It enforces the 2026-07-03 rule:
T1 is a positive, current, corroborated owner-operator claim, not merely the
absence of DSO evidence.
"""

from __future__ import annotations

import collections
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


BASE = Path("data/dso_research")
LANE = BASE / "_lane_a_20260702"
CANDIDATE = BASE / "_census_candidate_lane_a_wave1_20260702.json"
TRIAGE = BASE / "_lane_a_triage_wave1_20260702.json"
SCREEN = LANE / "hidden_control_screen_20260703.json"
AUDIT_OUT = LANE / "audit_t1_t2_positive_proof_20260704.json"
REMEDIATED_CANDIDATE = BASE / "_census_candidate_lane_a_wave1_20260702.json"
REMEDIATED_TRIAGE = BASE / "_lane_a_triage_wave1_20260702.json"

SEED = 20260704

T1 = "true_independent"
T2 = "single_loc_group"
T1_T2 = {T1, T2}

DIRECTORY_DOMAINS = {
    "ada.org",
    "bbb.org",
    "birdeye.com",
    "carecredit.com",
    "chamberofcommerce.com",
    "dentalplans.com",
    "dentistdig.com",
    "doctor.com",
    "doctorsnetwork.com",
    "doximity.com",
    "findadentist.ada.org",
    "healthgrades.com",
    "insuranceaccepted.com",
    "mapquest.com",
    "npidb.org",
    "npino.com",
    "npiprofile.com",
    "opencare.com",
    "ratemds.com",
    "sharecare.com",
    "usnews.com",
    "webmd.com",
    "wellness.com",
    "yelp.com",
    "zocdoc.com",
}

CONTROL_CODES = {"db_corporate_conflict", "parent_or_legal_entity_signal"}
T1_HARD_ROSTER_CODES = {
    "t1_provider_count_gt1",
    "t1_group_entity_classification",
    "t1_multiple_provider_surnames",
}
NETWORK_CODES = {
    "shared_phone_multiple_locations",
    "shared_website_domain",
    "shared_ein_or_parent_tin",
    "ao_reaches_multiple_locations",
    "shared_data_axle_officer",
    "shared_backoffice_mailing",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def is_directory_domain(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in DIRECTORY_DOMAINS)


def url_profile(urls: list[Any]) -> dict[str, Any]:
    hosts = [domain(u) for u in urls if isinstance(u, str) and u.startswith(("http://", "https://"))]
    directory_hosts = [h for h in hosts if is_directory_domain(h)]
    direct_hosts = [h for h in hosts if not is_directory_domain(h)]
    return {
        "hosts": hosts,
        "directory_hosts": directory_hosts,
        "direct_hosts": direct_hosts,
        "directory_only": bool(hosts) and not direct_hosts,
        "has_direct_source": bool(direct_hosts),
    }


def signal_codes(screen_row: dict[str, Any] | None) -> set[str]:
    if not screen_row:
        return set()
    return {s.get("code") for s in screen_row.get("signals", []) if s.get("code")}


def risk_score(row: dict[str, Any], screen_row: dict[str, Any] | None, profile: dict[str, Any]) -> int:
    codes = signal_codes(screen_row)
    score = 0
    if row.get("assigned_tier") == T1:
        score += 10
    if row.get("confidence") == "high":
        score += 3
    if profile["directory_only"] or "directory_only_support" in codes:
        score += 10
    if codes & CONTROL_CODES:
        score += 25
    if row.get("assigned_tier") == T1 and codes & T1_HARD_ROSTER_CODES:
        score += 20
    score += min(12, 4 * len(codes & NETWORK_CODES))
    priority = (screen_row or {}).get("priority")
    if priority == "block_before_merge":
        score += 8
    elif priority == "review_high":
        score += 5
    elif priority == "review_medium":
        score += 2
    return score


def finding_for(row: dict[str, Any], screen_row: dict[str, Any] | None) -> dict[str, Any]:
    codes = signal_codes(screen_row)
    profile = url_profile(row.get("evidence_urls") or [])
    tier = row.get("assigned_tier")
    findings: list[str] = []
    action = "pass"
    reason = "No hard T1/T2 audit issue found."

    if tier in T1_T2 and codes & CONTROL_CODES:
        action = "hold"
        reason = "Control/corporate signal remains on a T1/T2 candidate; fail closed to review."
        findings.append("control_signal")
    elif tier == T1 and codes & T1_HARD_ROSTER_CODES:
        action = "hold"
        reason = "T1 still conflicts with provider roster/group classification; cannot write as solo owner-operated."
        findings.append("t1_roster_conflict")
    elif tier == T1 and row.get("confidence") == "high" and (profile["directory_only"] or "directory_only_support" in codes):
        action = "downgrade_confidence"
        reason = "High-confidence T1 relies on directory-style support; lower to medium under positive-proof rule."
        findings.append("high_conf_t1_directory_only")
    elif tier == T2 and row.get("confidence") == "high" and (profile["directory_only"] or "directory_only_support" in codes):
        action = "downgrade_confidence"
        reason = "High-confidence T2 relies on directory-style support; lower to medium under source-quality rule."
        findings.append("high_conf_t2_directory_only")

    if tier == T1 and len(codes & NETWORK_CODES) >= 2:
        findings.append("t1_multiple_network_signals")
    if profile["directory_only"]:
        findings.append("directory_only_urls")
    if "stale_founder_history" in codes:
        findings.append("stale_founder_history")

    return {
        "location_id": row.get("location_id"),
        "practice_name": row.get("practice_name"),
        "assigned_tier": tier,
        "confidence": row.get("confidence"),
        "screen_priority": (screen_row or {}).get("priority", "clean_or_unscreened"),
        "signal_codes": sorted(codes),
        "url_profile": profile,
        "risk_score": risk_score(row, screen_row, profile),
        "audit_action": action,
        "audit_reason": reason,
        "findings": findings,
    }


def sample_rows(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    by_id = {f["location_id"]: f for f in findings}
    selected: dict[str, dict[str, Any]] = {}

    def add(label: str, candidates: list[dict[str, Any]], n: int, by_risk: bool = True) -> None:
        if by_risk:
            pool = sorted(candidates, key=lambda f: (-f["risk_score"], f["location_id"]))
        else:
            pool = candidates[:]
            rng.shuffle(pool)
        for f in pool:
            if len([x for x in selected.values() if label in x["sample_strata"]]) >= n:
                break
            item = selected.setdefault(f["location_id"], {**f, "sample_strata": []})
            if label not in item["sample_strata"]:
                item["sample_strata"].append(label)

    t1 = [f for f in findings if f["assigned_tier"] == T1]
    t2 = [f for f in findings if f["assigned_tier"] == T2]
    add("must_fix_hold", [f for f in findings if f["audit_action"] == "hold"], 25)
    add("confidence_downgrade", [f for f in findings if f["audit_action"] == "downgrade_confidence"], 25)
    add("review_high", [f for f in findings if f["screen_priority"] == "review_high"], 20)
    add(
        "directory_only_review_medium",
        [f for f in findings if f["screen_priority"] == "review_medium" and "directory_only_urls" in f["findings"]],
        20,
    )
    add("clean_control", [f for f in findings if f["screen_priority"] == "clean_or_unscreened"], 10, by_risk=False)
    add("random_t1", t1, 10, by_risk=False)
    add("random_t2", t2, 10, by_risk=False)
    return sorted(selected.values(), key=lambda f: (-f["risk_score"], f["location_id"]))


def main() -> None:
    candidate_doc = json.loads(CANDIDATE.read_text())
    triage_rows = json.loads(TRIAGE.read_text())
    screen_rows = json.loads(SCREEN.read_text()).get("suspects", [])
    screen_by_id = {r["location_id"]: r for r in screen_rows}
    rows = candidate_doc.get("classifications", [])

    findings = [
        finding_for(row, screen_by_id.get(row["location_id"]))
        for row in rows
        if row.get("assigned_tier") in T1_T2
    ]

    hold_ids = {f["location_id"] for f in findings if f["audit_action"] == "hold"}
    downgrade_ids = {f["location_id"] for f in findings if f["audit_action"] == "downgrade_confidence"}
    finding_by_id = {f["location_id"]: f for f in findings}

    remediated_rows = []
    added_triage = []
    for row in rows:
        lid = row.get("location_id")
        if lid in hold_ids:
            added_triage.append({
                **row,
                "_triage_reason": "t1_t2_positive_proof_audit_hold",
                "_audit": finding_by_id[lid],
            })
            continue
        if lid in downgrade_ids:
            row = {
                **row,
                "confidence": "medium",
                "reasoning": (row.get("reasoning") or "")
                + " | [T1/T2 positive-proof audit: confidence lowered from high because support is directory-style / not enough for high-confidence ownership proof.]",
            }
        remediated_rows.append(row)

    candidate_doc["classifications"] = remediated_rows
    candidate_doc.setdefault("_meta", {})["t1_t2_positive_proof_audit"] = {
        "generated_at": now_iso(),
        "script": "scrapers/audit_lane_a_t1_t2.py",
        "input_rows_t1_t2": len(findings),
        "held_rows": len(hold_ids),
        "confidence_downgraded_rows": len(downgrade_ids),
        "policy": "Hold T1/T2 control signals and T1 roster conflicts; downgrade directory-only high-confidence T1/T2 to medium.",
    }
    candidate_doc["_meta"]["tier_tally"] = dict(collections.Counter(r["assigned_tier"] for r in remediated_rows))

    triage_rows = triage_rows + added_triage

    CANDIDATE.write_text(json.dumps(candidate_doc, indent=1) + "\n")
    TRIAGE.write_text(json.dumps(triage_rows, indent=1) + "\n")

    summary = {
        "generated_at": now_iso(),
        "seed": SEED,
        "candidate_rows_before": len(rows),
        "candidate_rows_after": len(remediated_rows),
        "t1_t2_rows_scanned": len(findings),
        "finding_counts": dict(collections.Counter(f["audit_action"] for f in findings)),
        "held_rows": len(hold_ids),
        "confidence_downgraded_rows": len(downgrade_ids),
        "tier_tally_after": dict(collections.Counter(r["assigned_tier"] for r in remediated_rows)),
        "triage_rows_after": len(triage_rows),
    }
    AUDIT_OUT.write_text(json.dumps({
        "_meta": summary,
        "sample": sample_rows(findings),
        "findings": findings,
    }, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("audit_artifact", AUDIT_OUT)


if __name__ == "__main__":
    main()
