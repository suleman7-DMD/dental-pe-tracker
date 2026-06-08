#!/usr/bin/env python3
"""Surgical backfill of Data Axle corporate-signal columns into `practices`.

The Data Axle importer historically persisted only ~25 of 383 columns, discarding
the corporate-ownership signals (secondary EINs, back-office mailing address,
legal entity name, corporate-tree subsidiary IUSA, parent-scale headcount/sales,
and the executive/officer roster). Those columns are already on disk in
data/data-axle/processed/*.csv (+ data/data-axle/*.csv) — every file carries the
full 383-column header. This script RE-PARSES the existing raw exports (it does
NOT re-download) and populates the new da_* columns on existing practices.

Design (mirrors nppes_downloader.backfill_ownership_cols — additive, re-runnable):
  * NO synthetic rows, NO practice_changes churn, NO entity_classification /
    ownership_status / buyability writes. ONLY the da_* columns (+ ein/
    parent_company when currently NULL) are touched. Floor-safe by construction.
  * Signals are keyed by normalized (address, zip5) and by normalized phone, then
    attached to EVERY co-located NPI at the matched address so location-level
    detection sees the signal regardless of which NPI a detector keys on.
  * Idempotent: re-running overwrites da_* with the same merged values.

Usage:
    python3 -m scrapers.backfill_data_axle_corporate_signals            # apply
    python3 -m scrapers.backfill_data_axle_corporate_signals --dry-run  # report only
"""

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

import pandas as pd
from sqlalchemy import text

from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete
from scrapers.database import get_engine
from scrapers.data_axle_importer import (
    detect_columns,
    detect_corp_signal_columns,
    extract_corp_signals,
    merge_corp_signals,
    normalize_address,
    normalize_phone,
    normalize_zip,
    _da_clean,
    _da_ein,
)

log = get_logger("backfill_da_corp")

RAW_GLOBS = [
    "data/data-axle/processed/*.csv",
    "data/data-axle/*.csv",
]

# da_* columns we write, plus the two legacy corporate columns we fill-when-NULL.
DA_COLS = [
    "da_ein2", "da_ein3", "da_mailing_address", "da_mailing_city",
    "da_mailing_state", "da_mailing_zip", "da_legal_name", "da_subsidiary_iusa",
    "da_corporate_employees", "da_corporate_sales", "da_officers",
]


def _loc_key(addr, zip_code):
    na = normalize_address(addr)
    z = normalize_zip(zip_code)
    if not na or not z:
        return None
    return f"{na}|{z[:5]}"


def build_signal_maps():
    """Parse all on-disk raw files into location- and phone-keyed signal maps."""
    files = []
    for g in RAW_GLOBS:
        files.extend(sorted(glob.glob(g)))
    files = sorted(set(files))
    log.info("Parsing %d raw Data Axle files", len(files))

    loc_map = {}    # loc_key -> merged corp signals (+ ein1/parent)
    phone_map = {}  # phone10 -> merged corp signals
    stats = {"files": len(files), "rows": 0, "rows_with_signal": 0}

    for f in files:
        try:
            df = pd.read_csv(f, dtype=str, low_memory=False)
        except Exception as e:
            log.warning("skip %s: %s", os.path.basename(f), e)
            continue
        cols = list(df.columns)
        mapping, _ = detect_columns(cols)          # standard fields (addr/zip/phone/ein/parent)
        corp_colmap = detect_corp_signal_columns(cols)
        addr_col = mapping.get("address")
        zip_col = mapping.get("zip")
        phone_col = mapping.get("phone")
        ein_col = mapping.get("ein")
        parent_col = mapping.get("parent_company")
        if not addr_col or not zip_col:
            log.warning("skip %s: no address/zip column", os.path.basename(f))
            continue

        for _, row in df.iterrows():
            stats["rows"] += 1
            sig = extract_corp_signals(row, corp_colmap)
            # Augment with EIN 1 + parent_company (fill-when-NULL on practices)
            sig["ein1"] = _da_ein(row.get(ein_col)) if ein_col else None
            sig["parent_company"] = _da_clean(row.get(parent_col)) if parent_col else None
            # Does this row carry ANY corporate signal worth storing?
            if not any(v for k, v in sig.items()):
                continue
            stats["rows_with_signal"] += 1

            lk = _loc_key(row.get(addr_col), row.get(zip_col))
            if lk:
                if lk in loc_map:
                    merge_corp_signals(loc_map[lk], sig)
                    for k in ("ein1", "parent_company"):
                        if sig.get(k) and not loc_map[lk].get(k):
                            loc_map[lk][k] = sig[k]
                else:
                    loc_map[lk] = dict(sig)
            ph = normalize_phone(row.get(phone_col)) if phone_col else None
            if ph:
                if ph in phone_map:
                    merge_corp_signals(phone_map[ph], sig)
                    for k in ("ein1", "parent_company"):
                        if sig.get(k) and not phone_map[ph].get(k):
                            phone_map[ph][k] = sig[k]
                else:
                    phone_map[ph] = dict(sig)

    log.info("Built maps: %d locations, %d phones (%d/%d raw rows carried a signal)",
             len(loc_map), len(phone_map), stats["rows_with_signal"], stats["rows"])
    return loc_map, phone_map, stats


def apply_backfill(dry_run=False):
    loc_map, phone_map, parse_stats = build_signal_maps()
    engine = get_engine()

    touched = 0
    per_field = defaultdict(int)
    matched_by = {"location": 0, "phone": 0}

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT npi, address, zip, phone, ein, parent_company FROM practices"
        )).fetchall()
        log.info("Scanning %d practices for matches", len(rows))

        for npi, addr, zip_code, phone, cur_ein, cur_parent in rows:
            lk = _loc_key(addr, zip_code)
            sig = loc_map.get(lk) if lk else None
            via = "location"
            if not sig:
                ph = normalize_phone(phone) if phone else None
                sig = phone_map.get(ph) if ph else None
                via = "phone"
            if not sig:
                continue

            updates = {}
            for col in DA_COLS:
                v = sig.get(col)
                if v is not None:
                    updates[col] = v
                    per_field[col] += 1
            # Fill-when-NULL for the two legacy corporate columns
            if sig.get("ein1") and not cur_ein:
                updates["ein"] = sig["ein1"]
                per_field["ein(filled)"] += 1
            if sig.get("parent_company") and not cur_parent:
                updates["parent_company"] = sig["parent_company"]
                per_field["parent_company(filled)"] += 1

            if not updates:
                continue
            matched_by[via] += 1
            touched += 1
            if not dry_run:
                set_clause = ", ".join(f"{k} = :{k}" for k in updates)
                updates["npi"] = npi
                conn.execute(text(f"UPDATE practices SET {set_clause} WHERE npi = :npi"),
                             updates)

        if not dry_run:
            conn.commit()

    log.info("=" * 60)
    log.info("Backfill %s: %d practices touched (location=%d, phone=%d)",
             "DRY-RUN" if dry_run else "APPLIED", touched,
             matched_by["location"], matched_by["phone"])
    for col in DA_COLS + ["ein(filled)", "parent_company(filled)"]:
        if per_field.get(col):
            log.info("  %-28s %6d", col, per_field[col])
    return {
        "parse": parse_stats,
        "touched": touched,
        "matched_by": matched_by,
        "per_field": dict(per_field),
        "dry_run": dry_run,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    args = ap.parse_args()

    start_time = log_scrape_start("backfill_da_corp")
    try:
        result = apply_backfill(dry_run=args.dry_run)
        log_scrape_complete(
            "backfill_da_corp", start_time,
            updated_records=result["touched"],
            summary=f"{'DRY-RUN ' if result['dry_run'] else ''}"
                    f"touched={result['touched']} "
                    f"loc={result['matched_by']['location']} "
                    f"phone={result['matched_by']['phone']}",
            extra=result,
        )
        print(json.dumps(result, indent=2))
    except Exception as e:
        log.exception("backfill failed")
        log_scrape_complete("backfill_da_corp", start_time, summary=f"FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
