#!/usr/bin/env python3
"""Publish the generated office-census queue to Supabase (additive, own tables only).

  python3 scrapers/office_census_publish.py                 # validate files only (no DB access)
  python3 scrapers/office_census_publish.py --allow-db-write
      # create the 3 office_census_* tables if missing (scrapers/office_census_schema.sql),
      # then replace office_census_candidates + office_census_zip_coverage contents and
      # append the build manifest to office_census_builds -- ONE transaction
  python3 scrapers/office_census_publish.py --verify
      # independent read-back: live totals, per-state and per-ZIP counts vs the files

Touches no existing table. Never part of sync_to_supabase.py / refresh.sh.
Input = the committed files under data/office_census/ written by
`python3 scrapers/office_census.py build`, so live state is reproducible from git.
"""
import argparse
import collections
import csv
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "office_census"
SCHEMA = ROOT / "scrapers" / "office_census_schema.sql"

_env = ROOT / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_env)
except ImportError:
    if _env.is_file():
        for line in _env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

CAND_COLS = (
    "candidate_id", "zip", "city", "origin", "in_directory", "location_id", "name", "address",
    "suite", "suites_seen", "phone", "website", "entity_classification", "queue_state", "priority",
    "effort", "flags", "gp_scope_taxonomy", "provider_count", "org_npis_at_street",
    "phones_at_street", "da_records_at_street", "da_latest_update", "prior_evidence_level",
    "prior_evidence", "source_refs", "latitude", "longitude", "coord_status", "observations",
    "sources_checked", "decision", "batch_rank", "build_id",
)
CAND_JSON = {"suites_seen", "flags", "prior_evidence", "source_refs", "sources_checked", "decision"}


def load():
    manifest = json.loads((OUT / "manifest.json").read_text())
    cands = [json.loads(l) for l in (OUT / "candidates.jsonl").read_text().splitlines()]
    with (OUT / "zip_coverage.csv").open() as f:
        cov = list(csv.DictReader(f))
    return manifest, cands, cov


def validate(manifest, cands, cov):
    problems = []
    t = manifest["totals"]
    if len(cands) != t["candidates"]:
        problems.append(f"candidates.jsonl has {len(cands)} rows, manifest says {t['candidates']}")
    ids = [c["candidate_id"] for c in cands]
    if len(ids) != len(set(ids)):
        problems.append("duplicate candidate_id")
    states = collections.Counter(c["queue_state"] for c in cands)
    for s, n in t["by_state"].items():
        if states.get(s, 0) != n:
            problems.append(f"state {s}: file {states.get(s, 0)} != manifest {n}")
    if len(cov) != manifest["watched_zips"]:
        problems.append(f"zip_coverage has {len(cov)} rows, expected {manifest['watched_zips']}")
    dir_rows = sum(int(r["directory_rows"]) for r in cov)
    if dir_rows != t["directory_rows"]:
        problems.append(f"coverage directory_rows sum {dir_rows} != manifest {t['directory_rows']}")
    per_zip = collections.Counter(c["zip"] for c in cands)
    for r in cov:
        n = sum(int(r[k]) for k in ("directory_rows", "excluded_rows", "source_candidates", "external_discoveries"))
        if n != per_zip.get(r["zip"], 0):
            problems.append(f"zip {r['zip']}: coverage origins {n} != candidates {per_zip.get(r['zip'], 0)}")
    for c in cands:
        if c["queue_state"] == "CONFIRMED_OPERATING_GP" and not c.get("decision"):
            problems.append(f"{c['candidate_id']}: CONFIRMED without a ledger decision")
    return problems


def cand_params(c, build_id):
    p = {k: c.get(k) for k in CAND_COLS}
    p["build_id"] = build_id
    for k in CAND_JSON:
        p[k] = json.dumps(p[k]) if p[k] is not None else (None if k == "decision" else json.dumps([] if k in (
            "suites_seen", "flags", "sources_checked") else {}))
    return p


def cov_params(r, build_id):
    out = {}
    for k, v in r.items():
        if k == "pilot":
            out[k] = v == "True"
        elif k == "sources_searched":
            out[k] = json.dumps([s for s in v.split(";") if s])
        elif k in ("zip", "city", "stage"):
            out[k] = v or None
        elif k == "last_activity":
            out[k] = v or None
        else:
            out[k] = int(v)
    out["build_id"] = build_id
    return out


def get_engine():
    from sqlalchemy import create_engine
    url = os.environ.get("SUPABASE_POOLER_URL") or os.environ.get("SUPABASE_DATABASE_URL")
    if not url:
        raise SystemExit("FAIL: no Postgres URL (SUPABASE_POOLER_URL) in .env")
    return create_engine(url, pool_size=2, pool_pre_ping=True)


def write(manifest, cands, cov):
    from psycopg2.extras import execute_values
    bid = manifest["build_id"]
    engine = get_engine()
    with engine.begin() as conn:
        raw = conn.connection.dbapi_connection.cursor()
        raw.execute(SCHEMA.read_text())  # idempotent: IF NOT EXISTS + guarded policies
        raw.execute("DELETE FROM office_census_candidates")
        rows = [cand_params(c, bid) for c in cands]
        tmpl = "(" + ", ".join(f"%({k})s::jsonb" if k in CAND_JSON else f"%({k})s" for k in CAND_COLS) + ")"
        execute_values(raw, f"INSERT INTO office_census_candidates ({', '.join(CAND_COLS)}) VALUES %s",
                       rows, template=tmpl, page_size=500)
        raw.execute("DELETE FROM office_census_zip_coverage")
        crow = [cov_params(r, bid) for r in cov]
        cols = list(crow[0].keys())
        tmpl = "(" + ", ".join(f"%({k})s::jsonb" if k == "sources_searched" else f"%({k})s" for k in cols) + ")"
        execute_values(raw, f"INSERT INTO office_census_zip_coverage ({', '.join(cols)}) VALUES %s",
                       crow, template=tmpl, page_size=500)
        raw.execute(
            "INSERT INTO office_census_builds (build_id, rules_version, built_at, manifest) "
            "VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (build_id) DO UPDATE SET published_at = now()",
            (bid, manifest["rules_version"], manifest["built_at"], json.dumps(manifest)))
        raw.execute("NOTIFY pgrst, 'reload schema'")
    print(f"Published build {bid}: {len(cands)} candidates, {len(cov)} ZIP coverage rows.")


def verify(manifest, cands, cov):
    from sqlalchemy import text
    engine = get_engine()
    fail = 0
    with engine.connect() as conn:
        live_bid = {r[0] for r in conn.execute(text("SELECT DISTINCT build_id FROM office_census_candidates"))}
        live_states = dict(conn.execute(text(
            "SELECT queue_state, count(*) FROM office_census_candidates GROUP BY 1")).fetchall())
        live_zip = dict(conn.execute(text(
            "SELECT zip, count(*) FROM office_census_candidates GROUP BY 1")).fetchall())
        live_cov = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(text(
            "SELECT zip, directory_rows, open_items, batch_rank FROM office_census_zip_coverage"))}
        live_dir = conn.execute(text(
            "SELECT count(*) FROM office_census_candidates WHERE in_directory")).scalar()
        builds = conn.execute(text("SELECT count(*) FROM office_census_builds WHERE build_id=:b"),
                              {"b": manifest["build_id"]}).scalar()
    file_states = collections.Counter(c["queue_state"] for c in cands)
    file_zip = collections.Counter(c["zip"] for c in cands)
    print(f"build: file {manifest['build_id']} live {sorted(live_bid)} builds-row {builds}")
    if live_bid != {manifest["build_id"]} or builds != 1:
        print("FAIL: live build_id differs from files"); fail = 1
    print(f"candidates: file {len(cands)} live {sum(live_states.values())}; directory file "
          f"{manifest['totals']['directory_rows']} live {live_dir}")
    for s in sorted(set(file_states) | set(live_states)):
        mark = "" if file_states.get(s, 0) == live_states.get(s, 0) else "  MISMATCH"
        print(f"  {s:32s} file {file_states.get(s, 0):5d} live {live_states.get(s, 0):5d}{mark}")
        fail |= bool(mark)
    zip_mism = [z for z in set(file_zip) | set(live_zip) if file_zip.get(z, 0) != live_zip.get(z, 0)]
    cov_mism = [r["zip"] for r in cov if live_cov.get(r["zip"]) != (
        int(r["directory_rows"]), int(r["open_items"]), int(r["batch_rank"]))]
    print(f"per-ZIP candidate mismatches: {len(zip_mism)}; coverage-row mismatches: {len(cov_mism)} "
          f"(live coverage rows {len(live_cov)} / file {len(cov)})")
    fail |= bool(zip_mism or cov_mism or len(live_cov) != len(cov) or live_dir != manifest["totals"]["directory_rows"])
    print("FAIL" if fail else "OK: live office census matches the generated files exactly.")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--allow-db-write", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    manifest, cands, cov = load()
    problems = validate(manifest, cands, cov)
    if problems:
        for p in problems[:50]:
            print("  " + p)
        raise SystemExit(f"FAIL: {len(problems)} validation problem(s); nothing published.")
    print(f"Files valid: build {manifest['build_id']}, {len(cands)} candidates, {len(cov)} ZIPs.")
    if args.allow_db_write:
        write(manifest, cands, cov)
    if args.verify:
        return verify(manifest, cands, cov)
    if not args.allow_db_write:
        print("Validate-only (no DB access). Use --allow-db-write and/or --verify.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
