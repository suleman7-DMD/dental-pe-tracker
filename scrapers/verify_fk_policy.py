"""Verify the practice_changes_npi_fkey ON DELETE policy in Supabase.

The April 2026 audit moved `_sync_watched_zips_only` to use TRUNCATE TABLE
practices CASCADE because the FK had ON DELETE NO ACTION at the time. If the
FK has since been altered to ON DELETE CASCADE, we can simplify the sync to
plain DELETE. If still NO ACTION ('a'), we keep the TRUNCATE CASCADE pattern.

Usage:
    python3 scrapers/verify_fk_policy.py
    python3 scrapers/verify_fk_policy.py --apply-cascade   # alters the FK to CASCADE

Exit code 0 = verified (CASCADE in place OR NO ACTION confirmed).
Exit code 1 = unexpected state.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger

log = get_logger("verify_fk_policy")

# Mapping per Postgres docs (pg_constraint.confdeltype):
# 'a' = NO ACTION, 'r' = RESTRICT, 'c' = CASCADE, 'n' = SET NULL, 'd' = SET DEFAULT
DELETE_TYPE_LABELS = {
    "a": "NO ACTION",
    "r": "RESTRICT",
    "c": "CASCADE",
    "n": "SET NULL",
    "d": "SET DEFAULT",
}


def get_pg_engine():
    from sqlalchemy import create_engine
    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "SUPABASE_DATABASE_URL (or DATABASE_URL) is not set in env. "
            "Export it before running this script."
        )
    return create_engine(url, pool_pre_ping=True)


def query_fk(engine, constraint_name="practice_changes_npi_fkey"):
    from sqlalchemy import text
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT confdeltype, conrelid::regclass AS source_table, confrelid::regclass AS target_table
                FROM pg_constraint
                WHERE conname = :name
                """
            ),
            {"name": constraint_name},
        ).fetchone()
    return row


def apply_cascade(engine, constraint_name="practice_changes_npi_fkey"):
    """Drop and recreate the FK with ON DELETE CASCADE. Idempotent — safe to re-run.
    Caller is responsible for ensuring no concurrent writes during the swap.
    """
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE practice_changes DROP CONSTRAINT IF EXISTS {constraint_name}"))
        conn.execute(
            text(
                f"ALTER TABLE practice_changes "
                f"ADD CONSTRAINT {constraint_name} "
                f"FOREIGN KEY (npi) REFERENCES practices(npi) ON DELETE CASCADE"
            )
        )
    log.info("FK %s recreated with ON DELETE CASCADE", constraint_name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-cascade", action="store_true",
                        help="Alter the FK to ON DELETE CASCADE if not already")
    parser.add_argument("--constraint",
                        default="practice_changes_npi_fkey",
                        help="Constraint name to inspect (default practice_changes_npi_fkey)")
    args = parser.parse_args()

    engine = get_pg_engine()
    row = query_fk(engine, args.constraint)
    if row is None:
        log.error("Constraint %s not found in pg_constraint — schema drift?", args.constraint)
        sys.exit(1)

    delete_type, source_table, target_table = row
    label = DELETE_TYPE_LABELS.get(delete_type, f"UNKNOWN({delete_type})")
    log.info(
        "Constraint=%s source=%s target=%s ON DELETE=%s (confdeltype=%s)",
        args.constraint, source_table, target_table, label, delete_type,
    )

    if delete_type == "c":
        log.info("FK already has ON DELETE CASCADE — sync_to_supabase.py can use plain DELETE.")
        sys.exit(0)
    if delete_type == "a":
        log.warning(
            "FK has ON DELETE NO ACTION — _sync_watched_zips_only MUST keep TRUNCATE ... CASCADE. "
            "Run with --apply-cascade to upgrade."
        )
        if args.apply_cascade:
            apply_cascade(engine, args.constraint)
            new_row = query_fk(engine, args.constraint)
            new_label = DELETE_TYPE_LABELS.get(new_row[0], "?") if new_row else "?"
            log.info("Post-apply confdeltype=%s (%s)", new_row[0] if new_row else "?", new_label)
            sys.exit(0)
        sys.exit(0)  # 0 because NO ACTION is acceptable, just documented
    log.error("Unexpected confdeltype=%s — manual review required", delete_type)
    sys.exit(1)


if __name__ == "__main__":
    main()
