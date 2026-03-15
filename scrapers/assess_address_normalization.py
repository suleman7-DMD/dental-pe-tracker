"""
Address Normalization Assessment — Phase 2.1

Compares Method A (current: address.upper().strip()) vs Method B (enhanced:
expand abbreviations, strip suites, collapse spaces) for address deduplication.

If the average difference exceeds 5%, enhanced normalization should be ported
into merge_and_score.py's deduplicate_practices_in_zip().

Usage:
    python3 scrapers/assess_address_normalization.py
"""

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.database import init_db, get_session

# ── Address abbreviations (same as data_axle_importer.py) ─────────────────

ADDR_ABBREVS = {
    r"\bST\b": "STREET", r"\bDR\b": "DRIVE", r"\bAVE\b": "AVENUE",
    r"\bBLVD\b": "BOULEVARD", r"\bRD\b": "ROAD", r"\bLN\b": "LANE",
    r"\bCT\b": "COURT", r"\bPL\b": "PLACE", r"\bCIR\b": "CIRCLE",
    r"\bHWY\b": "HIGHWAY", r"\bPKY\b": "PARKWAY", r"\bPKWY\b": "PARKWAY",
    r"\bN\b": "NORTH", r"\bS\b": "SOUTH", r"\bE\b": "EAST", r"\bW\b": "WEST",
}

TEST_ZIPS = ["60491", "60439", "60441", "60440", "60517"]


def normalize_method_a(addr):
    """Current method used by merge_and_score.py:deduplicate_practices_in_zip()."""
    return (addr or "").upper().strip()


def normalize_method_b(addr):
    """Enhanced method: expand abbreviations, strip suites, collapse spaces."""
    if not addr:
        return ""
    a = str(addr).upper().strip()
    # Strip suite/unit/apt and everything after
    a = re.sub(r"\b(STE|SUITE|UNIT|APT|#|BLDG|FLOOR|FL)\s*\.?\s*\S*.*$", "", a)
    # Remove periods, commas
    a = a.replace(".", "").replace(",", "")
    # Expand abbreviations
    for pat, repl in ADDR_ABBREVS.items():
        a = re.sub(pat, repl, a)
    # Collapse whitespace
    a = re.sub(r"\s+", " ", a).strip()
    return a


def compare_for_zip(session, zip_code):
    """Compare grouping results for a single ZIP."""
    from sqlalchemy import text

    rows = session.execute(
        text("SELECT npi, address, city FROM practices WHERE zip = :z"),
        {"z": zip_code},
    ).fetchall()

    groups_a = defaultdict(list)
    groups_b = defaultdict(list)

    for npi, address, city in rows:
        city_upper = (city or "").upper().strip()
        key_a = (normalize_method_a(address), city_upper)
        key_b = (normalize_method_b(address), city_upper)
        groups_a[key_a].append(npi)
        groups_b[key_b].append(npi)

    count_a = len(groups_a)
    count_b = len(groups_b)
    diff = count_a - count_b
    diff_pct = (diff / count_a * 100) if count_a > 0 else 0.0

    # Find examples where groups differ
    examples = []
    for key_a, npis_a in groups_a.items():
        key_b = (normalize_method_b(key_a[0].upper()), key_a[1])
        # Check if this key_a maps to a different key_b that merges with another group
        addr_raw = key_a[0]
        addr_enhanced = normalize_method_b(addr_raw)
        if addr_raw != addr_enhanced:
            examples.append({
                "method_a": addr_raw,
                "method_b": addr_enhanced,
                "npis": len(npis_a),
            })

    return {
        "zip": zip_code,
        "total_practices": len(rows),
        "method_a_groups": count_a,
        "method_b_groups": count_b,
        "diff": diff,
        "diff_pct": diff_pct,
        "examples": examples[:5],
    }


def run():
    """Run the address normalization assessment."""
    init_db()
    session = get_session()

    results = []
    lines = []
    lines.append("=" * 70)
    lines.append("ADDRESS NORMALIZATION ASSESSMENT — Phase 2.1")
    lines.append("=" * 70)
    lines.append("")
    lines.append("Method A (current): address.upper().strip()")
    lines.append("Method B (enhanced): expand abbreviations, strip suites, collapse spaces")
    lines.append("")

    total_diff_pct = 0.0

    for zip_code in TEST_ZIPS:
        result = compare_for_zip(session, zip_code)
        results.append(result)
        total_diff_pct += result["diff_pct"]

        line = (f"ZIP {result['zip']}: "
                f"Method A = {result['method_a_groups']} locations, "
                f"Method B = {result['method_b_groups']} locations, "
                f"diff = {result['diff']} ({result['diff_pct']:.1f}%)")
        lines.append(line)
        print(line)

        if result["examples"]:
            for ex in result["examples"][:3]:
                detail = f"    Example: '{ex['method_a']}' → '{ex['method_b']}' ({ex['npis']} NPIs)"
                lines.append(detail)
                print(detail)

    avg_diff = total_diff_pct / len(TEST_ZIPS)
    lines.append("")
    lines.append(f"Average difference: {avg_diff:.1f}%")

    if avg_diff > 5.0:
        decision = ("DECISION: Average difference exceeds 5%. Enhanced normalization "
                     "should be ported into merge_and_score.py.")
    else:
        decision = ("DECISION: Average difference is within 5%. Current normalization "
                     "is acceptable. Proceeding with existing method.")

    lines.append(decision)
    lines.append("")
    print(f"\n{decision}")

    # Write output file
    output_path = os.path.expanduser("~/dental-pe-tracker/data/address_normalization_assessment.txt")
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nResults saved to {output_path}")

    session.close()
    return avg_diff


if __name__ == "__main__":
    run()
