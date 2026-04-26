"""
Generic launcher for batch practice-dossier research.

Default behavior (no flags): top-1-per-ZIP across Chicagoland watched ZIPs,
budget=$11, cost-per-practice=$0.055 (April-2025 estimate).

Flags supported:
  --budget USD            Cap total estimated spend (default 11.0). Practices
                          past the cap are trimmed from the tail.
  --cost-per-practice USD Per-practice estimate used for the budget calc
                          (default 0.055). Audit found real cost is closer to
                          $0.008/practice in batch mode — bump down once you
                          have your own console-verified rate.
  --target-count N        If set, pick top-N by priority across the pool
                          instead of one-per-ZIP. Useful for big backfills.
  --metro-pattern STR     SQL LIKE pattern for watched_zips.metro_area
                          (default '%Chicagoland%'). Use '%Boston%' for the
                          Boston Metro pool.
  --exclude-zip-pattern STR
                          SQL NOT LIKE pattern on practices.zip. Examples:
                          '606%' to skip Chicago proper (the use case the old
                          launch_2000_excl_chi.py script existed for).

Persists the resulting batch_id to BOTH data/last_batch_id.json (durable, the
poll.py default lookup path) and /tmp/full_batch_id.txt (back-compat).
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime

ROOT = "/Users/suleman/dental-pe-tracker"
sys.path.insert(0, ROOT)
for raw in open(os.path.join(ROOT, ".env")):
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

from scrapers.research_engine import ResearchEngine, MODEL_HAIKU
from scrapers.database import DB_PATH
from scrapers.practice_deep_dive import build_extra_context


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--budget", type=float, default=11.0,
                   help="Total estimated spend cap, USD (default 11.0)")
    p.add_argument("--cost-per-practice", type=float, default=0.055,
                   help="Per-practice cost estimate, USD (default 0.055)")
    p.add_argument("--target-count", type=int, default=None,
                   help="If set, pick top-N by priority instead of one-per-ZIP")
    p.add_argument("--metro-pattern", type=str, default="%Chicagoland%",
                   help="SQL LIKE pattern for watched_zips.metro_area")
    p.add_argument("--exclude-zip-pattern", type=str, default=None,
                   help="SQL NOT LIKE pattern on practices.zip (e.g. '606%%')")
    return p.parse_args()


def fetch_pool(metro_pattern: str, exclude_zip_pattern: str | None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sql = """
        SELECT p.npi, p.practice_name, p.doing_business_as, p.address, p.city,
               p.state, p.zip, p.entity_type, p.taxonomy_code,
               p.ownership_status, p.entity_classification,
               p.buyability_score, p.year_established, p.employee_count,
               p.estimated_revenue, p.provider_last_name, p.phone, p.website
        FROM practices p
        WHERE p.zip IN (SELECT zip_code FROM watched_zips WHERE metro_area LIKE ?)
    """
    params: list = [metro_pattern]
    if exclude_zip_pattern:
        sql += " AND p.zip NOT LIKE ?"
        params.append(exclude_zip_pattern)
    sql += """
          AND p.ownership_status IN ('independent', 'likely_independent', 'unknown')
          AND p.npi NOT IN (SELECT npi FROM practice_intel)
          AND p.entity_classification IN ('solo_high_volume','solo_established','solo_inactive',
                                           'family_practice','small_group','large_group')
        ORDER BY
            p.zip,
            CASE p.entity_classification
                WHEN 'solo_high_volume' THEN 1
                WHEN 'solo_established' THEN 2
                WHEN 'solo_inactive' THEN 3
                WHEN 'family_practice' THEN 4
                WHEN 'small_group' THEN 5
                WHEN 'large_group' THEN 6
            END,
            p.buyability_score DESC NULLS LAST,
            p.year_established ASC NULLS LAST
    """
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def pick_targets(rows, target_count: int | None):
    if target_count is not None:
        # Top-N by priority — ignore the per-ZIP rotation
        priority_order = {"solo_high_volume": 1, "solo_established": 2, "solo_inactive": 3,
                          "family_practice": 4, "small_group": 5, "large_group": 6}
        sorted_rows = sorted(
            rows,
            key=lambda r: (priority_order.get(r["entity_classification"], 99),
                           -(r["buyability_score"] or 0),
                           r["year_established"] or 9999),
        )
        return [dict(r) for r in sorted_rows[:target_count]]
    seen_zips: set = set()
    picks = []
    for r in rows:
        z = r["zip"]
        if z in seen_zips:
            continue
        seen_zips.add(z)
        picks.append(dict(r))
    return picks


def persist_batch_id(batch_id: str, args):
    """Write batch_id to durable + back-compat locations."""
    data_dir = os.path.join(ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    durable_path = os.path.join(data_dir, "last_batch_id.json")
    payload = {
        "batch_id": batch_id,
        "submitted_at": datetime.now().isoformat(),
        "metro_pattern": args.metro_pattern,
        "exclude_zip_pattern": args.exclude_zip_pattern,
        "target_count": args.target_count,
        "budget_usd": args.budget,
    }
    with open(durable_path, "w") as f:
        json.dump(payload, f, indent=2)
    # Back-compat: poll.py older builds read from /tmp
    tmp_path = "/tmp/full_batch_id.txt"
    with open(tmp_path, "w") as f:
        f.write(batch_id)
    return durable_path, tmp_path


def main():
    args = parse_args()

    rows = fetch_pool(args.metro_pattern, args.exclude_zip_pattern)
    print(f"Pool: {len(rows)} unresearched independents matching {args.metro_pattern}"
          f"{' (excl. ' + args.exclude_zip_pattern + ')' if args.exclude_zip_pattern else ''}")

    picks = pick_targets(rows, args.target_count)
    zip_set = {p["zip"] for p in picks}
    mode = f"top-{args.target_count}" if args.target_count else "top-1-per-ZIP"
    print(f"Picked {mode}: {len(picks)} practices across {len(zip_set)} ZIPs")

    cl = Counter(p["entity_classification"] for p in picks)
    print("\nClassification breakdown:")
    for k in ("solo_high_volume", "solo_established", "solo_inactive",
              "family_practice", "small_group", "large_group"):
        print(f"  {k:<20} {cl.get(k, 0)}")

    print("\nFirst 8 picks:")
    for p in picks[:8]:
        print(f"  {p['zip']} | {(p['practice_name'] or '')[:40]:<40} "
              f"| {p['entity_classification']:<18} | bs={p['buyability_score']}")

    est_cost = len(picks) * args.cost_per_practice
    print(f"\nEstimated cost: ${est_cost:.2f} "
          f"(@ ${args.cost_per_practice}/practice; budget=${args.budget})")

    if est_cost > args.budget:
        print(f"WARN: estimate exceeds ${args.budget} — trimming to fit")
        keep = int(args.budget / args.cost_per_practice)
        picks = picks[:keep]
        print(f"Trimmed to {len(picks)} picks (~${len(picks)*args.cost_per_practice:.2f})")

    items = []
    for p in picks:
        items.append({
            "npi": p["npi"],
            "name": p.get("practice_name", ""),
            "address": p.get("address", ""),
            "city": p.get("city", ""),
            "state": p.get("state", ""),
            "zip": p.get("zip", ""),
            "doctor_name": (p.get("practice_name", "") if p.get("entity_type") == "1"
                            else (f"Dr. {p['provider_last_name']}" if p.get("provider_last_name") else "")),
            "extra_context": build_extra_context(p),
        })

    eng = ResearchEngine(model=MODEL_HAIKU)
    reqs = eng.build_batch_requests(items, "practice")
    print(f"\nBuilt {len(reqs)} batch requests with bulletproofed prompts (force_search=True, max_uses=5)")

    print("Submitting to Anthropic Messages Batch API...")
    result = eng.submit_batch(reqs)
    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    batch_id = result.get("batch_id")
    print(f"\nBATCH SUBMITTED: {batch_id}")
    print(f"   {result.get('count')} requests, status={result.get('status')}")
    durable_path, tmp_path = persist_batch_id(batch_id, args)
    print(f"   batch_id saved to {durable_path}")
    print(f"   batch_id mirrored to {tmp_path} (back-compat)")


if __name__ == "__main__":
    main()
