"""One-off cleanup: delete PESP junk rows created by the old parse_deal.

Context: before the 2026-04-23 hardening, pesp_scraper.parse_deal returned a
row whenever EITHER a platform OR a PE sponsor was matched, so sponsor-only
summary sentences ("Dental Capital Partners continues its roll-up strategy…")
produced platform_company='Unknown' / target_name=NULL rows. 23 such rows are
in SQLite today; this script removes them so the Supabase sync push is clean.

Run locally once, commit the resulting deals delta via the normal sync. The
script is kept in-repo as an audit trail; it is NOT wired into refresh.sh.
"""
from __future__ import annotations

import sys

from sqlalchemy import and_, or_

from scrapers.database import Deal, get_session, init_db
from scrapers.logger_config import get_logger

log = get_logger("cleanup_pesp_junk")


def _junk_filter():
    """Match rows that the new parse_deal would have dropped outright."""
    return and_(
        Deal.source == "pesp",
        Deal.target_name.is_(None),
        or_(
            Deal.platform_company.is_(None),
            Deal.platform_company == "",
            Deal.platform_company == "Unknown",
        ),
    )


def main(dry_run: bool = False) -> int:
    init_db()
    session = get_session()
    try:
        rows = session.query(Deal).filter(_junk_filter()).all()
        if not rows:
            log.info("No PESP junk rows to clean up.")
            return 0

        log.info("Found %d PESP junk rows to delete:", len(rows))
        for r in rows:
            log.info(
                "  id=%s date=%s platform=%r pe_sponsor=%r url=%s",
                r.id, r.deal_date, r.platform_company, r.pe_sponsor, r.source_url,
            )

        if dry_run:
            log.info("--dry-run: no rows deleted.")
            return len(rows)

        for r in rows:
            session.delete(r)
        session.commit()
        log.info("Deleted %d rows.", len(rows))
        return len(rows)
    finally:
        session.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    deleted = main(dry_run=dry)
    log.info("Cleanup complete. %d rows %s.", deleted, "would be deleted" if dry else "deleted")
