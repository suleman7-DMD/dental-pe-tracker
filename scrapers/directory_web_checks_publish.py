#!/usr/bin/env python3
"""Publish rapid-validation checks to the live Directory page (Supabase directory_web_checks).

  python3 scrapers/directory_web_checks_publish.py                  # validate + preview, no DB access
  python3 scrapers/directory_web_checks_publish.py --allow-db-write --verify
      # replace directory_web_checks from data/office_census/rapid/checks.jsonl in ONE
      # transaction, log the publish, then read every row back (Postgres) and count it
      # through the anon REST API the page uses
  python3 scrapers/directory_web_checks_publish.py --verify         # read-back only
  python3 scrapers/directory_web_checks_publish.py --install-store  # shared-store tables + rapid_*
      # functions (directory_web_checks_store.sql), and backfill its log from checks.jsonl
  python3 scrapers/directory_web_checks_publish.py --new-token LABEL  # issue a RAPID_TOKEN

With the shared store (RAPID_TOKEN set), sessions publish each check as they record it and this
script is maintenance only: --allow-db-write first pulls every session's checks from the shared
log, so a full replace can never drop rows another session recorded.

Each row's latest check becomes one live row whose `effect` the Directory page applies:
  NOT_CURRENT_GP   -> removed          hidden from the directory list and map
  VALID_CORRECTED  -> open_corrected   web-seen name / phone / website / address shown
  VALID            -> open_verified
  IDENTITY_ONLY    -> listed_only
  IDENTITY_PROBLEM, ESCALATE -> needs_review
  NO_WEB_EVIDENCE  -> no_web_evidence  never counts against the row

Touches only directory_web_checks + directory_web_check_publishes (own tables, no FK, not in
sync_to_supabase.py / refresh.sh). practice_locations, ownership tiers and pipeline counts are
unchanged: the page applies the overlay at read time, so emptying the table restores it.

Safety brake: refuses to publish when removals exceed 35% of checked rows, or 50% of any
session with >= 20 rows (a runaway session), unless --allow-high-removal. Removals the shared
store's brake held back stay off the page unless --allow-high-removal.
"""
import argparse
import collections
import datetime
import hashlib
import json
import os
import pathlib
import secrets
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import office_census_rapid as rv  # noqa: E402
import rapid_store as store  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "scrapers" / "directory_web_checks_schema.sql"
STORE_SQL = ROOT / "scrapers" / "directory_web_checks_store.sql"

EFFECT = rv.EFFECT
load_env = store.load_env
COLS = ("location_id", "candidate_id", "zip", "effect", "decision", "reason", "duplicate_of", "gp_scope",
        "observed", "as_seen", "signals", "ties_by", "evidence", "leads", "note", "checked_at",
        "recorded_at", "session", "researcher", "rules", "publish_id")
JSON_COLS = {"observed", "as_seen", "signals", "ties_by", "evidence", "leads"}
MAX_REMOVED_SHARE = 0.35
MAX_SESSION_REMOVED_SHARE = 0.50
MIN_SESSION_ROWS = 20


def build_rows(checks, publish_id):
    return [rv.web_check_row(cid, e, publish_id) for cid, e in sorted(checks.items())]


def problems(rows, check_errs, allow_high_removal=False):
    out = [f"check: {x}" for x in check_errs[:20]]
    if len(check_errs) > 20:
        out.append(f"check: ... {len(check_errs) - 20} more")
    out += [f"{r['candidate_id']}: not a directory row" for r in rows if not r["candidate_id"].startswith("loc:")]
    if allow_high_removal:
        return out
    removed = sum(r["effect"] == "removed" for r in rows)
    if len(rows) >= MIN_SESSION_ROWS and removed / len(rows) > MAX_REMOVED_SHARE:
        out.append(f"removals are {removed}/{len(rows)} of checked rows (> {MAX_REMOVED_SHARE:.0%}); "
                   "review, then rerun with --allow-high-removal")
    by_session = collections.defaultdict(list)
    for r in rows:
        by_session[r["session"]].append(r["effect"] == "removed")
    for s, flags in by_session.items():
        if len(flags) >= MIN_SESSION_ROWS and sum(flags) / len(flags) > MAX_SESSION_REMOVED_SHARE:
            out.append(f"session {s} removed {sum(flags)}/{len(flags)} rows (> {MAX_SESSION_REMOVED_SHARE:.0%}); "
                       "review that session, then rerun with --allow-high-removal")
    return out


def pipeline_impact(rows):
    """Read-only: how the removed rows sit in the pipeline (they stay counted there)."""
    db = rv.db_path()
    ids = [r["location_id"] for r in rows if r["effect"] == "removed"]
    if not db or not ids:
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        got = con.execute(
            f"SELECT entity_classification, ownership_tier FROM practice_locations "
            f"WHERE location_id IN ({','.join('?' * len(ids))})", ids).fetchall()
    finally:
        con.close()
    return {"removed": len(ids), "found": len(got),
            "tiered": sum(1 for _, t in got if t),
            "corporate": sum(1 for c, _ in got if c in ("dso_regional", "dso_national"))}


def get_engine():
    from sqlalchemy import create_engine
    url = os.environ.get("SUPABASE_POOLER_URL") or os.environ.get("SUPABASE_DATABASE_URL")
    if not url:
        raise SystemExit("FAIL: no Postgres URL (SUPABASE_POOLER_URL) in .env")
    return create_engine(url, pool_size=2, pool_pre_ping=True)


def params(r):
    return {k: json.dumps(r[k]) if k in JSON_COLS else r[k] for k in COLS}


def write(rows, publish_id, sha, by_effect, known_entry_ids=None):
    from psycopg2.extras import execute_values
    engine = get_engine()
    with engine.begin() as conn:
        raw = conn.connection.dbapi_connection.cursor()
        raw.execute("SET LOCAL lock_timeout = '10s'")
        raw.execute("SET LOCAL statement_timeout = '120s'")
        # the same lock rapid_record takes: no session can record between this check and the replace
        raw.execute("SELECT pg_advisory_xact_lock(hashtext('directory_web_checks'))")
        raw.execute(SCHEMA.read_text())  # idempotent: IF NOT EXISTS + guarded policies
        if known_entry_ids is not None:
            raw.execute("SELECT entry_id FROM directory_web_check_log")
            new = {r[0] for r in raw.fetchall()} - known_entry_ids
            if new:
                raise SystemExit(f"FAIL: {len(new)} checks were recorded after the pull; rerun. Nothing published.")
        raw.execute("DELETE FROM directory_web_checks")
        tmpl = "(" + ", ".join(f"%({k})s::jsonb" if k in JSON_COLS else f"%({k})s" for k in COLS) + ")"
        if rows:
            execute_values(raw, f"INSERT INTO directory_web_checks ({', '.join(COLS)}) VALUES %s",
                           [params(r) for r in rows], template=tmpl, page_size=500)
        raw.execute("INSERT INTO directory_web_check_publishes (publish_id, rows, by_effect, checks_sha256, rules) "
                    "VALUES (%s, %s, %s::jsonb, %s, %s)",
                    (publish_id, len(rows), json.dumps(by_effect), sha, rv.RULES))
        raw.execute("NOTIFY pgrst, 'reload schema'")
    print(f"Published {publish_id}: {len(rows)} rows ({', '.join(f'{k} {v}' for k, v in sorted(by_effect.items()))}).")


def same(k, want, got):
    if k == "checked_at":
        return want == (got.isoformat() if got else None)
    if k == "recorded_at":
        return got is not None and datetime.datetime.fromisoformat(want) == got
    return want == got


def verify(rows, by_effect):
    from sqlalchemy import text
    engine = get_engine()
    with engine.connect() as conn:
        live = {r["location_id"]: dict(r) for r in
                conn.execute(text("SELECT * FROM directory_web_checks")).mappings()}
        last = conn.execute(text("SELECT publish_id, rows FROM directory_web_check_publishes "
                                 "ORDER BY published_at DESC LIMIT 1")).fetchone()
    fail = 0
    mism = [r["location_id"] for r in rows if r["location_id"] not in live or not all(
        same(k, r[k], live[r["location_id"]].get(k)) for k in COLS if k != "publish_id")]
    extra = set(live) - {r["location_id"] for r in rows}
    print(f"postgres: file {len(rows)} live {len(live)} · row mismatches {len(mism)} · extra live rows {len(extra)}"
          f" · latest full publish {last[0] if last else None} ({last[1] if last else '-'} rows)")
    if mism or extra:
        fail = 1
        for m in mism[:10]:
            print(f"  MISMATCH {m}")
    # The page reads through PostgREST as anon: count every effect that way too.
    url, key, _ = store.settings()
    if not url or not key:
        print("anon REST: skipped (Supabase URL / anon key not set)")
        return fail
    counts = {eff: store.count("directory_web_checks", effect=f"eq.{eff}") for eff in sorted(set(EFFECT.values()))}
    bad = {k: v for k, v in counts.items() if v != by_effect.get(k, 0)}
    print("anon REST by effect: " + ", ".join(f"{k} {v}" for k, v in counts.items()) +
          ("" if not bad else f"  MISMATCH {bad}"))
    fail |= bool(bad)
    print("FAIL" if fail else "OK: live directory_web_checks matches checks.jsonl exactly.")
    return fail


def install_store():
    """Create the shared-store tables and rapid_* functions (idempotent), then copy every
    checks.jsonl line into the log as a 'backfill' entry (already live; existing ids kept)."""
    lines = rv.read_jsonl(rv.path("checks.jsonl"))
    engine = get_engine()
    with engine.begin() as conn:
        raw = conn.connection.dbapi_connection.cursor()
        raw.execute("SET LOCAL lock_timeout = '10s'")
        raw.execute("SELECT pg_advisory_xact_lock(hashtext('directory_web_checks'))")
        raw.execute(SCHEMA.read_text())
        raw.execute(STORE_SQL.read_text())
        added = 0
        for e in lines:
            raw.execute(
                "INSERT INTO directory_web_check_log (entry_id, candidate_id, location_id, session, recorded_at, "
                "decision, searches, entry, outcome) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'backfill') "
                "ON CONFLICT (entry_id) DO NOTHING",
                (e["entry_id"], e["candidate_id"], rv.strip_loc(e["candidate_id"]), e.get("session"),
                 e["recorded_at"], e["decision"], e.get("searches", 0), json.dumps(e)))
            added += raw.rowcount
        raw.execute("NOTIFY pgrst, 'reload schema'")
    print(f"store installed · log backfill: {added} of {len(lines)} checks.jsonl lines added")


def new_token(label):
    tok = "rv_" + secrets.token_urlsafe(32)
    engine = get_engine()
    with engine.begin() as conn:
        conn.connection.dbapi_connection.cursor().execute(
            "INSERT INTO rapid_tokens (token_sha256, label) VALUES (%s, %s)",
            (hashlib.sha256(tok.encode()).hexdigest(), label))
    print(f"RAPID_TOKEN={tok}")
    print(f"(label {label!r}; revoke with: UPDATE rapid_tokens SET revoked_at = now() WHERE label = '{label}')")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--allow-db-write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--allow-high-removal", action="store_true")
    ap.add_argument("--rapid-dir", help="alternate rapid directory (tests)")
    ap.add_argument("--install-store", action="store_true", help="create/upgrade the shared store, backfill its log")
    ap.add_argument("--new-token", metavar="LABEL", help="issue a RAPID_TOKEN for sessions")
    args = ap.parse_args(argv)
    if args.rapid_dir:
        rv.P.set(args.rapid_dir)
    load_env()
    if args.install_store:
        install_store()
    if args.new_token:
        new_token(args.new_token)
    if args.install_store or args.new_token:
        return 0

    if not args.rapid_dir and store.configured():
        rv.P.store = "supabase"
        r = rv.pull()   # every session's checks, so a replace never drops another session's rows
        print(f"pulled the shared log: {r['log']} checks, {r['added']} new to checks.jsonl"
              + (f", {r['only_local']} local-only" if r["only_local"] else ""))
    elif args.allow_db_write and not args.rapid_dir:
        raise SystemExit("FAIL: the shared store is not configured (RAPID_TOKEN); a full replace from this "
                         "checkout alone could drop checks other sessions recorded. Nothing published.")

    with rv.locked():  # a consistent snapshot while sessions keep recording
        raw = rv.path("checks.jsonl").read_bytes() if rv.path("checks.jsonl").exists() else b""
        checks = rv.latest_checks(include_held=args.allow_high_removal)
        check_errs, _ = rv.check_errors()
    sha = hashlib.sha256(raw).hexdigest()
    stamp = rv.now_utc()
    publish_id = f"dwc-{stamp.strftime('%Y%m%dT%H%M%S')}-{sha[:8]}"
    rows = build_rows(checks, publish_id)
    by_effect = dict(collections.Counter(r["effect"] for r in rows))
    reasons = collections.Counter(r["reason"] for r in rows if r["effect"] == "removed")
    print(f"checks.jsonl: {len(rows)} rows · " + ", ".join(f"{k} {v}" for k, v in sorted(by_effect.items())))
    if reasons:
        print("removed by reason: " + ", ".join(f"{k} {v}" for k, v in reasons.most_common()))
    imp = pipeline_impact(rows)
    if imp:
        print(f"pipeline (unchanged by this publish): the {imp['removed']} removed rows still count in the GP "
              f"universe; {imp['tiered']} carry an ownership tier, {imp['corporate']} are detector-floor corporate")

    errs = problems(rows, check_errs, args.allow_high_removal)
    if errs:
        for p in errs:
            print("  " + p)
        raise SystemExit(f"FAIL: {len(errs)} problem(s); nothing published.")
    if args.allow_db_write:
        known = ({e.get("entry_id") for e in rv.read_jsonl(rv.path("checks.jsonl"))}
                 if rv.remote() else None)
        write(rows, publish_id, sha, by_effect, known)
        rv.path("last_publish.json").write_text(json.dumps(
            {"publish_id": publish_id, "published_at": stamp.isoformat(), "rows": len(rows),
             "by_effect": by_effect, "checks_sha256": sha}, indent=1))
    if args.verify:
        return verify(rows, by_effect)
    if not args.allow_db_write:
        print("Validate-only (no DB access). Use --allow-db-write and/or --verify.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
