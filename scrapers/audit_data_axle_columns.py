#!/usr/bin/env python3
"""
Audit Data Axle CSV exports for mapped vs. unmapped fields.

Use after downloading new Reference Solutions exports:

    python3 scrapers/audit_data_axle_columns.py
    python3 scrapers/audit_data_axle_columns.py --csv data/data-axle/my_export.csv

The goal is not to import data. It answers: "Did we download rich fields, and
are we actually using them?" High-fill unmapped columns should be reviewed
before discarding the export, especially fields that reveal corporate structure,
mailing divergence, officer/contact roles, branch/HQ status, and web presence.
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from rapidfuzz import process as rfprocess

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.data_axle_importer import FIELD_CANDIDATES  # noqa: E402

RAW_DIR = os.path.expanduser("~/dental-pe-tracker/data/data-axle")
EMPTY_SENTINELS = {
    "",
    "nan",
    "none",
    "null",
    "n/a",
    "na",
    "0",
    "0.0",
    "000000",
    "000000000",
    "$0",
    "$0.00",
}

HIGH_VALUE_TERMS = (
    "iusa", "parent", "subsidiary", "ein", "executive", "contact", "title",
    "officer", "owner", "ownership", "location", "branch", "headquarter",
    "hq", "mailing", "legal", "franchise", "website", "url", "employee",
    "sales", "revenue", "year", "established",
)


def _guess_mapping(column: str):
    best = (None, 0)
    for canonical, variants in FIELD_CANDIDATES.items():
        match = rfprocess.extractOne(column, variants, score_cutoff=82)
        if match and match[1] > best[1]:
            best = (canonical, int(match[1]))
    return best


def _is_high_value(column: str) -> bool:
    lower = column.lower()
    return any(term in lower for term in HIGH_VALUE_TERMS)


def _filled_count(series: pd.Series) -> int:
    """Count meaningful non-empty values, treating common Data Axle zero sentinels as empty."""
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    return int((~normalized.isin(EMPTY_SENTINELS)).sum())


def _default_paths() -> list[str]:
    """Find the Data Axle exports a human is likely to care about.

    The original default only scanned top-level non-combined files, which missed
    the actual March 2026 processed Chicagoland exports. Include top-level CSVs
    and processed combined CSVs, excluding obvious report/debug artifacts.
    """
    root = Path(RAW_DIR)
    paths = list(root.glob("*.csv")) + list((root / "processed").glob("*combined*.csv"))
    cleaned = []
    seen = set()
    for path in sorted(paths):
        name = path.name.lower()
        if name.startswith("detail"):
            continue
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        cleaned.append(resolved)
    return cleaned


def audit_csv(path: str, min_fill_pct: float):
    df = pd.read_csv(path, dtype=str, low_memory=False)
    rows = len(df)
    out = []
    for col in df.columns:
        filled = _filled_count(df[col])
        fill_pct = (100.0 * filled / rows) if rows else 0.0
        mapped, score = _guess_mapping(col)
        out.append({
            "column": col,
            "filled": filled,
            "fill_pct": fill_pct,
            "mapped": mapped,
            "score": score,
            "high_value": _is_high_value(col),
        })

    mapped = [r for r in out if r["mapped"]]
    unmapped = [r for r in out if not r["mapped"]]
    high_value_unmapped = [
        r for r in unmapped
        if r["high_value"] and r["fill_pct"] >= min_fill_pct
    ]

    print(f"\n== {path}")
    print(f"rows={rows} columns={len(out)} mapped={len(mapped)} unmapped={len(unmapped)}")
    print("\nMapped columns:")
    for r in sorted(mapped, key=lambda x: (x["mapped"], -x["fill_pct"], x["column"]))[:120]:
        print(f"  {r['column']:<44} -> {r['mapped']:<24} fill={r['fill_pct']:5.1f}% score={r['score']}")

    if high_value_unmapped:
        print("\nHigh-value unmapped columns to review:")
        for r in sorted(high_value_unmapped, key=lambda x: (-x["fill_pct"], x["column"]))[:80]:
            print(f"  {r['column']:<60} fill={r['fill_pct']:5.1f}%")
    else:
        print("\nHigh-value unmapped columns to review: none above threshold")

    return {
        "rows": rows,
        "columns": len(out),
        "mapped": len(mapped),
        "unmapped": len(unmapped),
        "high_value_unmapped": len(high_value_unmapped),
    }


def main():
    parser = argparse.ArgumentParser(description="Audit Data Axle CSV columns before import")
    parser.add_argument("--csv", action="append", dest="csvs", help="Specific CSV path. May be repeated.")
    parser.add_argument("--min-fill-pct", type=float, default=5.0, help="Minimum fill percent for high-value unmapped report")
    args = parser.parse_args()

    paths = args.csvs or _default_paths()
    if not paths:
        print(f"No Data Axle CSVs found in {RAW_DIR}")
        return

    totals = {"rows": 0, "columns": 0, "mapped": 0, "unmapped": 0, "high_value_unmapped": 0}
    for path in paths:
        summary = audit_csv(path, args.min_fill_pct)
        for k in totals:
            totals[k] += summary[k]

    print("\n== TOTAL")
    print(
        "files={files} rows={rows} columns_seen={columns} mapped={mapped} "
        "unmapped={unmapped} high_value_unmapped={high_value_unmapped}".format(
            files=len(paths),
            **totals,
        )
    )


if __name__ == "__main__":
    main()
