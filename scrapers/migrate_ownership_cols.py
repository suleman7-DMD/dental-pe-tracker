"""ALTER TABLE practices — add the NPPES ownership-piercing columns on BOTH
databases (SQLite pipeline DB + Supabase Postgres). Idempotent on both.

WHY: nppes_downloader.py historically kept only ~16 of the ~330 columns in the
CMS npidata_pfile, discarding the fields that let us pierce friendly-PC / DSO
ownership veils — the Authorized Official (the human who legally controls an
organization NPI), the back-office MAILING address (DSOs route many local PCs to
one MSO billing address), the subpart flag, and the parent-organization LBN/TIN.
These ten columns are the structural raw material for the Phase B detectors
(B2 = officer + mailing + parent-TIN clustering). They are detection-internal;
the frontend never reads them, but we add them to Supabase too so the weekly
sync carries them without column-mismatch errors.

Pattern mirrors dossier_batch/migrate_verification_cols.py exactly:
  - Postgres: ADD COLUMN IF NOT EXISTS (native idempotency).
  - SQLite: introspect PRAGMA table_info and skip existing columns (SQLite has
    no ADD COLUMN IF NOT EXISTS).

Base.metadata.create_all() does NOT alter existing tables, so these explicit
ALTERs are required on both live DBs. Safe to re-run any number of times.

USAGE:
  python3 -m scrapers.migrate_ownership_cols              # both DBs
  python3 -m scrapers.migrate_ownership_cols --sqlite-only # skip Supabase
GATED: run only AFTER the weekly refresh.sh Supabase sync has finished — never
mid-sync (a TRUNCATE CASCADE is in flight during the practices sync).
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(ROOT, ".env")
if os.path.exists(env_path):
    for raw in open(env_path):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

# (column_name, sqlite_type, postgres_type)
NEW_COLS = [
    ("authorized_official_last_name", "TEXT", "TEXT"),
    ("authorized_official_first_name", "TEXT", "TEXT"),
    ("authorized_official_title", "TEXT", "TEXT"),
    ("authorized_official_credential", "TEXT", "TEXT"),
    ("mailing_address", "TEXT", "TEXT"),
    ("mailing_city", "TEXT", "TEXT"),
    ("mailing_state", "TEXT", "TEXT"),
    ("mailing_zip", "TEXT", "TEXT"),
    ("is_org_subpart", "TEXT", "VARCHAR(1)"),
    ("parent_org_lbn", "TEXT", "TEXT"),
    ("parent_org_tin", "TEXT", "TEXT"),
]

# Indexes that make the Phase B2 clustering joins cheap. Partial index on the
# TIN (sparse — only org NPIs that disclose a parent populate it).
INDEXES = [
    ("ix_practices_parent_org_tin",
     "CREATE INDEX IF NOT EXISTS ix_practices_parent_org_tin "
     "ON practices(parent_org_tin)"),
    ("ix_practices_auth_official",
     "CREATE INDEX IF NOT EXISTS ix_practices_auth_official "
     "ON practices(authorized_official_last_name, authorized_official_first_name)"),
    ("ix_practices_mailing_zip",
     "CREATE INDEX IF NOT EXISTS ix_practices_mailing_zip "
     "ON practices(mailing_zip)"),
]

SQLITE_ONLY = "--sqlite-only" in sys.argv


def migrate_sqlite():
    sqlite_path = os.path.join(ROOT, "data", "dental_pe_tracker.db")
    if not os.path.exists(sqlite_path):
        print(f"SKIP SQLite: {sqlite_path} not found")
        return
    print("== SQLite ==")
    with sqlite3.connect(sqlite_path) as conn:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(practices)").fetchall()}
        added = 0
        for name, sqlite_type, _ in NEW_COLS:
            if name in existing:
                print(f"  -> {name} already exists, skipping")
                continue
            conn.execute(f"ALTER TABLE practices ADD COLUMN {name} {sqlite_type}")
            print(f"  -> ADDED {name} {sqlite_type}")
            added += 1
        for _, ddl in INDEXES:
            conn.execute(ddl)
        conn.commit()
        final = {r[1] for r in conn.execute("PRAGMA table_info(practices)").fetchall()}
        have = sum(1 for n, _, _ in NEW_COLS if n in final)
        print(f"  SQLite: {added} added this run; {have}/{len(NEW_COLS)} present total.")


def migrate_supabase():
    try:
        from scrapers.sync_to_supabase import _get_pg_url
    except Exception as e:  # pragma: no cover
        print(f"SKIP Supabase: cannot import _get_pg_url ({e})")
        return
    try:
        url = _get_pg_url()
    except Exception as e:
        print(f"SKIP Supabase: no Postgres URL ({e})")
        return
    from sqlalchemy import create_engine, text
    engine = create_engine(url, pool_pre_ping=True)
    print("\n== Supabase (Postgres) ==")
    with engine.begin() as conn:
        conn.execute(text("SET statement_timeout = '120s'"))
        for name, _, pg_type in NEW_COLS:
            conn.execute(text(
                f"ALTER TABLE practices ADD COLUMN IF NOT EXISTS {name} {pg_type}"))
            print(f"  -> {name} {pg_type} (added or already existed)")
        for _, ddl in INDEXES:
            conn.execute(text(ddl))
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='practices' AND column_name = ANY(:names)
            ORDER BY column_name
        """), {"names": [n for n, _, _ in NEW_COLS]}).fetchall()
        print(f"  Supabase: {len(rows)}/{len(NEW_COLS)} ownership columns present.")


if __name__ == "__main__":
    migrate_sqlite()
    if not SQLITE_ONLY:
        migrate_supabase()
    print("\nDONE. Next: backfill values via "
          "`python3 scrapers/nppes_downloader.py --backfill-ownership-cols`.")
