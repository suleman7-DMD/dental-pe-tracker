#!/usr/bin/env python3
"""Publish rapid-validation checks to the live Directory page (Supabase directory_web_checks).

  python3 scrapers/directory_web_checks_publish.py                  # validate + preview, no DB access
  python3 scrapers/directory_web_checks_publish.py --allow-db-write --verify
      # replace directory_web_checks from data/office_census/rapid/checks.jsonl in ONE
      # transaction, log the publish, then read every row back (Postgres) and count it
      # through the anon REST API the page uses
  python3 scrapers/directory_web_checks_publish.py --verify         # read-back only

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
session with >= 20 rows (a runaway session), unless --allow-high-removal.
"""
import argparse
import collections
import datetime
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import office_census_rapid as rv  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "scrapers" / "directory_web_checks_schema.sql"

EFFECT = {"VALID": "open_verified", "VALID_CORRECTED": "open_corrected", "IDENTITY_ONLY": "listed_only",
          "NOT_CURRENT_GP": "removed", "IDENTITY_PROBLEM": "needs_review", "ESCALATE": "needs_review",
          "NO_WEB_EVIDENCE": "no_web_evidence"}
COLS = ("location_id", "candidate_id", "zip", "effect", "decision", "reason", "duplicate_of", "gp_scope",
        "observed", "as_seen", "signals", "ties_by", "evidence", "leads", "note", "checked_at",
        "recorded_at", "session", "researcher", "rules", "publish_id")
JSON_COLS = {"observed", "as_seen", "signals", "ties_by", "evidence", "leads"}
MAX_REMOVED_SHARE = 0.35
MAX_SESSION_REMOVED_SHARE = 0.50
MIN_SESSION_ROWS = 20


def load_env():
    for base in (os.environ.get("OFFICE_CENSUS_INPUT_ROOT"), ROOT, pathlib.Path.home() / "dental-pe-tracker"):
        env = pathlib.Path(base) / ".env" if base else None
        if env and env.is_file():
            break
    else:
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env)
    except ImportError:
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def strip_loc(cid):
    return cid.split(":", 1)[1] if isinstance(cid, str) and cid.startswith("loc:") else cid


def build_rows(checks, publish_id):
    rows = []
    for cid, e in sorted(checks.items()):
        rows.append({
            "location_id": strip_loc(cid), "candidate_id": cid, "zip": e["zip"],
            "effect": EFFECT[e["decision"]], "decision": e["decision"], "reason": e.get("reason"),
            "duplicate_of": strip_loc(e.get("duplicate_of")), "gp_scope": e.get("gp_scope"),
            "observed": e.get("observed") or {}, "as_seen": e.get("as_seen") or {},
            "signals": e.get("signals") or [], "ties_by": e.get("ties_by") or [],
            "evidence": e.get("evidence") or [], "leads": e.get("leads") or [], "note": e.get("note"),
            "checked_at": e["checked_at"], "recorded_at": e["recorded_at"], "session": e.get("session"),
            "researcher": e.get("researcher"), "rules": e.get("rules"), "publish_id": publish_id})
    return rows


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


def write(rows, publish_id, sha, by_effect):
    from psycopg2.extras import execute_values
    engine = get_engine()
    with engine.begin() as conn:
        raw = conn.connection.dbapi_connection.cursor()
        raw.execute("SET LOCAL lock_timeout = '10s'")
        raw.execute("SET LOCAL statement_timeout = '120s'")
        raw.execute("SELECT pg_advisory_xact_lock(hashtext('directory_web_checks'))")
        raw.execute(SCHEMA.read_text())  # idempotent: IF NOT EXISTS + guarded policies
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
          f" · latest publish {last[0] if last else None} ({last[1] if last else '-'} rows)")
    if mism or extra or not last or last[1] != len(live):
        fail = 1
        for m in mism[:10]:
            print(f"  MISMATCH {m}")
    # The page reads through PostgREST as anon: count every effect that way too.
    import requests
    base, key = os.environ.get("NEXT_PUBLIC_SUPABASE_URL"), os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not base or not key:
        print("anon REST: skipped (NEXT_PUBLIC_SUPABASE_URL / ANON_KEY not in .env)")
        return fail
    hdr = {"apikey": key, "Authorization": f"Bearer {key}", "Prefer": "count=exact", "Range": "0-0"}
    counts = {}
    for eff in sorted(set(EFFECT.values())):
        for attempt in range(6):  # a brand-new table 404s until PostgREST reloads its schema cache
            resp = requests.get(f"{base}/rest/v1/directory_web_checks", params={"select": "location_id",
                                "effect": f"eq.{eff}"}, headers=hdr, timeout=30)
            if resp.status_code != 404:
                break
            time.sleep(2)
        rng = resp.headers.get("content-range", "")
        counts[eff] = int(rng.split("/")[-1]) if resp.ok and "/" in rng else f"HTTP {resp.status_code}"
    bad = {k: v for k, v in counts.items() if v != by_effect.get(k, 0)}
    print("anon REST by effect: " + ", ".join(f"{k} {v}" for k, v in counts.items()) +
          ("" if not bad else f"  MISMATCH {bad}"))
    fail |= bool(bad)
    print("FAIL" if fail else "OK: live directory_web_checks matches checks.jsonl exactly.")
    return fail


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--allow-db-write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--allow-high-removal", action="store_true")
    ap.add_argument("--rapid-dir", help="alternate rapid directory (tests)")
    args = ap.parse_args(argv)
    if args.rapid_dir:
        rv.P.set(args.rapid_dir)
    load_env()

    with rv.locked():  # a consistent snapshot while sessions keep recording
        raw = rv.path("checks.jsonl").read_bytes() if rv.path("checks.jsonl").exists() else b""
        checks = rv.latest_checks()
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
        write(rows, publish_id, sha, by_effect)
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
