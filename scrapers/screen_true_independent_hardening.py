"""Screen Lane A census rows for false true-independent / hidden-control risk.

Read-only. This script joins Lane A result-unit JSON rows back to SQLite
`practice_locations` and every bridged NPI in `practices`, then emits a review
queue of T1/T2/T3 rows whose evidence or structural signals are not strong
enough for a clean "true solo owner-operated" / "dentist-owned" merge.

It does not re-tier rows and does not write to SQLite or Supabase.

Usage:
    python3 scrapers/screen_true_independent_hardening.py
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sqlite3
import urllib.parse
from typing import Any

try:
    from scrapers.detect_corporate_clusters import (
        _clean_ein,
        _parse_officers,
        is_exec_title,
        norm_addr,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from detect_corporate_clusters import (  # type: ignore
        _clean_ein,
        _parse_officers,
        is_exec_title,
        norm_addr,
    )


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
DEFAULT_RESULTS_DIR = os.path.join(ROOT, "data", "dso_research", "_lane_a_20260702")
DEFAULT_OUTPUT = os.path.join(
    DEFAULT_RESULTS_DIR, "hidden_control_screen_20260703.json"
)

TARGET_TIERS = {"true_independent", "single_loc_group", "dentist_multi"}
CORPORATE_ENTITY_CLASSES = {"dso_regional", "dso_national"}
GROUP_ENTITY_CLASSES = {"family_practice", "small_group", "large_group"}

DIRECTORY_DOMAINS = {
    "aedit.com",
    "ada.org",
    "bbb.org",
    "birdeye.com",
    "caredash.com",
    "chamberofcommerce.com",
    "dentalinsider.com",
    "dentalplans.com",
    "dentistreg.com",
    "dentistry.com",
    "doctor.com",
    "doctor.webmd.com",
    "ehealthscores.com",
    "facebook.com",
    "findadentist.ada.org",
    "findatopdoc.com",
    "groupon.com",
    "healthgrades.com",
    "hipaaspace.com",
    "linkedin.com",
    "local.yahoo.com",
    "mapquest.com",
    "medicarelist.com",
    "manta.com",
    "npidashboard.com",
    "npidb.org",
    "npino.com",
    "npiprofile.com",
    "npiregistry.cms.hhs.gov",
    "opencare.com",
    "opennpi.com",
    "providerwire.com",
    "providers.sharecare.com",
    "sharecare.com",
    "superpages.com",
    "vitals.com",
    "vitadox.com",
    "webmd.com",
    "wellness.com",
    "yellowpages.com",
    "yelp.com",
    "zocdoc.com",
}

EXEC_TITLE_KEYWORDS = (
    "CEO",
    "CFO",
    "COO",
    "CHIEF",
    "DIRECTOR",
    "MANAGER",
    "ADMINISTRATOR",
    "CONTROLLER",
    "VICE PRESIDENT",
    "VP",
    "REGIONAL",
    "TREASURER",
    "GENERAL COUNSEL",
)

STALE_TEXT_RE = re.compile(
    r"\b(served|serving|founded|established|since|practicing since)\s+"
    r"(19[0-9]{2}|200[0-9]|201[0-6])\b",
    re.I,
)
CURRENT_OWNER_RE = re.compile(r"\b(owner|owned|owns|founder|principal|president)\b", re.I)
SINGLE_LOC_RE = re.compile(r"\b(single location|one location|solo|owner-operator)\b", re.I)
NO_CORP_RE = re.compile(
    r"\b(no corporate|no dso|no ms[o0]|no parent|no pe|no chain|no network)\b",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--tiers",
        default="true_independent,single_loc_group,dentist_multi",
        help="Comma-separated assigned_tier values to screen.",
    )
    return parser.parse_args()


def parse_json_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if not isinstance(value, str):
        return []
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return []
    if isinstance(loaded, list):
        return [str(v) for v in loaded if v]
    return []


def clean_npi(value: Any) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\D", "", str(value))
    if not s or s.startswith("DA") or s.startswith("DIR"):
        return None
    return s if len(s) == 10 else None


def location_npis(loc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("primary_npi", "org_npi"):
        npi = clean_npi(loc.get(key))
        if npi and npi not in out:
            out.append(npi)
    for raw in parse_json_list(loc.get("provider_npis")):
        npi = clean_npi(raw)
        if npi and npi not in out:
            out.append(npi)
    return out


def chunked(values: list[str], size: int = 800) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def evidence_urls(row: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("evidence_urls", "sources"):
        value = row.get(key)
        if isinstance(value, list):
            urls.extend(str(v) for v in value if isinstance(v, str) and v)
        elif isinstance(value, str) and value:
            urls.append(value)
    artifacts = row.get("evidence_artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict):
                for key in ("url", "source_url"):
                    value = artifact.get(key)
                    if isinstance(value, str) and value:
                        urls.append(value)
    return list(dict.fromkeys(urls))


def domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return None
    host = (parsed.netloc or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def is_directory_domain(host: str | None) -> bool:
    if not host:
        return False
    return host in DIRECTORY_DOMAINS or any(
        host.endswith(f".{base}") for base in DIRECTORY_DOMAINS
    )


def phone_key(value: Any) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def person_key(first: Any, last: Any) -> str | None:
    ln = re.sub(r"[^A-Z]", "", str(last or "").upper())
    fn = re.sub(r"[^A-Z]", "", str(first or "").upper())
    if len(ln) < 2:
        return None
    return f"{ln},{fn}" if fn else ln


def name_tokens(value: Any) -> set[str]:
    text = re.sub(r"[^A-Z ]", " ", str(value or "").upper())
    stop = {
        "DDS",
        "DMD",
        "PC",
        "P",
        "C",
        "LLC",
        "LTD",
        "DENTAL",
        "DENTIST",
        "DENTISTRY",
        "FAMILY",
        "CARE",
        "ASSOCIATES",
        "ASSOC",
        "CLINIC",
        "CENTER",
        "GROUP",
        "THE",
        "AND",
        "OF",
    }
    return {t for t in text.split() if len(t) >= 3 and t not in stop}


def signal(
    code: str,
    severity: str,
    score: int,
    explanation: str,
    evidence: dict[str, Any] | None = None,
    category: str = "weak",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "score": score,
        "category": category,
        "explanation": explanation,
        "evidence": evidence or {},
    }


def load_result_rows(results_dir: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(glob.glob(os.path.join(results_dir, "result_unit_*.json"))):
        with open(path) as f:
            data = json.load(f)
        unit_id = data.get("unit_id") or os.path.basename(path).removeprefix(
            "result_"
        ).removesuffix(".json")
        for row in data.get("classifications") or data.get("practices") or []:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item["_unit_id"] = unit_id
            item["_file"] = os.path.basename(path)
            rows.append(item)
    return rows


def load_locations(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT location_id, normalized_address, zip, city, state, practice_name,
               doing_business_as, primary_npi, org_npi, provider_npis,
               provider_count, has_org_npi, entity_classification,
               ownership_status, affiliated_dso, affiliated_pe_sponsor,
               parent_company, ein, website, phone, ownership_tier, network_id
        FROM practice_locations
        """
    ).fetchall()
    return {r["location_id"]: dict(r) for r in rows}


def load_practices(
    conn: sqlite3.Connection, npis: list[str]
) -> dict[str, dict[str, Any]]:
    if not npis:
        return {}
    cols = """
        npi, practice_name, doing_business_as, entity_type, address, city, state,
        zip, phone, entity_classification, affiliated_dso, affiliated_pe_sponsor,
        parent_company, parent_iusa, ein, website, provider_last_name,
        authorized_official_last_name, authorized_official_first_name,
        authorized_official_title, authorized_official_credential,
        mailing_address, mailing_city, mailing_state, mailing_zip,
        parent_org_lbn, parent_org_tin, da_ein2, da_ein3,
        da_mailing_address, da_mailing_city, da_mailing_state, da_mailing_zip,
        da_legal_name, da_subsidiary_iusa, da_corporate_employees,
        da_corporate_sales, da_officers, ownership_tier, pe_backed, network_id
    """
    out: dict[str, dict[str, Any]] = {}
    for chunk in chunked(npis):
        placeholders = ",".join("?" for _ in chunk)
        for row in conn.execute(
            f"SELECT {cols} FROM practices WHERE npi IN ({placeholders})", chunk
        ):
            out[row["npi"]] = dict(row)
    return out


def build_contexts(
    locations: dict[str, dict[str, Any]], practices: dict[str, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, set[str]]]]:
    contexts: dict[str, dict[str, Any]] = {}
    clusters: dict[str, dict[str, set[str]]] = {
        "ao": collections.defaultdict(set),
        "ein": collections.defaultdict(set),
        "mail": collections.defaultdict(set),
        "phone": collections.defaultdict(set),
        "domain": collections.defaultdict(set),
        "da_officer": collections.defaultdict(set),
    }

    for location_id, loc in locations.items():
        npi_list = location_npis(loc)
        npi_rows = [practices[n] for n in npi_list if n in practices]
        org_rows = [
            r
            for r in npi_rows
            if (r.get("entity_type") or "").lower() == "organization"
            or r.get("npi") == clean_npi(loc.get("org_npi"))
        ]
        provider_rows = [
            r for r in npi_rows if (r.get("entity_type") or "").lower() == "individual"
        ]
        provider_surnames = {
            re.sub(r"[^A-Z]", "", str(r.get("provider_last_name") or "").upper())
            for r in provider_rows
            if r.get("provider_last_name")
        }
        provider_surnames = {s for s in provider_surnames if len(s) >= 2}

        ao_keys: set[str] = set()
        ao_records = []
        for r in org_rows:
            key = person_key(
                r.get("authorized_official_first_name"),
                r.get("authorized_official_last_name"),
            )
            if key:
                ao_keys.add(key)
                clusters["ao"][key].add(location_id)
                ao_records.append(
                    {
                        "key": key,
                        "first": r.get("authorized_official_first_name"),
                        "last": r.get("authorized_official_last_name"),
                        "title": r.get("authorized_official_title"),
                        "credential": r.get("authorized_official_credential"),
                        "npi": r.get("npi"),
                    }
                )

        eins: set[str] = set()
        for value in [loc.get("ein")] + [
            r.get(k)
            for r in npi_rows
            for k in ("ein", "parent_org_tin", "da_ein2", "da_ein3")
        ]:
            ein = _clean_ein(value)
            if ein:
                eins.add(ein)
        for ein in eins:
            clusters["ein"][ein].add(location_id)

        mail_keys: set[str] = set()
        for r in org_rows:
            m_addr = norm_addr(r.get("mailing_address"))
            p_addr = norm_addr(loc.get("normalized_address"))
            if m_addr and m_addr != p_addr:
                key = f"{m_addr}|{str(r.get('mailing_zip') or '')[:5]}"
                mail_keys.add(key)
                clusters["mail"][key].add(location_id)
            da_addr = norm_addr(r.get("da_mailing_address"))
            if da_addr and da_addr != p_addr:
                key = f"{da_addr}|{str(r.get('da_mailing_zip') or '')[:5]}"
                mail_keys.add(key)
                clusters["mail"][key].add(location_id)

        phones = {phone_key(loc.get("phone"))}
        phones.update(phone_key(r.get("phone")) for r in npi_rows)
        phones = {p for p in phones if p}
        for key in phones:
            clusters["phone"][key].add(location_id)

        domains = {domain(loc.get("website"))}
        domains.update(domain(r.get("website")) for r in npi_rows)
        domains = {d for d in domains if d and not is_directory_domain(d)}
        for key in domains:
            clusters["domain"][key].add(location_id)

        da_officers = set()
        for r in npi_rows:
            for last, first in _parse_officers(r):
                key = f"{last},{first}"
                da_officers.add(key)
                clusters["da_officer"][key].add(location_id)

        contexts[location_id] = {
            "loc": loc,
            "npis": npi_list,
            "npi_rows": npi_rows,
            "org_rows": org_rows,
            "provider_rows": provider_rows,
            "provider_surnames": provider_surnames,
            "ao_records": ao_records,
            "ao_keys": ao_keys,
            "eins": eins,
            "mail_keys": mail_keys,
            "phones": phones,
            "domains": domains,
            "da_officers": da_officers,
        }
    return contexts, clusters


def cluster_ids(
    clusters: dict[str, dict[str, set[str]]], kind: str, key: str
) -> list[str]:
    return sorted(clusters[kind].get(key, set()))


def has_corp_text(value: Any) -> bool:
    if not value:
        return False
    text = str(value).upper()
    if text in {"NONE", "NAN", "NULL", "0", "000000000"}:
        return False
    return bool(text.strip())


def assess_row(
    row: dict[str, Any],
    ctx: dict[str, Any] | None,
    clusters: dict[str, dict[str, set[str]]],
) -> dict[str, Any]:
    assigned_tier = row.get("assigned_tier")
    signals: list[dict[str, Any]] = []
    urls = evidence_urls(row)
    domains = [domain(u) for u in urls if domain(u)]
    directory_only = bool(domains) and all(is_directory_domain(d) for d in domains)

    if not urls:
        signals.append(
            signal(
                "evidence_no_url",
                "high",
                4,
                "Classified row has no evidence URL in the result file.",
                category="evidence",
            )
        )
    elif directory_only and assigned_tier in {"true_independent", "single_loc_group"}:
        signals.append(
            signal(
                "directory_only_support",
                "medium",
                2,
                "T1/T2 ownership is supported only by directory/social/registry-style URLs; needs current owner corroboration.",
                {"domains": sorted(set(domains))},
                category="evidence",
            )
        )

    confidence = row.get("confidence")
    if confidence == "low":
        signals.append(
            signal(
                "low_confidence_classified",
                "medium",
                2,
                "Classified row is low confidence and should not merge as final ownership.",
                category="evidence",
            )
        )

    text = " ".join(
        str(row.get(k) or "") for k in ("reasoning", "evidence_basis", "practice_name")
    )
    if assigned_tier == "true_independent":
        if not CURRENT_OWNER_RE.search(text):
            signals.append(
                signal(
                    "t1_reasoning_lacks_owner_word",
                    "low",
                    1,
                    "T1 reasoning does not explicitly state current owner/ownership language.",
                    category="evidence",
                )
            )
        if not SINGLE_LOC_RE.search(text):
            signals.append(
                signal(
                    "t1_reasoning_lacks_single_location_word",
                    "low",
                    1,
                    "T1 reasoning does not explicitly state single-location/solo proof.",
                    category="evidence",
                )
            )
        if not NO_CORP_RE.search(text):
            signals.append(
                signal(
                    "t1_reasoning_lacks_negative_control_word",
                    "low",
                    1,
                    "T1 reasoning does not explicitly mention negative DSO/MSO/parent/network checks.",
                    category="evidence",
                )
            )
    if STALE_TEXT_RE.search(text):
        signals.append(
            signal(
                "stale_founder_history",
                "low",
                1,
                "Evidence contains old founder/history language; current ownership should be separately corroborated.",
                category="stale",
            )
        )

    if ctx is None:
        signals.append(
            signal(
                "location_missing_from_db",
                "high",
                5,
                "Result location_id was not found in practice_locations.",
                category="integrity",
            )
        )
        return finalize_assessment(row, signals, None)

    loc = ctx["loc"]
    provider_count = loc.get("provider_count") or len(ctx["provider_rows"])
    provider_surnames = ctx["provider_surnames"]
    loc_class = loc.get("entity_classification")

    if assigned_tier == "true_independent":
        if provider_count and int(provider_count) > 1:
            signals.append(
                signal(
                    "t1_provider_count_gt1",
                    "hard",
                    6,
                    "T1 conflicts with DB provider_count > 1; likely not true solo owner-operated.",
                    {
                        "provider_count": provider_count,
                        "provider_surnames": sorted(provider_surnames),
                    },
                    category="structural",
                )
            )
        if loc_class in GROUP_ENTITY_CLASSES:
            signals.append(
                signal(
                    "t1_group_entity_classification",
                    "hard",
                    5,
                    "T1 conflicts with location entity_classification indicating a group practice.",
                    {"entity_classification": loc_class},
                    category="structural",
                )
            )
        if len(provider_surnames) > 1:
            signals.append(
                signal(
                    "t1_multiple_provider_surnames",
                    "hard",
                    5,
                    "T1 has multiple individual provider surnames bridged to the location.",
                    {"provider_surnames": sorted(provider_surnames)},
                    category="structural",
                )
            )

    if assigned_tier == "single_loc_group" and provider_count and int(provider_count) <= 1:
        signals.append(
            signal(
                "t2_provider_count_lte1",
                "medium",
                2,
                "T2 has provider_count <= 1; may be a false group or a stale roster.",
                {"provider_count": provider_count},
                category="structural",
            )
        )

    if loc_class in CORPORATE_ENTITY_CLASSES or has_corp_text(loc.get("affiliated_dso")):
        signals.append(
            signal(
                "db_corporate_conflict",
                "hard",
                6,
                "Lane A dentist-owned/independent tier conflicts with existing DB corporate classifier or affiliated_dso.",
                {
                    "entity_classification": loc_class,
                    "affiliated_dso": loc.get("affiliated_dso"),
                    "affiliated_pe_sponsor": loc.get("affiliated_pe_sponsor"),
                },
                category="corporate",
            )
        )

    parent_values = []
    for source, value in [
        ("practice_locations.parent_company", loc.get("parent_company")),
        ("practice_locations.affiliated_pe_sponsor", loc.get("affiliated_pe_sponsor")),
    ]:
        if has_corp_text(value):
            parent_values.append({"source": source, "value": value})
    for r in ctx["npi_rows"]:
        for key in (
            "parent_company",
            "parent_org_lbn",
            "parent_iusa",
            "da_subsidiary_iusa",
        ):
            if has_corp_text(r.get(key)):
                parent_values.append({"source": f"practices.{key}", "value": r.get(key)})
    if parent_values:
        signals.append(
            signal(
                "parent_or_legal_entity_signal",
                "medium",
                3,
                "Parent/legal-entity fields are populated; needs verification that this is not corporate/MSO control.",
                {"values": parent_values[:12]},
                category="corporate",
            )
        )

    da_legal_names = sorted(
        {
            str(r.get("da_legal_name")).strip()
            for r in ctx["npi_rows"]
            if has_corp_text(r.get("da_legal_name"))
        }
    )
    for legal_name in da_legal_names[:5]:
        legal_tokens = name_tokens(legal_name)
        practice_tokens = name_tokens(loc.get("practice_name")) | name_tokens(
            loc.get("doing_business_as")
        )
        if legal_tokens and not (legal_tokens & practice_tokens):
            signals.append(
                signal(
                    "da_legal_name_mismatch",
                    "low",
                    1,
                    "Data-Axle legal name does not share meaningful tokens with the practice name; weak corroboration-only signal.",
                    {"da_legal_name": legal_name},
                    category="weak",
                )
            )

    for ao in ctx["ao_records"]:
        reach = cluster_ids(clusters, "ao", ao["key"])
        if len(reach) > 1:
            score = 4 if len(reach) >= 3 else 3
            signals.append(
                signal(
                    "ao_reaches_multiple_locations",
                    "medium",
                    score,
                    "Authorized official appears across multiple locations; T1/T2 cannot remain clean without owner/network review.",
                    {
                        "ao": ao,
                        "reach_count": len(reach),
                        "sample_location_ids": reach[:12],
                    },
                    category="network",
                )
            )
        if is_exec_title(ao.get("title"), ao.get("credential")):
            signals.append(
                signal(
                    "ao_nonclinical_exec_title",
                    "hard",
                    5,
                    "Organization NPI authorized official has a non-clinical executive title.",
                    {"ao": ao},
                    category="corporate",
                )
            )
        ao_last = re.sub(r"[^A-Z]", "", str(ao.get("last") or "").upper())
        practice_tokens = name_tokens(loc.get("practice_name")) | name_tokens(
            loc.get("doing_business_as")
        )
        if (
            ao_last
            and ao_last not in provider_surnames
            and ao_last not in practice_tokens
            and assigned_tier in {"true_independent", "single_loc_group"}
        ):
            signals.append(
                signal(
                    "ao_not_provider_or_practice_name",
                    "low",
                    1,
                    "AO surname is not in the bridged provider surnames or practice name; weak signal alone.",
                    {
                        "ao": ao,
                        "provider_surnames": sorted(provider_surnames),
                        "practice_tokens": sorted(practice_tokens),
                    },
                    category="weak",
                )
            )

    for ein in sorted(ctx["eins"]):
        reach = cluster_ids(clusters, "ein", ein)
        if len(reach) > 1:
            signals.append(
                signal(
                    "shared_ein_or_parent_tin",
                    "medium",
                    4 if len(reach) >= 3 else 3,
                    "EIN / parent TIN appears across multiple locations.",
                    {"ein": ein, "reach_count": len(reach), "sample_location_ids": reach[:12]},
                    category="network",
                )
            )

    for key in sorted(ctx["mail_keys"]):
        reach = cluster_ids(clusters, "mail", key)
        if len(reach) >= 3:
            signals.append(
                signal(
                    "shared_backoffice_mailing",
                    "medium",
                    3,
                    "Back-office mailing address is shared across 3+ locations.",
                    {"mail_key": key, "reach_count": len(reach), "sample_location_ids": reach[:12]},
                    category="network",
                )
            )

    for key in sorted(ctx["phones"]):
        reach = cluster_ids(clusters, "phone", key)
        if len(reach) > 1:
            signals.append(
                signal(
                    "shared_phone_multiple_locations",
                    "medium",
                    2,
                    "Phone number appears across multiple locations; review for network or duplicate.",
                    {"phone": key, "reach_count": len(reach), "sample_location_ids": reach[:12]},
                    category="network",
                )
            )

    for key in sorted(ctx["domains"]):
        reach = cluster_ids(clusters, "domain", key)
        if len(reach) > 1:
            signals.append(
                signal(
                    "shared_website_domain",
                    "medium",
                    2,
                    "Website domain is shared across multiple locations; review for multi-location group or DSO.",
                    {"domain": key, "reach_count": len(reach), "sample_location_ids": reach[:12]},
                    category="network",
                )
            )

    for key in sorted(ctx["da_officers"]):
        reach = cluster_ids(clusters, "da_officer", key)
        if len(reach) >= 3:
            signals.append(
                signal(
                    "shared_data_axle_officer",
                    "low",
                    2,
                    "Data-Axle officer appears across 3+ locations; corroboration-only signal.",
                    {"officer": key, "reach_count": len(reach), "sample_location_ids": reach[:12]},
                    category="network",
                )
            )

    if assigned_tier == "dentist_multi":
        network_codes = {
            "ao_reaches_multiple_locations",
            "shared_ein_or_parent_tin",
            "shared_backoffice_mailing",
            "shared_phone_multiple_locations",
            "shared_website_domain",
            "shared_data_axle_officer",
        }
        if not row.get("network_id") and not any(s["code"] in network_codes for s in signals):
            signals.append(
                signal(
                    "t3_network_basis_not_structurally_visible",
                    "low",
                    1,
                    "T3 has no network_id and no deterministic network signal in this screen; verify source basis.",
                    category="evidence",
                )
            )

    return finalize_assessment(row, signals, ctx)


def finalize_assessment(
    row: dict[str, Any], signals: list[dict[str, Any]], ctx: dict[str, Any] | None
) -> dict[str, Any]:
    assigned_tier = row.get("assigned_tier")
    hard = [s for s in signals if s["severity"] == "hard"]
    network = [s for s in signals if s["category"] == "network"]
    evidence = [s for s in signals if s["category"] == "evidence"]
    score = sum(int(s["score"]) for s in signals)
    if hard:
        priority = "block_before_merge"
    elif assigned_tier in {"true_independent", "single_loc_group"} and len(network) >= 2:
        priority = "block_before_merge"
    elif score >= 6 or (network and evidence):
        priority = "review_high"
    elif score >= 3:
        priority = "review_medium"
    elif signals:
        priority = "sample_low"
    else:
        priority = "clean_screen"

    loc = ctx["loc"] if ctx else {}
    return {
        "location_id": row.get("location_id"),
        "practice_name": row.get("practice_name") or loc.get("practice_name"),
        "zip": row.get("zip") or loc.get("zip"),
        "unit_id": row.get("_unit_id"),
        "file": row.get("_file"),
        "assigned_tier": row.get("assigned_tier"),
        "confidence": row.get("confidence"),
        "status": row.get("status"),
        "priority": priority,
        "score": score,
        "signals": signals,
        "db_context": {
            "entity_classification": loc.get("entity_classification"),
            "provider_count": loc.get("provider_count"),
            "primary_npi": loc.get("primary_npi"),
            "org_npi": loc.get("org_npi"),
            "provider_npis": parse_json_list(loc.get("provider_npis")),
            "ownership_tier": loc.get("ownership_tier"),
            "network_id": loc.get("network_id"),
            "phone": loc.get("phone"),
            "website": loc.get("website"),
        },
        "reasoning_excerpt": str(row.get("reasoning") or "")[:700],
        "evidence_urls": evidence_urls(row),
    }


def main() -> int:
    args = parse_args()
    target_tiers = {t.strip() for t in args.tiers.split(",") if t.strip()}

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    locations = load_locations(conn)
    all_npis: set[str] = set()
    for loc in locations.values():
        all_npis.update(location_npis(loc))
    practices = load_practices(conn, sorted(all_npis))
    conn.close()

    contexts, clusters = build_contexts(locations, practices)
    result_rows = load_result_rows(args.results_dir)
    target_rows = [
        row
        for row in result_rows
        if row.get("assigned_tier") in target_tiers and row.get("status") == "classified"
    ]
    assessments = [
        assess_row(row, contexts.get(row.get("location_id")), clusters)
        for row in target_rows
    ]
    suspects = [a for a in assessments if a["priority"] != "clean_screen"]
    suspects.sort(
        key=lambda a: (
            {
                "block_before_merge": 0,
                "review_high": 1,
                "review_medium": 2,
                "sample_low": 3,
            }.get(a["priority"], 9),
            -a["score"],
            str(a["zip"] or ""),
            str(a["practice_name"] or ""),
        )
    )

    priority_counts = collections.Counter(a["priority"] for a in assessments)
    tier_counts = collections.Counter(a["assigned_tier"] for a in assessments)
    signal_counts = collections.Counter(
        s["code"] for a in assessments for s in a["signals"]
    )
    priority_by_tier = collections.defaultdict(collections.Counter)
    for a in assessments:
        priority_by_tier[a["assigned_tier"]][a["priority"]] += 1

    output = {
        "_meta": {
            "generated_by": "scrapers/screen_true_independent_hardening.py",
            "purpose": (
                "Read-only deterministic screen for false T1/T2/T3 and hidden "
                "control risk before Lane A consolidation."
            ),
            "db": os.path.relpath(args.db, ROOT),
            "results_dir": os.path.relpath(args.results_dir, ROOT),
            "target_tiers": sorted(target_tiers),
            "result_rows_loaded": len(result_rows),
            "target_rows_screened": len(assessments),
            "suspect_rows": len(suspects),
            "clean_rows": priority_counts.get("clean_screen", 0),
            "decision_rule": (
                "hard signal or >=2 network signals => block_before_merge; "
                "review_high/review_medium are PM/analyst queues, not automatic re-tiers."
            ),
        },
        "summary": {
            "tier_counts": dict(tier_counts),
            "priority_counts": dict(priority_counts),
            "priority_by_tier": {
                tier: dict(counts) for tier, counts in priority_by_tier.items()
            },
            "top_signal_counts": dict(signal_counts.most_common(40)),
        },
        "suspects": suspects,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, sort_keys=True)

    print("True-independent hardening screen complete")
    print(f"  result rows loaded: {len(result_rows)}")
    print(f"  target rows screened: {len(assessments)}")
    print(f"  clean rows: {priority_counts.get('clean_screen', 0)}")
    print(f"  suspects: {len(suspects)}")
    for key, count in priority_counts.most_common():
        print(f"  {key}: {count}")
    print("  top signals:")
    for code, count in signal_counts.most_common(12):
        print(f"    {code}: {count}")
    print(f"  written -> {os.path.relpath(args.output, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
