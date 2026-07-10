"""Merge the 2026-07-10 full-run JHV research wave into the seed file.

Inputs (result files = ground truth, never re-researched):
  data/dso_research/_jhv_full_run_batches_20260710/batch_*.json  -- 94 Sonnet batch outputs
  data/dso_research/_jhv_full_cohort_20260710.json               -- the 560-practice cohort
  data/dso_research/_jhv_pilot_results_20260710.json             -- 34 normalized pilot rows
  data/job_hunt_verification_seed.json                           -- 48-row seed of truth

Steps (validate-first, same contract as import_job_hunt_verification.py):
  1. Load + merge batch files; assert exact coverage of the 560 cohort ids, no dups.
  2. Bank the merged verbatim rows to _jhv_full_run_results_raw_20260710.json.
  3. Normalize to seed shape (bookkeeping cols, enum-safe remaps -- remaps are
     LOGGED, never silent).
  4. Validate every new row with the importer's own validate().
  5. Build the new seed = old 48 + pilot 34 + full-run 560 = 642 unique rows,
     validate the whole file, and write it ONLY with --write-seed.
  6. Write an evidence file with tallies + remap log.

Usage:
  python3 -m scrapers.merge_jhv_full_run_20260710              # dry run (steps 1-5 checks)
  python3 -m scrapers.merge_jhv_full_run_20260710 --write-seed # also write seed + evidence
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.import_job_hunt_verification import COLUMNS, validate, tally, report_tally

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCH_GLOB = os.path.join(ROOT, "data/dso_research/_jhv_full_run_batches_20260710/batch_*.json")
COHORT_PATH = os.path.join(ROOT, "data/dso_research/_jhv_full_cohort_20260710.json")
PILOT_PATH = os.path.join(ROOT, "data/dso_research/_jhv_pilot_results_20260710.json")
SEED_PATH = os.path.join(ROOT, "data/job_hunt_verification_seed.json")
RAW_OUT = os.path.join(ROOT, "data/dso_research/_jhv_full_run_results_raw_20260710.json")
EVIDENCE_OUT = os.path.join(ROOT, "data/dso_research/jhv_full_run_merge_evidence_20260710.json")

CHECKED_BY = "fable-sonnet-full-run"
ALLOWED_ROLE_TYPES = {"dentist", "hygienist", "assistant", "front_office", "other"}
ALLOWED_DOCTOR_ROLES = {"owner", "associate", "unknown"}
# Conservative remaps for known-safe drift only; anything else falls to
# "other"/"unknown" and is logged in the evidence file.
ROLE_TYPE_REMAP = {
    "office_manager": "front_office", "receptionist": "front_office",
    "front_desk": "front_office", "dental_assistant": "assistant",
    "dental_hygienist": "hygienist", "orthodontist": "dentist",
    "associate_dentist": "dentist", "general_dentist": "dentist",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write-seed", action="store_true",
                    help="write the merged 642-row seed + raw bank + evidence file")
    args = ap.parse_args()

    batch_files = sorted(glob.glob(BATCH_GLOB))
    print(f"batch files: {len(batch_files)}")
    raw, seen_ids, dup_ids = [], set(), []
    per_file = {}
    for bf in batch_files:
        rows = json.load(open(bf))
        if not isinstance(rows, list):
            raise SystemExit(f"FAIL: {bf} is not a JSON array")
        per_file[os.path.basename(bf)] = len(rows)
        for r in rows:
            lid = r.get("location_id")
            if lid in seen_ids:
                dup_ids.append(lid)
            seen_ids.add(lid)
            raw.append(r)
    if dup_ids:
        raise SystemExit(f"FAIL: duplicate location_ids across batches: {dup_ids}")

    cohort_ids = {r["location_id"] for r in json.load(open(COHORT_PATH))}
    missing = sorted(cohort_ids - seen_ids)
    extra = sorted(seen_ids - cohort_ids)
    print(f"raw rows: {len(raw)}  cohort: {len(cohort_ids)}  "
          f"missing: {len(missing)}  extra: {len(extra)}")
    if missing:
        print("MISSING ids (relaunch these units):")
        for m in missing:
            print(" ", m)
    if extra:
        raise SystemExit(f"FAIL: rows outside the cohort: {extra}")
    if missing:
        raise SystemExit(f"FAIL: {len(missing)} cohort ids uncovered -- relaunch first.")

    # Normalize
    now = datetime.now(timezone.utc).isoformat()
    remap_log = []
    normalized = []
    for r in raw:
        row = {c: r.get(c) for c in COLUMNS if c in r}
        for c in ("doctors", "openings", "evidence_urls"):
            if not isinstance(row.get(c), list):
                remap_log.append(f"{r['location_id']}: {c} {row.get(c)!r} -> []")
                row[c] = []
        row["last_checked_at"] = now
        row["checked_by"] = CHECKED_BY
        row["created_at"] = now
        row["updated_at"] = now
        if row.get("provider_count_website") == 0:
            row["provider_count_website"] = None
        for o in row["openings"]:
            rt = o.get("role_type")
            if rt not in ALLOWED_ROLE_TYPES:
                new = ROLE_TYPE_REMAP.get(rt, "other")
                remap_log.append(f"{r['location_id']}: role_type {rt!r} -> {new!r}")
                o["role_type"] = new
        for d in row["doctors"]:
            if d.get("role") not in ALLOWED_DOCTOR_ROLES:
                remap_log.append(f"{r['location_id']}: doctor role {d.get('role')!r} -> 'unknown'")
                d["role"] = "unknown"
        missing_cols = [c for c in COLUMNS if c not in row]
        for c in missing_cols:
            remap_log.append(f"{r['location_id']}: missing column {c} -> null")
            row[c] = None
        normalized.append(row)

    problems = validate(normalized)
    if problems:
        for p in problems:
            print(" ", p)
        raise SystemExit(f"FAIL: {len(problems)} validation problem(s) in full-run rows.")
    report_tally("Full-run (normalized)", tally(normalized), len(normalized))
    if remap_log:
        print(f"remaps applied: {len(remap_log)} (see evidence file)")

    seed = json.load(open(SEED_PATH))
    pilot = json.load(open(PILOT_PATH))
    combined = seed + pilot + normalized
    ids = [r["location_id"] for r in combined]
    if len(ids) != len(set(ids)):
        raise SystemExit("FAIL: id collision between seed/pilot/full-run.")
    problems = validate(combined)
    if problems:
        raise SystemExit(f"FAIL: {len(problems)} problem(s) in combined seed.")
    report_tally("Combined seed candidate", tally(combined), len(combined))

    if not args.write_seed:
        print("Dry run OK. Re-run with --write-seed to write seed + raw bank + evidence.")
        return

    with open(RAW_OUT, "w") as f:
        json.dump(raw, f, indent=1)
        f.write("\n")
    with open(SEED_PATH, "w") as f:
        json.dump(combined, f, indent=1, default=str)
        f.write("\n")
    with open(EVIDENCE_OUT, "w") as f:
        json.dump({
            "merged_at": now,
            "checked_by": CHECKED_BY,
            "batch_files": per_file,
            "full_run_rows": len(normalized),
            "full_run_tally": tally(normalized),
            "pilot_rows": len(pilot),
            "seed_rows_before": len(seed),
            "seed_rows_after": len(combined),
            "combined_tally": tally(combined),
            "remap_log": remap_log,
        }, f, indent=1)
        f.write("\n")
    print(f"Wrote {RAW_OUT}")
    print(f"Wrote {SEED_PATH} ({len(combined)} rows)")
    print(f"Wrote {EVIDENCE_OUT}")


if __name__ == "__main__":
    main()
