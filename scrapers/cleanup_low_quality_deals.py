#!/usr/bin/env python3
"""Remove structurally unverifiable deal-flow rows.

This is intentionally conservative. It deletes rows that should not be user
visible because the app cannot verify them from a source URL, or because the
parser produced a placeholder platform such as "Unknown". It does not delete
source-backed sparse rows just because target_name is blank; those are lower
fidelity archive rows and should be replaced by better extraction, not wiped
blindly.
"""

from __future__ import annotations

import argparse
import collections
import json
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_complete, log_scrape_start


DB_PATH = ROOT / "data" / "dental_pe_tracker.db"
EVIDENCE_PATH = ROOT / "data" / "dso_research" / "deal_quality_cleanup_20260703.json"
BACKUP_PATH = ROOT / "data" / "backups" / "dental_pe_tracker_pre_deal_quality_cleanup_20260703.db"

BAD_PLATFORM_PLACEHOLDERS = {
    "",
    "unknown",
    "group dentistry now",
    "when group dentistry now",
}

log = get_logger("cleanup_low_quality_deals")


def _blank(value) -> bool:
    return value is None or str(value).strip() == ""


def _row_reasons(row: sqlite3.Row) -> list[str]:
    reasons: list[str] = []
    platform = (row["platform_company"] or "").strip().lower()
    source = (row["source"] or "").strip().lower()

    if _blank(row["source_url"]):
        reasons.append("missing_source_url")

    if platform in BAD_PLATFORM_PLACEHOLDERS:
        reasons.append("bad_platform_placeholder")

    if source == "pitchbook" and _blank(row["source_url"]) and _blank(row["target_name"]):
        reasons.append("pitchbook_no_source_no_target")

    return reasons


def _summarize(conn: sqlite3.Connection) -> dict:
    return {
        "total_deals": conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0],
        "by_source": [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    source,
                    COUNT(*) AS rows,
                    SUM(CASE WHEN target_name IS NULL OR TRIM(target_name) = '' THEN 1 ELSE 0 END) AS blank_target,
                    SUM(CASE WHEN source_url IS NULL OR TRIM(source_url) = '' THEN 1 ELSE 0 END) AS blank_source_url,
                    MAX(deal_date) AS latest_deal_date
                FROM deals
                GROUP BY source
                ORDER BY source
                """
            )
        ],
    }


def collect_candidates(conn: sqlite3.Connection) -> tuple[list[dict], collections.Counter]:
    candidates: list[dict] = []
    reason_counts: collections.Counter = collections.Counter()

    for row in conn.execute(
        """
        SELECT
            id, deal_date, platform_company, pe_sponsor, target_name, target_city,
            target_state, deal_type, source, source_url, notes
        FROM deals
        ORDER BY deal_date DESC, id ASC
        """
    ):
        reasons = _row_reasons(row)
        if not reasons:
            continue
        reason_counts.update(reasons)
        item = dict(row)
        item["delete_reasons"] = reasons
        candidates.append(item)

    return candidates, reason_counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite DB path")
    parser.add_argument("--evidence", default=str(EVIDENCE_PATH), help="JSON evidence output path")
    parser.add_argument("--apply", action="store_true", help="Actually delete rows. Omit for dry-run.")
    parser.add_argument("--no-backup", action="store_true", help="Skip DB backup before --apply")
    args = parser.parse_args()

    db_path = Path(args.db)
    evidence_path = Path(args.evidence)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    start_time = log_scrape_start("cleanup_low_quality_deals")
    before = _summarize(conn)
    candidates, reason_counts = collect_candidates(conn)

    report = {
        "_meta": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "script": "scrapers/cleanup_low_quality_deals.py",
            "mode": "apply" if args.apply else "dry_run",
            "policy": (
                "Delete structurally unverifiable deal-flow rows only: rows with no "
                "source_url, placeholder platforms, or source-less/target-less PitchBook imports."
            ),
        },
        "before": before,
        "candidate_count": len(candidates),
        "reason_counts": dict(reason_counts),
        "candidate_ids": [row["id"] for row in candidates],
        "candidate_sample": candidates[:50],
    }

    if args.apply and candidates:
        if not args.no_backup:
            BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, BACKUP_PATH)
            report["_meta"]["backup_path"] = str(BACKUP_PATH.relative_to(ROOT))

        ids = [row["id"] for row in candidates]
        placeholders = ",".join("?" for _ in ids)
        with conn:
            conn.execute(f"DELETE FROM deals WHERE id IN ({placeholders})", ids)
        report["deleted_count"] = len(ids)
        report["after"] = _summarize(conn)
    else:
        report["deleted_count"] = 0
        report["after"] = before

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    log.info(
        "%s: candidates=%d reasons=%s evidence=%s",
        "APPLIED" if args.apply else "DRY-RUN",
        len(candidates),
        dict(reason_counts),
        evidence_path,
    )
    log_scrape_complete(
        "cleanup_low_quality_deals",
        start_time,
        new_records=0,
        updated_records=0,
        summary=f"deal cleanup {'applied' if args.apply else 'dry-run'}: {len(candidates)} candidates",
        extra={"candidates": len(candidates), "applied": args.apply, "evidence": str(evidence_path)},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
