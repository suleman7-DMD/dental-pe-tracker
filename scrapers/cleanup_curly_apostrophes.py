"""One-off cleanup: normalize curly quotes/apostrophes in existing Deal rows.

Context: before 3.5 of the 2026-04-23 parser pattern-hunt, scraper output
contained raw U+2019 RIGHT SINGLE QUOTATION MARK characters copied verbatim
from PESP/GDN prose. The live scrapers now pass all extracted strings through
``database.normalize_punctuation`` before ``insert_deal``, but 15 rows in
``deals`` today still carry curly characters — left over from pre-hardening
scrapes.

This script:
  1. Finds every Deal row whose platform_company / target_name / pe_sponsor
     contains any curly quote or apostrophe (U+2018/19/1A/1B, U+201C/1D/1E/1F).
  2. Computes the normalized (ASCII) version via ``normalize_punctuation``.
  3. If the normalized tuple is already present as a distinct row, deletes the
     curly row (the ASCII twin wins).
  4. Otherwise rewrites the row in place with the normalized strings.

Run locally once, then the existing Supabase sync picks up the delta. Kept
in-repo as an audit trail; NOT wired into refresh.sh.
"""
from __future__ import annotations

import sys

from sqlalchemy import or_

from scrapers.database import Deal, get_session, init_db, normalize_punctuation
from scrapers.logger_config import get_logger

log = get_logger("cleanup_curly_apostrophes")

_CURLY_CHARS = "‘’‚‛“”„‟"


def _has_curly(s: str | None) -> bool:
    return bool(s) and any(c in s for c in _CURLY_CHARS)


def _curly_filter():
    """SQLAlchemy filter matching rows with curly chars in any name column.

    SQLite ``LIKE`` is byte-substring safe for multi-byte UTF-8 sequences: each
    curly char serializes to 3 bytes and a literal ``'%<char>%'`` matches exactly.
    """
    preds = []
    for col in (Deal.platform_company, Deal.target_name, Deal.pe_sponsor):
        for ch in _CURLY_CHARS:
            preds.append(col.like(f"%{ch}%"))
    return or_(*preds)


def main(dry_run: bool = False) -> tuple[int, int]:
    init_db()
    session = get_session()
    try:
        rows = session.query(Deal).filter(_curly_filter()).all()
        if not rows:
            log.info("No curly-apostrophe rows to clean up.")
            return (0, 0)

        log.info("Found %d row(s) with curly punctuation", len(rows))

        deleted = 0
        rewritten = 0
        for r in rows:
            orig_platform = r.platform_company
            orig_target = r.target_name
            orig_sponsor = r.pe_sponsor

            new_platform = normalize_punctuation(orig_platform)
            new_target = normalize_punctuation(orig_target)
            new_sponsor = normalize_punctuation(orig_sponsor)

            if (new_platform, new_target, new_sponsor) == (orig_platform, orig_target, orig_sponsor):
                # Nothing changed after normalize — should not happen because
                # the query filter matched curly chars. Defensive no-op.
                continue

            # Is there an existing ASCII twin (distinct id, same key)?
            twin_q = session.query(Deal).filter(
                Deal.id != r.id,
                Deal.source == r.source,
                Deal.deal_date == r.deal_date,
                Deal.platform_company == new_platform,
            )
            if new_target is None:
                twin_q = twin_q.filter(Deal.target_name.is_(None))
            else:
                twin_q = twin_q.filter(Deal.target_name == new_target)
            twin = twin_q.first()

            if twin is not None:
                log.info(
                    "DEDUP id=%s %r -> merges into id=%s (%r / %r)",
                    r.id, orig_target or orig_platform,
                    twin.id, twin.platform_company, twin.target_name,
                )
                if not dry_run:
                    session.delete(r)
                deleted += 1
            else:
                log.info(
                    "REWRITE id=%s  platform: %r -> %r  target: %r -> %r",
                    r.id, orig_platform, new_platform, orig_target, new_target,
                )
                if not dry_run:
                    r.platform_company = new_platform
                    r.target_name = new_target
                    r.pe_sponsor = new_sponsor
                rewritten += 1

        if dry_run:
            log.info("--dry-run: no changes committed.")
        else:
            session.commit()
            log.info("Committed: %d rewritten, %d deleted", rewritten, deleted)

        return (rewritten, deleted)
    finally:
        session.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    rewritten, deleted = main(dry_run=dry)
    verb = "would be" if dry else ""
    log.info(
        "Cleanup complete. %d row(s) %s rewritten, %d row(s) %s deleted.",
        rewritten, verb, deleted, verb,
    )
