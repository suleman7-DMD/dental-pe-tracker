#!/usr/bin/env python3
"""Codex fail-closed adjudication for Lane A rows missing Opus batch output.

This does not replace the Opus adjudicator. It labels the 147 rows that had no
landed adjudication file after the Fable session limit, using only the persisted
screen bundle, Lane A evidence, and deterministic §6h rules. It is deliberately
conservative: contradictory corporate/control signals stay held.
"""

from __future__ import annotations

import collections
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE = Path("data/dso_research/_lane_a_20260702")
MISSING = BASE / "_adjudication_missing_20260703.json"
ROLLUP_RECOVERY = BASE / "_adjudication_rollup_20260703.json"
CODEX_OUT = BASE / "adjudication_codex_missing_20260703.json"
ROLLUP_COMPLETE = BASE / "_adjudication_rollup_complete_20260703.json"

CORPORATE_CODES = {"db_corporate_conflict", "parent_or_legal_entity_signal"}
NETWORK_CODES = {
    "shared_phone_multiple_locations",
    "shared_website_domain",
    "shared_ein_or_parent_tin",
    "ao_reaches_multiple_locations",
    "shared_data_axle_officer",
    "shared_backoffice_mailing",
}
AO_CONTROL_CODES = {"ao_nonclinical_exec_title", "ao_not_provider_or_practice_name"}
T1_ROSTER_CODES = {
    "t1_provider_count_gt1",
    "t1_group_entity_classification",
    "t1_multiple_provider_surnames",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def codes(bundle: dict[str, Any]) -> set[str]:
    return {signal.get("code") for signal in bundle.get("signals", []) if signal.get("code")}


def evidence_values(bundle: dict[str, Any], code: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for signal in bundle.get("signals", []):
      if signal.get("code") == code and isinstance(signal.get("evidence"), dict):
        values.append(signal["evidence"])
    return values


def count_network_codes(cs: set[str]) -> int:
    return sum(1 for code in NETWORK_CODES if code in cs)


def text(bundle: dict[str, Any]) -> str:
    return " ".join(
        str(bundle.get(key) or "")
        for key in ("lane_a_reasoning", "lane_a_evidence_basis", "practice_name")
    ).lower()


def reasoning_has_any(bundle: dict[str, Any], terms: tuple[str, ...]) -> bool:
    t = text(bundle)
    return any(term in t for term in terms)


def is_evenly_placeholder_false_alarm(bundle: dict[str, Any]) -> bool:
    t = text(bundle)
    if "evenly" not in t:
        return False
    return "placeholder" in t or "false-signal" in t or "false signal" in t


def has_own_source(bundle: dict[str, Any]) -> bool:
    t = text(bundle)
    if any(term in t for term in ("own website", "own site", "practice's own", "official site")):
        return True
    urls = bundle.get("lane_a_evidence_urls") or []
    directory_domains = (
        "healthgrades", "yelp", "zocdoc", "dentalplans", "opencare", "webmd", "bbb.org",
        "dnb.com", "findadentist", "ada.org",
    )
    for url in urls:
        u = str(url).lower()
        if u.startswith("http") and not any(domain in u for domain in directory_domains):
            return True
    return False


def has_single_location_claim(bundle: dict[str, Any]) -> bool:
    return reasoning_has_any(
        bundle,
        (
            "single location",
            "single-location",
            "single office",
            "single-office",
            "one location",
            "one office",
            "at this single",
            "no additional locations",
            "no second location",
        ),
    )


def has_multi_location_claim(bundle: dict[str, Any]) -> bool:
    return reasoning_has_any(
        bundle,
        (
            "two locations",
            "2 locations",
            "multiple locations",
            "multi-location",
            "multi location",
            "locations in",
            "offices in",
            "3 locations",
            "three locations",
            "network",
        ),
    )


def has_owner_claim(bundle: dict[str, Any]) -> bool:
    return reasoning_has_any(
        bundle,
        (
            "owner",
            "owned",
            "founder",
            "president",
            "partner",
            "dentist-owned",
            "dentist owned",
            "non-corporate",
            "family-owned",
        ),
    )


def corporate_hold(bundle: dict[str, Any], cs: set[str]) -> bool:
    if "db_corporate_conflict" in cs:
        return True
    if "parent_or_legal_entity_signal" in cs and not is_evenly_placeholder_false_alarm(bundle):
        return True
    return False


def adjudicate(bundle: dict[str, Any]) -> dict[str, Any]:
    cs = codes(bundle)
    db = bundle.get("db_context") or {}
    assigned = bundle.get("assigned_tier")
    provider_count = db.get("provider_count")
    entity = db.get("entity_classification")
    network_count = count_network_codes(cs)
    own_source = has_own_source(bundle)
    single_claim = has_single_location_claim(bundle)
    multi_claim = has_multi_location_claim(bundle)
    owner_claim = has_owner_claim(bundle)
    directory_only = "directory_only_support" in cs
    nonclinical_ao = "ao_nonclinical_exec_title" in cs

    base = {
        "location_id": bundle.get("location_id"),
        "practice_name": bundle.get("practice_name"),
        "zip": bundle.get("zip"),
        "assigned_tier": assigned,
        "corrected_tier": None,
        "corrected_confidence": None,
        "web_searched": False,
        "adjudication_source": "codex_missing_adjudication",
        "screen_signal_codes": sorted(cs),
        "rule_basis": "§6h positive-proof gate; deterministic recovery from persisted blocker bundle",
    }

    if corporate_hold(bundle, cs):
        base.update(
            disposition="hold_dso_verify",
            merge_action="hold_do_not_merge",
            rationale=(
                "Held: persisted bundle has a contradictory corporate/control signal "
                f"({', '.join(sorted(cs & CORPORATE_CODES))}). Codex did not re-web-verify this row, "
                "so the old detector/source conflict cannot be overturned safely in the merge."
            ),
        )
        return base

    if nonclinical_ao and not multi_claim:
        base.update(
            disposition="hold_control_review",
            merge_action="hold_do_not_merge",
            rationale=(
                "Held: authorized official has a non-clinical/executive title and the Lane A evidence "
                "does not cleanly prove a dentist-owned multi-location structure. This is a hidden-control "
                "risk, not a safe T1/T2 accept."
            ),
        )
        return base

    if assigned == "true_independent":
        if cs & T1_ROSTER_CODES:
            if isinstance(provider_count, int) and 1 < provider_count <= 7 and entity in {"small_group", "family_practice"}:
                base.update(
                    disposition="correct",
                    corrected_tier="single_loc_group",
                    corrected_confidence="medium",
                    merge_action="merge_corrected_tier",
                    rationale=(
                        "Corrected T1 -> T2: DB roster/entity signals show multiple providers at the location. "
                        "That defeats solo owner-operated status, but provider count is small and no hard "
                        "corporate-control signal remains after screening."
                    ),
                )
                return base
            base.update(
                disposition="hold_unresolved",
                merge_action="hold_do_not_merge",
                rationale=(
                    "Held: T1 conflicts with roster/group signals that are too large or too contradictory "
                    "to correct mechanically. This cannot merge as true solo owner-operated without row-level review."
                ),
            )
            return base

        if directory_only:
            base.update(
                disposition="hold_unresolved",
                merge_action="hold_do_not_merge",
                rationale="Held: T1 is supported by directory-style evidence only, which fails the positive-proof standard for true solo ownership.",
            )
            return base

        if network_count >= 2 and not (own_source and owner_claim and single_claim):
            base.update(
                disposition="hold_network_review",
                merge_action="hold_do_not_merge",
                rationale=(
                    "Held: T1 has multiple independent network/control signals and the persisted reasoning "
                    "does not fully rebut them with current owner + single-location proof."
                ),
            )
            return base

        if own_source and owner_claim and single_claim and network_count <= 2:
            base.update(
                disposition="accept",
                merge_action="merge_original",
                rationale=(
                    "Accepted T1 with caution: persisted evidence includes own/current source language, owner/operator proof, "
                    "and a single-location rebuttal; remaining screen signals are weak/structural and should be persisted."
                ),
            )
            return base

        base.update(
            disposition="hold_unresolved",
            merge_action="hold_do_not_merge",
            rationale="Held: T1 lacks enough current owner-operator and single-location proof to satisfy §6h after screening.",
        )
        return base

    if assigned == "single_loc_group":
        if multi_claim and not nonclinical_ao:
            base.update(
                disposition="correct",
                corrected_tier="dentist_multi",
                corrected_confidence="medium",
                merge_action="merge_corrected_tier",
                rationale=(
                    "Corrected T2 -> T3: Lane A reasoning itself describes a dentist-owned multi-location/network structure. "
                    "No hard corporate-control signal remains after screening."
                ),
            )
            return base

        if network_count >= 2 and not (own_source and single_claim):
            base.update(
                disposition="hold_network_review",
                merge_action="hold_do_not_merge",
                rationale=(
                    "Held: T2 has multiple network signals and lacks a clean own-source single-location rebuttal. "
                    "It may be T3 or controlled; do not merge as T2 mechanically."
                ),
            )
            return base

        if directory_only and not own_source:
            base.update(
                disposition="hold_unresolved",
                merge_action="hold_do_not_merge",
                rationale="Held: T2 relies on directory-style support without enough current practice-owned evidence.",
            )
            return base

        base.update(
            disposition="accept",
            merge_action="merge_original",
            rationale=(
                "Accepted T2: row is already outside the true-solo bucket; persisted reasoning/URLs support a dentist-owned "
                "single-location group, and remaining signals do not justify DSO/T3 promotion without new web review."
            ),
        )
        return base

    if assigned == "dentist_multi":
        if nonclinical_ao and not own_source:
            base.update(
                disposition="hold_control_review",
                merge_action="hold_do_not_merge",
                rationale="Held: T3 has non-clinical AO/control signal and lacks enough own-source proof to merge safely.",
            )
            return base
        base.update(
            disposition="accept",
            merge_action="merge_original",
            rationale=(
                "Accepted T3: assigned tier already represents not-solo, multi-location dentist-owned status. "
                "No unresolved corporate-conflict signal remains after screening."
            ),
        )
        return base

    base.update(
        disposition="hold_unresolved",
        merge_action="hold_do_not_merge",
        rationale="Held: unhandled tier/signal pattern in Codex missing adjudication; fail closed.",
    )
    return base


def main() -> None:
    missing_doc = json.loads(MISSING.read_text())
    missing = missing_doc["bundles"]
    codex_dispositions = [adjudicate(bundle) for bundle in missing]

    CODEX_OUT.write_text(
        json.dumps(
            {
                "_meta": {
                    "generated_at": now_iso(),
                    "input_file": str(MISSING),
                    "count": len(codex_dispositions),
                    "policy": "Conservative Codex recovery adjudication. Not Opus; all provenance is labeled codex_missing_adjudication.",
                    "no_db_writes": True,
                },
                "dispositions": codex_dispositions,
                "summary": summarize(codex_dispositions),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    recovery = json.loads(ROLLUP_RECOVERY.read_text())
    real = [
        row
        for row in recovery.get("dispositions", [])
        if row.get("adjudication_source") == "opus_batch"
    ]
    combined = real + codex_dispositions
    ROLLUP_COMPLETE.write_text(
        json.dumps(
            {
                "_meta": {
                    "generated_at": now_iso(),
                    "base_recovery_rollup": str(ROLLUP_RECOVERY),
                    "codex_missing_file": str(CODEX_OUT),
                    "policy": "Complete representation of all 277 blockers: 130 Opus batch dispositions plus 147 conservative Codex missing-row dispositions.",
                    "no_db_writes": True,
                },
                "dispositions": combined,
                "summary": summarize(combined),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    print("wrote", CODEX_OUT, len(codex_dispositions))
    print("wrote", ROLLUP_COMPLETE, len(combined))
    print(json.dumps(summarize(combined), indent=2, sort_keys=True))


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_dispositions": len(rows),
        "unique_location_ids": len({row.get("location_id") for row in rows}),
        "source_counts": dict(collections.Counter(row.get("adjudication_source") for row in rows)),
        "assigned_tier_counts": dict(collections.Counter(row.get("assigned_tier") for row in rows)),
        "corrected_tier_counts": dict(collections.Counter(str(row.get("corrected_tier")) for row in rows)),
        "disposition_counts": dict(collections.Counter(row.get("disposition") for row in rows)),
        "merge_action_counts": dict(collections.Counter(row.get("merge_action") for row in rows)),
    }


if __name__ == "__main__":
    main()
