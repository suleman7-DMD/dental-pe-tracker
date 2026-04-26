"""
PESP CSV importer — thin alias for ``pesp_airtable_scraper.py`` CSV mode.

F09 (2026-04-26) ship-able fix for the Aug-2024 Airtable structural block.

Background
----------
PESP's monthly roundup posts shifted in mid-2024 from prose-with-deals to
``<iframe src="https://airtable.com/embed/...">`` widgets that hide the
deal table behind Airtable's auth wall. We confirmed (2026-04-26) that
the public ``readSharedViewData`` and ``/csv`` endpoints both redirect
to ``/login`` — there is no anonymous JSON path.

Workflow
--------
For each unscraped PESP post:

1. Open the post in a browser.
2. Click into the embedded Airtable view, then ⋯ → "Download CSV".
3. ``python3 scrapers/pesp_csv_importer.py <path-to.csv>`` — dental rows
   are filtered, deduped, and inserted via the same ``insert_deal()``
   gate as the HTML scraper.

The 14 known iframe URLs (Aug-2024 through Jan-2026) are catalogued in
``pesp_airtable_scraper.IFRAME_URL_REGISTRY``; append new months as PESP
publishes them.

Rationale for keeping this file
-------------------------------
F09 in ``IMPLEMENTATION_PLAN_2026_04_26.md`` specifies the file name
``pesp_csv_importer.py``. ``pesp_airtable_scraper.py`` predates that
spec but already implements both the CSV path (``--csv``) and a
Playwright auto-mode stub (``--auto``). Rather than rename and break
in-flight references, this file forwards CSV-mode invocations to the
existing ingester so both the spec'd name and the umbrella name work.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scrapers.pesp_airtable_scraper import DEFAULT_COL_MAP, run as airtable_run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("csv_path", type=str, help="Path to Airtable-exported CSV")
    parser.add_argument("--dry-run", action="store_true", help="Parse + log only; no DB writes")
    for key, default in DEFAULT_COL_MAP.items():
        parser.add_argument(
            f"--col-{key}",
            type=str,
            default=None,
            help=f"Override column for {key} (default: {default!r})",
        )
    args = parser.parse_args()

    if not Path(args.csv_path).exists():
        print(f"ERROR: CSV not found: {args.csv_path}", file=sys.stderr)
        sys.exit(1)

    forwarded = argparse.Namespace(
        mode="csv",
        csv_path=args.csv_path,
        dry_run=args.dry_run,
    )
    for key in DEFAULT_COL_MAP:
        setattr(forwarded, f"col_{key}", getattr(args, f"col_{key}", None))
    airtable_run(forwarded)


if __name__ == "__main__":
    main()
