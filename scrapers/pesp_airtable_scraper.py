"""
PESP Airtable Ingester — handles post-mid-2025 PESP deals that live in
Airtable iframes instead of HTML prose.

Background
----------
Starting around mid-2025, PESP stopped listing deals in the HTML body of its
monthly roundup posts and instead embeds an Airtable iframe. ``pesp_scraper.py``
detects this case (``_classify_page_structure`` returns ``summary_only`` when
an ``airtable.com`` iframe is present) and intentionally produces zero rows,
which is why those months are listed in ``PESP_EXPECTED_EMPTY_MONTHS``.

Why this matters: PESP is the only source that names the **PE sponsor** on
~70% of its deals. GDN names the platform but only names the sponsor on ~2%
of rows. So losing PESP for the Airtable era leaves a real PE-attribution
gap (verified 2026-04-25: GDN covers volume but not sponsorship).

Approach
--------
Airtable's public ``readSharedViewData`` and ``downloadCsv`` endpoints both
redirect to ``/login`` without an authenticated session — so a pure ``requests``
based path isn't viable. Two supported modes:

  --csv <path>      Ingest a CSV that you exported manually from the Airtable
                    embed (every Airtable shared view has a ⋯ menu → "Download
                    CSV"). Five minutes per month. ToS-clean. Today.

  --auto            (Stub) Render the Airtable embed via Playwright, extract
                    the rendered table, ingest. Requires ``pip install
                    playwright && playwright install chromium``. NOT YET
                    IMPLEMENTED — the function logs a clear error explaining
                    why and points at ``--csv``. Implementing the auto path
                    is ~150 LOC of Playwright + DOM extraction; it's a 1-2
                    hour follow-up.

Either mode writes through ``insert_deal()`` (the same dedup helper the
HTML scraper uses), so duplicates against existing GDN/PESP-prose rows
are handled by the per-row savepoint logic in ``sync_to_supabase.py``.

Iframe URL registry
-------------------
``IFRAME_URL_REGISTRY`` maps the PESP post slug → its Airtable embed URL.
Seeded with the 3 distinct shared views observed in 2024-08 .. 2026-03
posts. New months: append the new (slug, embed_url) pair as PESP publishes.

Column mapping
--------------
Default column names match the headers PESP Airtable uses as of 2026-04-25:
``Date``, ``Acquirer``, ``Target``, ``State``, ``Sector``, ``Sub-sector``,
``Investor``, ``Source``. If PESP renames columns, override with
``--col-date <name>`` etc., or edit ``DEFAULT_COL_MAP`` below.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import date, datetime
from pathlib import Path

from scrapers.database import Deal, get_session, init_db, insert_deal, normalize_punctuation
from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_complete, log_scrape_error, log_scrape_start

log = get_logger("pesp_airtable_scraper")
SOURCE_NAME = "pesp_airtable"

# ── Iframe URL registry ─────────────────────────────────────────────────────
# slug → Airtable embed URL. Discovered by fetching the PESP post and grepping
# for `airtable.com/embed/`. As PESP publishes new months, append below.
IFRAME_URL_REGISTRY: dict[str, str] = {
    # 14 Airtable views verified live 2026-04-25 by fetching each PESP post
    # with Chrome UA and extracting `<iframe src="https://airtable.com/embed/...">`.
    # All views share the same base appbXEB4PCgy1jWem; each month gets its own
    # `sh...` view ID (PESP creates a new shared view per month rather than
    # updating one in-place — earlier note saying otherwise was wrong).
    #
    # september-2025, december-2025, february-2026, march-2026 returned 404
    # (post not yet published / no archived snapshot) and are intentionally
    # absent. Re-probe with Chrome UA when those months publish.
    "private-equity-health-care-acquisitions-august-2024": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shr5CuUhCEMUYreno?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-september-2024": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrbnlBZdDEx1ShZF?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-october-2024": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shr47fUdc51ak7bJ9?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-january-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrRZKgxTYKLvykjv?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-february-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrqSgYvVxhVQKjL1?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-march-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrU1PEgnRqO4P0jC?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-april-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrh1Lrali22y13gl?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-may-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shr2LFc0lD9YirVXY?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-june-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrXwOQ7OU513t3EU?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-july-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrdtcx3ZR4TCCJhv?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-august-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrqAIQfY5eDTiewv?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-october-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrycSTfuHKGV3YFR?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-november-2025": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrT3oqVUFeAXKHhC?viewControls=on"
    ),
    "private-equity-health-care-acquisitions-january-2026": (
        "https://airtable.com/embed/appbXEB4PCgy1jWem/shrpTfM6IjU3nbo39?viewControls=on"
    ),
}

# ── Column mapping ──────────────────────────────────────────────────────────
DEFAULT_COL_MAP = {
    "date": "Date",
    "acquirer": "Acquirer",         # → platform_company
    "target": "Target",              # → target_name
    "state": "State",                # → target_state
    "sector": "Sector",              # → specialty (filter dental/oral surgery only)
    "sub_sector": "Sub-sector",
    "investor": "Investor",          # → pe_sponsor
    "url": "Source",                 # → source_url
}

# Sectors PESP uses that map to dental scope
DENTAL_SECTORS = {"dental", "dentistry", "oral surgery", "orthodontics", "endodontics", "periodontics"}


# ── CSV ingest ──────────────────────────────────────────────────────────────


def _parse_csv_date(raw: str) -> date | None:
    """Airtable typically exports dates as ``YYYY-MM-DD``, but accommodate
    common variants (``M/D/YYYY``, ``YYYY-MM-DDT...``)."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    log.warning("Unparseable date string: %r", raw)
    return None


def _is_dental(row: dict, col_map: dict) -> bool:
    """Return True if the row's sector or sub-sector mentions dental keywords."""
    for key in ("sector", "sub_sector"):
        col = col_map[key]
        val = (row.get(col) or "").strip().lower()
        if any(kw in val for kw in DENTAL_SECTORS):
            return True
    # Fall back: if the target/acquirer name mentions dental, count it
    for key in ("target", "acquirer"):
        col = col_map[key]
        val = (row.get(col) or "").strip().lower()
        if any(kw in val for kw in ("dental", "dso", "orthodont", "endodont", "periodont", "oral surgery")):
            return True
    return False


def ingest_csv(path: Path, col_map: dict, dry_run: bool = False) -> tuple[int, int]:
    """Parse an Airtable-exported CSV and upsert dental rows into ``deals``.

    Returns ``(rows_processed, rows_inserted)``.
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    if not dry_run:
        init_db()
    session = get_session() if not dry_run else None

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                log.error("CSV has no header row: %s", path)
                return 0, 0
            log.info("CSV columns: %s", reader.fieldnames)
            missing = [v for v in col_map.values() if v not in reader.fieldnames]
            if missing:
                log.warning(
                    "Expected columns missing: %s. Override with --col-* flags or edit DEFAULT_COL_MAP.",
                    missing,
                )

            processed = 0
            inserted = 0
            for row in reader:
                processed += 1
                if not _is_dental(row, col_map):
                    continue
                deal_date = _parse_csv_date(row.get(col_map["date"], ""))
                if deal_date is None:
                    continue
                platform = normalize_punctuation((row.get(col_map["acquirer"]) or "").strip()) or None
                target = normalize_punctuation((row.get(col_map["target"]) or "").strip()) or None
                pe_sponsor = normalize_punctuation((row.get(col_map["investor"]) or "").strip()) or None
                state = (row.get(col_map["state"]) or "").strip().upper()[:2] or None
                source_url = (row.get(col_map["url"]) or "").strip() or None

                # Skip rows that have no actionable identity (no target AND no platform)
                if not target and not platform:
                    continue

                if dry_run:
                    log.info(
                        "[dry-run] %s | platform=%s | target=%s | sponsor=%s | state=%s",
                        deal_date.isoformat(), platform, target, pe_sponsor, state,
                    )
                    inserted += 1
                    continue

                ok = insert_deal(
                    session,
                    deal_date=deal_date,
                    platform_company=platform,
                    target_name=target,
                    pe_sponsor=pe_sponsor,
                    target_state=state,
                    source=SOURCE_NAME,
                    source_url=source_url,
                )
                if ok:
                    inserted += 1

            if not dry_run:
                session.commit()

        return processed, inserted
    finally:
        if session is not None:
            session.close()


# ── Auto mode (Playwright) ──────────────────────────────────────────────────


def auto_ingest(slug: str | None, dry_run: bool = False) -> tuple[int, int]:  # noqa: ARG001
    """Render a PESP Airtable iframe via Playwright and ingest the rendered table.

    NOT IMPLEMENTED — see module docstring. Implementation roadmap:

    1. ``pip install playwright && playwright install chromium`` (or wrap the
       import in a try/except and degrade gracefully).
    2. For each (slug, iframe_url) in ``IFRAME_URL_REGISTRY`` (or just the one
       passed via --slug): launch a chromium page, navigate to ``iframe_url``,
       wait for ``[data-testid="grid-cell"]`` (or whatever Airtable's current
       grid selector is), scroll/page through rows.
    3. Extract rows by reading column-cell aria labels — Airtable's DOM
       changes often, so prefer aria over class names.
    4. Pass each row through ``ingest_csv``-style normalization (re-use the
       same column map and ``_is_dental`` filter).
    5. Cache iframe DOM dumps under ``data/pesp_airtable_cache/<slug>.html``
       so re-runs don't hammer Airtable and so the parser is testable
       offline against fixtures.

    Estimated effort: 150 LOC + a small fixture set + 2-3 hours of debugging
    against Airtable's selectors.
    """
    msg = (
        "Auto-mode (Playwright) is not yet implemented. Use --csv <path> "
        "after manually exporting the Airtable shared view as CSV. "
        "See module docstring for the implementation roadmap."
    )
    log.error(msg)
    raise NotImplementedError(msg)


# ── Entrypoint ──────────────────────────────────────────────────────────────


def run(args: argparse.Namespace) -> None:
    """Top-level orchestrator. Wraps the chosen mode in the standard
    ``log_scrape_start/complete/error`` pipeline-logger envelope."""
    start = time.time()
    log_scrape_start(SOURCE_NAME, summary=f"PESP Airtable ingester ({args.mode})")

    try:
        if args.mode == "csv":
            col_map = dict(DEFAULT_COL_MAP)
            for key in col_map:
                override = getattr(args, f"col_{key}", None)
                if override:
                    col_map[key] = override
            processed, inserted = ingest_csv(Path(args.csv_path), col_map, dry_run=args.dry_run)
        elif args.mode == "auto":
            processed, inserted = auto_ingest(args.slug, dry_run=args.dry_run)
        else:  # pragma: no cover
            raise ValueError(f"Unknown mode: {args.mode}")
        log_scrape_complete(
            SOURCE_NAME,
            start_time=start,
            summary=f"Processed {processed} CSV rows, inserted {inserted} dental deals",
            details={"mode": args.mode, "processed": processed, "inserted": inserted},
        )
    except NotImplementedError as e:
        log_scrape_error(SOURCE_NAME, e, start)
        sys.exit(2)
    except Exception as e:  # noqa: BLE001
        log.exception("PESP Airtable ingest failed")
        log_scrape_error(SOURCE_NAME, e, start)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)

    csv_p = sub.add_parser("csv", help="Ingest a manually-exported Airtable CSV")
    csv_p.add_argument("csv_path", type=str, help="Path to CSV file")
    csv_p.add_argument("--dry-run", action="store_true", help="Parse + log only; no DB writes")
    for key, default in DEFAULT_COL_MAP.items():
        csv_p.add_argument(f"--col-{key}", type=str, default=None, help=f"Override column for {key} (default: {default!r})")

    auto_p = sub.add_parser("auto", help="(stub) Playwright-rendered ingestion")
    auto_p.add_argument("--slug", type=str, default=None, help="Specific PESP post slug to scrape (default: all in registry)")
    auto_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
