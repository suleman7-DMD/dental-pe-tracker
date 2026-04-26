"""
Backfill practices.entity_classification from practice_locations.

Why this exists: `reclassify_locations.py` writes location-level classifications
to `practice_locations`, but the front-end Launchpad and Warroom target list
read NPI-level `practices.entity_classification` directly. Without backfilling,
each page shows a different number for the same ZIP.

Strategy:
  1. Read every row of practice_locations (5,732 rows).
  2. For each location, expand primary_npi + org_npi + provider_npis JSON
     into the full set of NPIs at that address.
  3. Build a flat dict NPI -> (entity_classification, classification_reasoning).
  4. Bulk UPDATE practices in 1000-NPI batches.

Coverage: ~92% of watched-ZIP NPIs are in some provider_npis array. The 8%
gap is NPIs whose addresses didn't normalize cleanly into a location row;
those keep their existing NPI-level classification.

Idempotent — safe to re-run.

Usage: python3 scrapers/backfill_practices_classification.py [--dry-run]
"""

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.database import get_session, Practice, PracticeLocation
from scrapers.logger_config import get_logger
from sqlalchemy import update

log = get_logger("backfill_practices_classification")
DRY_RUN = "--dry-run" in sys.argv


def build_npi_map(session):
    """Read all practice_locations rows, build NPI -> (classification, reasoning)."""
    locs = session.query(PracticeLocation).all()
    log.info("Read %d practice_locations rows", len(locs))

    npi_map = {}
    npis_seen = 0
    for loc in locs:
        ec = loc.entity_classification
        reason = loc.classification_reasoning
        if not ec:
            continue
        npis_for_loc = set()
        if loc.primary_npi:
            npis_for_loc.add(loc.primary_npi)
        if loc.org_npi:
            npis_for_loc.add(loc.org_npi)
        if loc.provider_npis:
            try:
                arr = json.loads(loc.provider_npis)
                for n in arr:
                    if n:
                        npis_for_loc.add(str(n))
            except (json.JSONDecodeError, TypeError):
                pass
        for npi in npis_for_loc:
            npi_map[npi] = (ec, reason)
            npis_seen += 1

    log.info("Mapped %d NPIs (%d unique) to %d distinct classifications",
             npis_seen, len(npi_map), len(set(v[0] for v in npi_map.values())))
    return npi_map


def diff_existing(session, npi_map):
    """Compute how many NPIs would change vs how many are already correct."""
    npis = list(npi_map.keys())
    rows = []
    for i in range(0, len(npis), 1000):
        chunk = npis[i:i + 1000]
        rows.extend(
            session.query(Practice.npi, Practice.entity_classification)
            .filter(Practice.npi.in_(chunk))
            .all()
        )

    existing = {r[0]: r[1] for r in rows}
    transitions = Counter()
    unchanged = 0
    not_in_practices = 0
    for npi, (new_ec, _) in npi_map.items():
        if npi not in existing:
            not_in_practices += 1
            continue
        old = existing[npi]
        if old == new_ec:
            unchanged += 1
        else:
            transitions[(old or "NULL", new_ec)] += 1

    log.info("=== Diff summary ===")
    log.info("  Unchanged: %d", unchanged)
    log.info("  Will change: %d", sum(transitions.values()))
    log.info("  Not in practices table: %d", not_in_practices)
    log.info("  Top transitions:")
    for (old, new), n in transitions.most_common(15):
        log.info("    %-25s -> %-25s %d", old, new, n)
    return transitions


def apply_updates(session, npi_map):
    """Apply UPDATEs in batches.

    Skips dso_national -> dso_regional downgrades: an NPI whose name matches
    a known national brand is more authoritative than a location whose
    affiliated_dso is set without a national brand match. Both are
    "corporate" so the rollup count is unaffected.
    """
    npis = list(npi_map.keys())
    existing = {}
    for i in range(0, len(npis), 1000):
        chunk = npis[i:i + 1000]
        rows = (
            session.query(Practice.npi, Practice.entity_classification)
            .filter(Practice.npi.in_(chunk))
            .all()
        )
        for npi, ec in rows:
            existing[npi] = ec

    skipped_preservation = 0
    total_updated = 0
    BATCH = 500
    for i in range(0, len(npis), BATCH):
        chunk_npis = npis[i:i + BATCH]
        groups = {}
        for npi in chunk_npis:
            new_ec, reason = npi_map[npi]
            old_ec = existing.get(npi)
            if old_ec == "dso_national" and new_ec == "dso_regional":
                skipped_preservation += 1
                continue
            key = (new_ec, reason)
            groups.setdefault(key, []).append(npi)
        for (ec, reason), group_npis in groups.items():
            stmt = (
                update(Practice)
                .where(Practice.npi.in_(group_npis))
                .values(
                    entity_classification=ec,
                    classification_reasoning=reason,
                )
            )
            result = session.execute(stmt)
            total_updated += result.rowcount or 0
        session.commit()
        if i % (BATCH * 10) == 0:
            log.info("  Committed %d/%d NPIs (rowcount %d, preserved %d)",
                     i + BATCH, len(npis), total_updated, skipped_preservation)
    log.info("DONE: %d practices rows updated, %d dso_national preserved",
             total_updated, skipped_preservation)
    return total_updated


def main():
    session = get_session()
    try:
        npi_map = build_npi_map(session)
        diff_existing(session, npi_map)

        if DRY_RUN:
            log.info("DRY RUN — no changes applied")
            return

        applied = apply_updates(session, npi_map)
        log.info("=" * 60)
        log.info("BACKFILL COMPLETE: %d practices rows updated", applied)
        log.info("=" * 60)

        # Verify: distribution after
        from sqlalchemy import func, text
        log.info("Practices distribution (watched ZIPs) after backfill:")
        result = session.execute(text(
            "SELECT entity_classification, COUNT(*) AS n "
            "FROM practices "
            "WHERE zip IN (SELECT zip_code FROM watched_zips) "
            "GROUP BY entity_classification "
            "ORDER BY n DESC"
        ))
        for ec, n in result:
            log.info("  %-25s %d", ec or "NULL", n)
    finally:
        session.close()


if __name__ == "__main__":
    main()
