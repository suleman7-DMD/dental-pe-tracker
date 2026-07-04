#!/usr/bin/env python3
"""Delete low-quality deal rows directly from Supabase.

The normal deals sync is incremental and does not propagate SQLite deletions.
This script applies the same quality policy to the live Supabase deals table,
with an explicit max-delete guard and an evidence JSON report.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from scrapers.cleanup_low_quality_deals import BAD_PLATFORM_PLACEHOLDERS, _blank
from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_complete, log_scrape_start
from scrapers.sync_to_supabase import _get_pg_engine, _set_statement_timeout


EVIDENCE_PATH = ROOT / "data" / "dso_research" / "deal_quality_live_cleanup_20260704.json"

log = get_logger("reconcile_live_deal_quality")


def _jsonable(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _row_reasons(row: dict, *, strict_targets: bool) -> list[str]:
    reasons: list[str] = []
    platform = (row.get("platform_company") or "").strip().lower()
    source = (row.get("source") or "").strip().lower()

    if _blank(row.get("source_url")):
        reasons.append("missing_source_url")

    if platform in BAD_PLATFORM_PLACEHOLDERS:
        reasons.append("bad_platform_placeholder")

    if source == "pitchbook" and _blank(row.get("source_url")) and _blank(row.get("target_name")):
        reasons.append("pitchbook_no_source_no_target")

    if strict_targets and _blank(row.get("target_name")):
        reasons.append("missing_target_name")

    return reasons


def _summarize(conn) -> dict:
    return {
        "total_deals": conn.execute(text("SELECT COUNT(*) FROM deals")).scalar(),
        "by_source": [
            {key: _jsonable(value) for key, value in dict(row._mapping).items()}
            for row in conn.execute(
                text(
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
            )
        ],
    }


def collect_candidates(conn, *, strict_targets: bool) -> tuple[list[dict], collections.Counter]:
    rows = [
        dict(row._mapping)
        for row in conn.execute(
            text(
                """
                SELECT
                    id, deal_date, platform_company, pe_sponsor, target_name,
                    target_city, target_state, deal_type, source, source_url, notes
                FROM deals
                ORDER BY deal_date DESC NULLS LAST, id ASC
                """
            )
        )
    ]

    candidates: list[dict] = []
    reason_counts: collections.Counter = collections.Counter()
    for row in rows:
        reasons = _row_reasons(row, strict_targets=strict_targets)
        if not reasons:
            continue
        reason_counts.update(reasons)
        item = dict(row)
        if item.get("deal_date") is not None:
            item["deal_date"] = item["deal_date"].isoformat()
        item["delete_reasons"] = reasons
        candidates.append(item)

    return candidates, reason_counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default=str(EVIDENCE_PATH), help="JSON evidence output path")
    parser.add_argument("--apply", action="store_true", help="Actually delete rows. Omit for dry-run.")
    parser.add_argument(
        "--strict-targets",
        action="store_true",
        help="Also delete live rows whose target_name is blank.",
    )
    parser.add_argument(
        "--max-delete",
        type=int,
        default=3000,
        help="Safety guard: refuse to delete more than this many rows.",
    )
    args = parser.parse_args()

    start_time = log_scrape_start("reconcile_live_deal_quality")
    engine = _get_pg_engine()
    evidence_path = Path(args.evidence)

    with engine.connect() as conn:
        _set_statement_timeout(conn)
        before = _summarize(conn)
        candidates, reason_counts = collect_candidates(conn, strict_targets=args.strict_targets)

    report = {
        "_meta": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "script": "scrapers/reconcile_live_deal_quality.py",
            "mode": "apply" if args.apply else "dry_run",
            "strict_targets": args.strict_targets,
            "max_delete": args.max_delete,
            "policy": (
                "Apply live Supabase deal-quality cleanup. Rows with missing source URLs, "
                "placeholder platforms, source-less target-less PitchBook imports, and, "
                "when strict_targets=true, blank target_name are removed from the primary "
                "deal-feed table."
            ),
        },
        "before": before,
        "candidate_count": len(candidates),
        "reason_counts": dict(reason_counts),
        "candidate_ids": [row["id"] for row in candidates],
        "candidate_sample": candidates[:75],
    }

    if len(candidates) > args.max_delete:
        report["deleted_count"] = 0
        report["refused"] = f"candidate_count {len(candidates)} exceeds max_delete {args.max_delete}"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        raise SystemExit(report["refused"])

    if args.apply and candidates:
        ids = [row["id"] for row in candidates]
        with engine.begin() as conn:
            _set_statement_timeout(conn, local=True)
            result = conn.execute(text("DELETE FROM deals WHERE id = ANY(:ids)"), {"ids": ids})
            report["deleted_count"] = result.rowcount or 0
            report["after"] = _summarize(conn)
    else:
        report["deleted_count"] = 0
        report["after"] = before

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    log.info(
        "%s: candidates=%d deleted=%d reasons=%s evidence=%s",
        "APPLIED" if args.apply else "DRY-RUN",
        len(candidates),
        report["deleted_count"],
        dict(reason_counts),
        evidence_path,
    )
    log_scrape_complete(
        "reconcile_live_deal_quality",
        start_time,
        new_records=0,
        updated_records=0,
        summary=f"live deal cleanup {'applied' if args.apply else 'dry-run'}: {len(candidates)} candidates",
        extra={
            "candidates": len(candidates),
            "deleted": report["deleted_count"],
            "applied": args.apply,
            "evidence": str(evidence_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
