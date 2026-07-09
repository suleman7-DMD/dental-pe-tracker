"""Promote exact-matched, documentary-verified Chicagoland DSO locations.

This is a narrow follow-up to the 2026-06-12 audit. The older IL DSO seeding
script used a coarse xref key (house number + ZIP + first street token), which
is fine for a first-pass undercount scan but too collision-prone for final
location promotion. This script uses stricter normalized street+ZIP matching
against `practice_locations.normalized_address`.

Inputs are documentary sources already captured in the repo:
  * data/dso_research/il_dso_locations_merged.json
    Government/DSO-locator/friendly-PC verified IL DSO source list.
  * data/dso_research/locator_results_20260612/*.json
    DSO-owned locator pages collected during the interrupted June 12 session.

Rules:
  * IL watched ZIPs only.
  * Promote only GP-location classes that are currently independent.
  * Do not promote specialist-only/non-clinical/da_unverified rows.
  * Do not re-promote any location in false-corporate demotion audit files.
  * Every raw SQL UPDATE bumps updated_at.
  * Recompute IL zip_scores directly from practice_locations afterward.

Audit output:
  data/dso_research/il_verified_locator_promotions_20260619.json
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from collections import defaultdict
from typing import Any


DB = "data/dental_pe_tracker.db"
MERGED = "data/dso_research/il_dso_locations_merged.json"
LOCATOR_DIR = "data/dso_research/locator_results_20260612"
DEMOTIONS_GLOB = "data/dso_research/il_false_corporate_demotions_*.json"
AUDIT = "data/dso_research/il_verified_locator_promotions_20260619.json"
MARKER = "[verified locator/PC audit 2026-06-19]"

INDEP = {
    "solo_established",
    "solo_new",
    "solo_inactive",
    "solo_high_volume",
    "family_practice",
    "small_group",
    "large_group",
}
CORP = {"dso_regional", "dso_national"}
GP_CLASSES = INDEP | CORP

NATIONAL = {
    "Aspen Dental",
    "Heartland Dental",
    "Dental Dreams",
    "Affordable Care",
    "Affordable Dentures & Implants",
    "Smile Doctors",
    "Western Dental",
}

DIRS = {
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
}
SUFFIXES = {
    "street": "st",
    "st.": "st",
    "avenue": "ave",
    "ave.": "ave",
    "road": "rd",
    "rd.": "rd",
    "boulevard": "blvd",
    "blvd.": "blvd",
    "drive": "dr",
    "dr.": "dr",
    "court": "ct",
    "ct.": "ct",
    "place": "pl",
    "pl.": "pl",
    "parkway": "pkwy",
    "lane": "ln",
    "ln.": "ln",
    "highway": "hwy",
}
UNIT_WORDS = {
    "suite",
    "ste",
    "unit",
    "apt",
    "apartment",
    "fl",
    "floor",
    "bldg",
    "building",
    "room",
    "rm",
}


def normalize_street(value: str | None) -> str:
    """Normalize enough for exact street+ZIP matching, not fuzzy matching.

    Drops suite/unit fragments and standardizes direction/suffix tokens. It
    deliberately does not use the older house+first-street-token key because
    that key collided hundreds of times in Chicagoland.
    """
    s = (value or "").lower().replace("&", " and ")
    s = re.sub(r"#\s*[a-z0-9-]+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens: list[str] = []
    for token in s.split():
        if token in UNIT_WORDS:
            break
        token = DIRS.get(token, token)
        token = SUFFIXES.get(token, token)
        tokens.append(token)
    return " ".join(tokens)


def address_key(address: str | None, zip_code: str | None) -> tuple[str, str] | None:
    street = normalize_street(address)
    zip5 = (zip_code or "")[:5]
    if not street or not zip5:
        return None
    return street, zip5


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def iter_verified_sources(watched_il: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if os.path.exists(MERGED):
        for rec in load_json(MERGED):
            if (rec.get("zip") or "")[:5] not in watched_il:
                continue
            rows.append(
                {
                    "dso_name": rec.get("dso_name"),
                    "pe_sponsor": rec.get("pe_sponsor"),
                    "location_name": rec.get("location_name"),
                    "address": rec.get("address"),
                    "city": rec.get("city"),
                    "zip": (rec.get("zip") or "")[:5],
                    "phone": rec.get("phone"),
                    "source_type": "merged_verified_il_dso",
                    "source_url": "data/dso_research/il_dso_locations_merged.json",
                    "source_detail": "+".join(rec.get("_sources", [])),
                    "confidence": rec.get("confidence", "high"),
                }
            )

    if os.path.isdir(LOCATOR_DIR):
        for path in sorted(glob.glob(os.path.join(LOCATOR_DIR, "*.json"))):
            data = load_json(path)
            offices = data.get("offices", []) if isinstance(data, dict) else data
            for office in offices:
                if (office.get("state") or "IL").upper() not in {"IL", "ILLINOIS"}:
                    continue
                if (office.get("zip") or "")[:5] not in watched_il:
                    continue
                rows.append(
                    {
                        "dso_name": data.get("dso_name"),
                        "pe_sponsor": data.get("pe_sponsor"),
                        "location_name": office.get("name"),
                        "address": office.get("address"),
                        "city": office.get("city"),
                        "zip": (office.get("zip") or "")[:5],
                        "phone": office.get("phone"),
                        "source_type": "dso_owned_locator_20260612",
                        "source_url": office.get("source_url") or path,
                        "source_detail": os.path.basename(path),
                        "confidence": "high",
                    }
                )

    # One source per exact address+brand is enough for promotion, but keep all
    # source details in the audit for traceability.
    dedup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = address_key(row.get("address"), row.get("zip"))
        if not key or not row.get("dso_name"):
            continue
        dkey = (key[0], key[1], row["dso_name"])
        existing = dedup.get(dkey)
        if existing is None:
            row["_address_key"] = key
            row["_all_sources"] = [
                {
                    "source_type": row["source_type"],
                    "source_url": row["source_url"],
                    "source_detail": row["source_detail"],
                }
            ]
            dedup[dkey] = row
        else:
            existing["_all_sources"].append(
                {
                    "source_type": row["source_type"],
                    "source_url": row["source_url"],
                    "source_detail": row["source_detail"],
                }
            )
            if not existing.get("pe_sponsor") and row.get("pe_sponsor"):
                existing["pe_sponsor"] = row["pe_sponsor"]
    return list(dedup.values())


def loc_npis(row: sqlite3.Row) -> list[str]:
    out: list[str] = []
    for col in ("primary_npi", "org_npi"):
        if row[col]:
            out.append(row[col])
    if row["provider_npis"]:
        try:
            out.extend(n for n in json.loads(row["provider_npis"]) if n)
        except Exception:
            pass
    return list(dict.fromkeys(out))


def is_directory_only_location(row: sqlite3.Row) -> bool:
    npi = row["primary_npi"] or ""
    return npi.startswith("DA_") or npi.startswith("DIR_")


def normalized_phone(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def recompute_il_zip_scores(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    for (zip_code,) in conn.execute("SELECT zip_code FROM zip_scores WHERE state='IL'").fetchall():
        total = conn.execute(
            """
            SELECT COUNT(*) FROM practice_locations
            WHERE substr(zip,1,5)=?
              AND entity_classification IN (
                'solo_established','solo_new','solo_inactive','solo_high_volume',
                'family_practice','small_group','large_group',
                'dso_regional','dso_national'
              )
            """,
            (zip_code,),
        ).fetchone()[0]
        corp = conn.execute(
            """
            SELECT COUNT(*) FROM practice_locations
            WHERE substr(zip,1,5)=?
              AND entity_classification IN ('dso_regional','dso_national')
            """,
            (zip_code,),
        ).fetchone()[0]
        cur.execute(
            """
            UPDATE zip_scores
               SET total_gp_locations=?,
                   corporate_location_count=?,
                   corporate_share_pct=CASE
                       WHEN ?>0 THEN ROUND(1.0*?/?,4)
                       ELSE 0
                   END
             WHERE zip_code=?
            """,
            (total, corp, total, corp, total, zip_code),
        )


def main(apply: bool = True) -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    watched_il = {
        r[0]
        for r in conn.execute("SELECT zip_code FROM watched_zips WHERE state='IL'").fetchall()
    }
    demotion_ids: set[str] = set()
    for path in sorted(glob.glob(DEMOTIONS_GLOB)):
        data = load_json(path)
        demotion_ids |= {d["location_id"] for d in data.get("demotions", [])}

    loc_by_key: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    corp_by_zip_phone: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in conn.execute(
        """
        SELECT pl.* FROM practice_locations pl
        JOIN watched_zips w ON substr(pl.zip,1,5)=w.zip_code
        WHERE w.state='IL'
        """
    ):
        key = address_key(row["normalized_address"], row["zip"])
        if key:
            loc_by_key[key].append(row)
        phone_key = normalized_phone(row["phone"])
        if phone_key and row["entity_classification"] in CORP:
            corp_by_zip_phone[(row["zip"], phone_key)].append(row)

    gp0, corp0 = conn.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    il0 = conn.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores WHERE state='IL'"
    ).fetchone()
    npi0 = conn.execute(
        """
        SELECT COUNT(*) FROM practices p
        JOIN watched_zips w ON p.zip=w.zip_code
        WHERE p.entity_classification IN ('dso_regional','dso_national')
        """
    ).fetchone()[0]

    audit: dict[str, Any] = {
        "generated": "2026-06-19",
        "method": "strict normalized street+ZIP exact match against documentary DSO sources",
        "before": {
            "watched_gp_locations": gp0,
            "watched_corporate_locations": corp0,
            "il_gp_locations": il0[0],
            "il_corporate_locations": il0[1],
            "watched_corporate_npis": npi0,
        },
        "promotions": [],
        "skipped": [],
    }

    promote: dict[str, dict[str, Any]] = {}
    for source in iter_verified_sources(watched_il):
        key = source["_address_key"]
        matches = loc_by_key.get(key, [])
        if not matches:
            audit["skipped"].append({"reason": "no_practice_location_exact_match", "source": source})
            continue

        for loc in matches:
            lid = loc["location_id"]
            if lid in demotion_ids:
                audit["skipped"].append(
                    {"reason": "blocked_by_false_corporate_demotion_audit", "location_id": lid, "source": source}
                )
                continue
            ec = loc["entity_classification"]
            if ec in CORP:
                audit["skipped"].append(
                    {"reason": "already_corporate", "location_id": lid, "current_class": ec, "source": source}
                )
                continue
            if is_directory_only_location(loc):
                audit["skipped"].append(
                    {
                        "reason": "directory_only_primary_record_not_promoted_to_floor",
                        "location_id": lid,
                        "current_class": ec,
                        "primary_npi": loc["primary_npi"],
                        "source": source,
                    }
                )
                continue
            phone_key = normalized_phone(loc["phone"])
            same_phone_corps = [
                r
                for r in corp_by_zip_phone.get((loc["zip"], phone_key), [])
                if r["location_id"] != lid
            ] if phone_key else []
            if same_phone_corps:
                audit["skipped"].append(
                    {
                        "reason": "same_zip_phone_already_has_corporate_location",
                        "location_id": lid,
                        "current_class": ec,
                        "same_phone_corporate_locations": [
                            {
                                "location_id": r["location_id"],
                                "practice_name": r["practice_name"],
                                "address": r["normalized_address"],
                                "class": r["entity_classification"],
                            }
                            for r in same_phone_corps
                        ],
                        "source": source,
                    }
                )
                continue
            if ec not in INDEP:
                audit["skipped"].append(
                    {"reason": "not_gp_independent_class", "location_id": lid, "current_class": ec, "source": source}
                )
                continue

            existing = promote.get(lid)
            if existing is None:
                promote[lid] = {"location": loc, "source": source}
            else:
                existing["source"]["_all_sources"].extend(source.get("_all_sources", []))
                if (
                    existing["source"].get("dso_name") != source.get("dso_name")
                    and source.get("source_type") == "dso_owned_locator_20260612"
                ):
                    # Prefer the current DSO-owned locator when two historical
                    # source rows disagree on a brand at the same address.
                    existing["source"] = source

    # Final DB-state guard: if another cleanup step has already moved a row out
    # of an independent GP class, do not promote a stale in-memory candidate.
    for lid in list(promote):
        current = conn.execute(
            "SELECT entity_classification FROM practice_locations WHERE location_id=?",
            (lid,),
        ).fetchone()
        if not current or current["entity_classification"] not in INDEP:
            audit["skipped"].append(
                {
                    "reason": "final_current_class_not_independent",
                    "location_id": lid,
                    "current_class": current["entity_classification"] if current else None,
                    "source": promote[lid]["source"],
                }
            )
            del promote[lid]

    print(
        f"BEFORE floor={corp0}/{gp0}={100*corp0/gp0:.2f}% "
        f"(IL {il0[1]}/{il0[0]}={100*il0[1]/il0[0]:.2f}%) corp NPIs={npi0}"
    )
    print(f"PROMOTE {len(promote)} exact-matched watched-IL GP locations")
    for item in promote.values():
        loc = item["location"]
        src = item["source"]
        print(
            f"  {loc['location_id']} {loc['entity_classification']:16} -> "
            f"{src['dso_name']}: {loc['practice_name']} | {loc['normalized_address']} {loc['zip']}"
        )

    if not apply:
        print("(dry-run: no writes)")
        conn.close()
        return

    npi_updates = 0
    for lid, item in promote.items():
        loc = item["location"]
        src = item["source"]
        current = conn.execute(
            "SELECT entity_classification FROM practice_locations WHERE location_id=?",
            (lid,),
        ).fetchone()
        if not current or current["entity_classification"] not in INDEP:
            audit["skipped"].append(
                {
                    "reason": "apply_current_class_not_independent",
                    "location_id": lid,
                    "current_class": current["entity_classification"] if current else None,
                    "source": src,
                }
            )
            continue
        dso = src["dso_name"]
        sponsor = src.get("pe_sponsor")
        new_ec = "dso_national" if dso in NATIONAL else "dso_regional"
        ownership_status = "pe_backed" if sponsor else "dso_affiliated"
        source_summary = "; ".join(
            sorted(
                {
                    f"{s['source_type']}:{s.get('source_detail') or s.get('source_url')}"
                    for s in src.get("_all_sources", [])
                }
            )
        )
        reason = (
            f"{MARKER} PROMOTED {loc['entity_classification']}->{new_ec}: "
            f"exact normalized address match to documentary DSO source for {dso}; "
            f"source={source_summary}; locator_url={src.get('source_url') or 'n/a'}"
        )
        cur.execute(
            """
            UPDATE practice_locations
               SET entity_classification=?,
                   ownership_status=?,
                   affiliated_dso=?,
                   affiliated_pe_sponsor=?,
                   classification_reasoning=?,
                   classification_confidence=95,
                   updated_at=datetime('now')
             WHERE location_id=?
            """,
            (new_ec, ownership_status, dso, sponsor, reason, lid),
        )

        flipped: list[dict[str, str]] = []
        for npi in loc_npis(loc):
            res = cur.execute(
                """
                UPDATE practices
                   SET entity_classification=?,
                       ownership_status=?,
                       affiliated_dso=?,
                       affiliated_pe_sponsor=?,
                       updated_at=datetime('now')
                 WHERE npi=?
                   AND (
                        entity_classification IS NULL
                        OR entity_classification IN (
                          'solo_established','solo_new','solo_inactive',
                          'solo_high_volume','family_practice','small_group',
                          'large_group','org_only_npi'
                        )
                   )
                """,
                (new_ec, ownership_status, dso, sponsor, npi),
            )
            if res.rowcount:
                npi_updates += 1
                flipped.append({"npi": npi, "to": new_ec})

        audit["promotions"].append(
            {
                "location_id": lid,
                "practice_name": loc["practice_name"],
                "address": loc["normalized_address"],
                "city": loc["city"],
                "zip": loc["zip"],
                "old_class": loc["entity_classification"],
                "new_class": new_ec,
                "dso_name": dso,
                "pe_sponsor": sponsor,
                "source": {
                    "location_name": src.get("location_name"),
                    "source_url": src.get("source_url"),
                    "all_sources": src.get("_all_sources", []),
                },
                "npi_flips": flipped,
            }
        )

    recompute_il_zip_scores(conn)
    conn.commit()

    gp1, corp1 = conn.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    il1 = conn.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores WHERE state='IL'"
    ).fetchone()
    npi1 = conn.execute(
        """
        SELECT COUNT(*) FROM practices p
        JOIN watched_zips w ON p.zip=w.zip_code
        WHERE p.entity_classification IN ('dso_regional','dso_national')
        """
    ).fetchone()[0]
    audit["after"] = {
        "watched_gp_locations": gp1,
        "watched_corporate_locations": corp1,
        "watched_floor_pct": round(100.0 * corp1 / gp1, 4) if gp1 else 0,
        "il_gp_locations": il1[0],
        "il_corporate_locations": il1[1],
        "il_floor_pct": round(100.0 * il1[1] / il1[0], 4) if il1[0] else 0,
        "watched_corporate_npis": npi1,
        "npi_updates": npi_updates,
    }
    with open(AUDIT, "w") as f:
        json.dump(audit, f, indent=2, default=str)

    print(
        f"AFTER  floor={corp1}/{gp1}={100*corp1/gp1:.2f}% "
        f"(IL {il1[1]}/{il1[0]}={100*il1[1]/il1[0]:.2f}%) corp NPIs={npi1}"
    )
    print(f"NPI rows updated: {npi_updates}")
    print(f"audit written: {AUDIT}")
    conn.close()


if __name__ == "__main__":
    import sys

    main(apply="--dry-run" not in sys.argv)
