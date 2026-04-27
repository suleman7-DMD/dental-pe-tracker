#!/usr/bin/env python3
"""
One-shot backfill: re-extract target_name for deals where it's NULL.

Runs the (now-fixed) extract_target() from gdn_scraper.py over each deal's
raw_text. Only updates rows where a non-empty target is successfully extracted.
Idempotent — skips deals that already have a target_name.

Usage:
    python3 scrapers/backfill_deal_targets.py [--dry-run]
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from scrapers.database import get_session
from scrapers.gdn_scraper import extract_target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = parser.parse_args()

    session = get_session()
    try:
        rows = session.execute(text(
            "SELECT id, raw_text, platform_company, source FROM deals "
            "WHERE target_name IS NULL AND raw_text IS NOT NULL"
        )).fetchall()

        print(f"Found {len(rows)} deals with NULL target_name and non-NULL raw_text")

        updated = 0
        skipped = 0
        dupes = 0
        by_source = {}

        for row in rows:
            deal_id, raw_text, platform, source = row
            target = extract_target(raw_text, platform)

            if not target or len(target) < 3 or len(target) > 80:
                skipped += 1
                continue

            low = target.lower()
            junk_phrases = [
                "the company", "an entity", "the organization", "the 20",
                "practices an entity", "pennsylvania", "virginia",
                "california", "texas", "florida", "georgia", "ohio",
                "indiana", "colorado",
            ]
            if any(low.startswith(j) for j in junk_phrases):
                skipped += 1
                continue
            if low.startswith("ga.") or low.startswith("tx.") or low.startswith("fl."):
                skipped += 1
                continue
            junk_contains = [" also", " winner", " award"]
            if any(j in low for j in junk_contains):
                skipped += 1
                continue
            if platform and low == platform.lower():
                skipped += 1
                continue
            if platform and low.startswith(platform.lower() + " "):
                skipped += 1
                continue
            state_frag = len(target) <= 6 and not any(c.islower() for c in target)
            if state_frag:
                skipped += 1
                continue

            by_source[source] = by_source.get(source, 0) + 1

            if args.dry_run:
                print(f"  [{source}] id={deal_id}: '{target}' (platform={platform})")
                updated += 1
            else:
                try:
                    nested = session.begin_nested()
                    session.execute(text(
                        "UPDATE deals SET target_name = :target, updated_at = CURRENT_TIMESTAMP "
                        "WHERE id = :id AND target_name IS NULL"
                    ), {"target": target, "id": deal_id})
                    nested.commit()
                    updated += 1
                except IntegrityError:
                    dupes += 1
                    continue

        if not args.dry_run:
            session.commit()

        print(f"\n{'Would update' if args.dry_run else 'Updated'}: {updated}")
        print(f"Skipped (no match or too short/long): {skipped}")
        print(f"Skipped (unique constraint collision): {dupes}")
        print(f"By source: {by_source}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
