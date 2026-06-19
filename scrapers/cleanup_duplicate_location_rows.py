"""Exclude documented duplicate practice_location rows from GP denominators.

NPPES emits providers and organizations separately. Most of those collapse into
one `practice_locations` row, but a few suite/direction variants still produce a
second location row at the same real office. The 2026-06-19 audit found a small
high-confidence subset: an independent-looking row shares ZIP, phone, house
number, and street core with an already corporate row.

These rows are not "independent offices" and should not be promoted as new
corporate offices either. They are duplicate location artifacts. We mark only
that high-confidence subset as `duplicate_location`, which the scorer/frontend
exclude from GP denominators and maps.

Audit output:
  data/dso_research/duplicate_location_cleanup_20260619.json
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from typing import Any


DB = "data/dental_pe_tracker.db"
AUDIT = "data/dso_research/duplicate_location_cleanup_20260619.json"
MARKER = "[duplicate-location audit 2026-06-19]"

GP_CLASSES = {
    "solo_established",
    "solo_new",
    "solo_inactive",
    "solo_high_volume",
    "family_practice",
    "small_group",
    "large_group",
    "dso_regional",
    "dso_national",
}
CORP = {"dso_regional", "dso_national"}


def clean_phone(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def duplicate_key(row: sqlite3.Row) -> tuple[str, str, str, str] | None:
    phone = clean_phone(row["phone"])
    if not phone:
        return None
    address = (row["normalized_address"] or "").lower()
    address = re.sub(r"[^a-z0-9\s]", " ", address)
    tokens = address.split()
    if not tokens:
        return None
    house = tokens[0]
    dirs = {"n", "s", "e", "w", "north", "south", "east", "west"}
    suffixes = {
        "st",
        "street",
        "ave",
        "avenue",
        "rd",
        "road",
        "blvd",
        "drive",
        "dr",
        "ct",
        "court",
        "ln",
        "lane",
        "hwy",
        "highway",
    }
    unit_words = {"suite", "ste", "unit", "apt", "fl", "floor", "room", "rm"}
    street = ""
    for token in tokens[1:]:
        if token in unit_words:
            break
        if token in dirs or token in suffixes:
            continue
        street = token[:8]
        break
    if not street:
        return None
    return (row["zip"], phone, house, street)


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

    gp0, corp0 = conn.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    il0 = conn.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores WHERE state='IL'"
    ).fetchone()

    rows = list(
        conn.execute(
            """
            SELECT pl.* FROM practice_locations pl
            JOIN watched_zips w ON substr(pl.zip,1,5)=w.zip_code
            WHERE w.state='IL'
              AND pl.entity_classification IN (
                'solo_established','solo_new','solo_inactive','solo_high_volume',
                'family_practice','small_group','large_group',
                'dso_regional','dso_national'
              )
              AND pl.phone IS NOT NULL
            """
        )
    )
    groups: dict[tuple[str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        key = duplicate_key(row)
        if key:
            groups[key].append(row)

    duplicates: list[dict[str, Any]] = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        corp_rows = [r for r in group if r["entity_classification"] in CORP]
        non_corp_rows = [r for r in group if r["entity_classification"] not in CORP]
        if not corp_rows or not non_corp_rows:
            continue
        # The corporate row is the canonical counted office. The non-corporate
        # rows are duplicate provider/org artifacts at the same real office.
        for row in non_corp_rows:
            duplicates.append(
                {
                    "location_id": row["location_id"],
                    "practice_name": row["practice_name"],
                    "address": row["normalized_address"],
                    "zip": row["zip"],
                    "old_class": row["entity_classification"],
                    "phone": row["phone"],
                    "primary_npi": row["primary_npi"],
                    "corporate_sibling_locations": [
                        {
                            "location_id": c["location_id"],
                            "practice_name": c["practice_name"],
                            "address": c["normalized_address"],
                            "class": c["entity_classification"],
                            "primary_npi": c["primary_npi"],
                        }
                        for c in corp_rows
                    ],
                }
            )

    print(
        f"BEFORE floor={corp0}/{gp0}={100*corp0/gp0:.2f}% "
        f"(IL {il0[1]}/{il0[0]}={100*il0[1]/il0[0]:.2f}%)"
    )
    print(f"DUPLICATE LOCATION ROWS TO EXCLUDE: {len(duplicates)}")
    for row in duplicates:
        sib = row["corporate_sibling_locations"][0]
        print(
            f"  {row['location_id']} {row['old_class']:16} -> duplicate_location: "
            f"{row['practice_name']} | sibling {sib['practice_name']}"
        )

    if not apply:
        print("(dry-run: no writes)")
        conn.close()
        return

    for row in duplicates:
        reason = (
            f"{MARKER} EXCLUDED from GP location denominator: same ZIP, phone, "
            f"house number, and street core as already-counted corporate location "
            f"{row['corporate_sibling_locations'][0]['location_id']} "
            f"({row['corporate_sibling_locations'][0]['practice_name']})."
        )
        cur.execute(
            """
            UPDATE practice_locations
               SET entity_classification='duplicate_location',
                   ownership_status='unknown',
                   classification_reasoning=?,
                   classification_confidence=95,
                   updated_at=datetime('now')
             WHERE location_id=?
            """,
            (reason, row["location_id"]),
        )
        if row["primary_npi"]:
            cur.execute(
                """
                UPDATE practices
                   SET entity_classification='duplicate_location',
                       ownership_status='unknown',
                       updated_at=datetime('now')
                 WHERE npi=?
                """,
                (row["primary_npi"],),
            )

    recompute_il_zip_scores(conn)
    conn.commit()

    gp1, corp1 = conn.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    il1 = conn.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores WHERE state='IL'"
    ).fetchone()
    audit = {
        "generated": "2026-06-19",
        "method": "same ZIP + normalized phone + house number + street core as already-corporate location",
        "before": {
            "watched_gp_locations": gp0,
            "watched_corporate_locations": corp0,
            "il_gp_locations": il0[0],
            "il_corporate_locations": il0[1],
        },
        "after": {
            "watched_gp_locations": gp1,
            "watched_corporate_locations": corp1,
            "watched_floor_pct": round(100.0 * corp1 / gp1, 4) if gp1 else 0,
            "il_gp_locations": il1[0],
            "il_corporate_locations": il1[1],
            "il_floor_pct": round(100.0 * il1[1] / il1[0], 4) if il1[0] else 0,
        },
        "duplicates": duplicates,
    }
    with open(AUDIT, "w") as f:
        json.dump(audit, f, indent=2, default=str)
    print(
        f"AFTER  floor={corp1}/{gp1}={100*corp1/gp1:.2f}% "
        f"(IL {il1[1]}/{il1[0]}={100*il1[1]/il1[0]:.2f}%)"
    )
    print(f"audit written: {AUDIT}")
    conn.close()


if __name__ == "__main__":
    import sys

    main(apply="--dry-run" not in sys.argv)
