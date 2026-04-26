"""
launch_DA_prefix_only.py — Re-research bulletproofing fix for DA_ Data-Axle-only rows.

Audit B1 (2026-04-26) found that DA_-prefix synthetic-NPI rows in `practice_intel`
predate the anti-hallucination rollout — they were imported before forced-search,
per-claim _source_url, and the verification block were enforced. The honest
target for re-research is rows whose stored verification_quality is
"insufficient" — those clearly never went through the gate.

This script:
  1. Reads DA_-prefix rows with verification_quality='insufficient'
  2. Looks up their address/name/state from `practices`
  3. Builds a bulletproofed Haiku batch (force_search, max_uses=5, _source_url required)
  4. Submits

Cost model: $0.008/practice (calibrated 2026-04-26 in CLAUDE.md), so the 41
target rows should clear ~$0.33. Budget cap set to $5 for headroom.
"""
import os
import sys

ROOT = "/Users/suleman/dental-pe-tracker"
sys.path.insert(0, ROOT)
for raw in open(os.path.join(ROOT, ".env")):
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import sqlite3
from scrapers.research_engine import ResearchEngine, MODEL_HAIKU
from scrapers.database import DB_PATH
from scrapers.practice_deep_dive import build_extra_context


COST_PER_PRACTICE = 0.008
COST_CAP_USD = 5.0


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT p.npi, p.practice_name, p.doing_business_as, p.address, p.city,
               p.state, p.zip, p.entity_type, p.taxonomy_code,
               p.ownership_status, p.entity_classification,
               p.buyability_score, p.year_established, p.employee_count,
               p.estimated_revenue, p.provider_last_name, p.phone, p.website
          FROM practices p
          JOIN practice_intel pi ON pi.npi = p.npi
         WHERE p.npi LIKE 'DA_%'
           AND pi.verification_quality = 'insufficient'
    """).fetchall()
    conn.close()

    print(f"Pool: {len(rows)} DA_-prefix dossiers with verification_quality='insufficient'")
    if not rows:
        print("Nothing to re-research. Exit.")
        return

    est = len(rows) * COST_PER_PRACTICE
    print(f"Estimated cost: ${est:.2f} (@ ${COST_PER_PRACTICE}/practice, batch+bulletproof)")

    if est > COST_CAP_USD:
        keep = int(COST_CAP_USD / COST_PER_PRACTICE)
        rows = rows[:keep]
        print(f"WARN: estimate exceeds ${COST_CAP_USD} cap — trimming to {len(rows)} rows")

    items = []
    for p in rows:
        items.append({
            "npi": p["npi"],
            "name": p["practice_name"] or "",
            "address": p["address"] or "",
            "city": p["city"] or "",
            "state": p["state"] or "",
            "zip": p["zip"] or "",
            "doctor_name": (p["practice_name"] or "" if p["entity_type"] == "1"
                            else (f"Dr. {p['provider_last_name']}" if p["provider_last_name"] else "")),
            "extra_context": build_extra_context(dict(p)),
        })

    eng = ResearchEngine(model=MODEL_HAIKU)
    reqs = eng.build_batch_requests(items, "practice")
    print(f"Built {len(reqs)} bulletproofed batch requests")

    print("Submitting...")
    result = eng.submit_batch(reqs)
    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    batch_id = result.get("batch_id")
    print(f"\n✅ BATCH SUBMITTED: {batch_id}")
    print(f"   {result.get('count')} requests, status={result.get('status')}")
    with open("/tmp/da_rerun_batch_id.txt", "w") as f:
        f.write(batch_id)
    print("   batch_id saved to /tmp/da_rerun_batch_id.txt")
    print("\nNext: `python3 scrapers/dossier_batch/poll.py` — but first edit poll.py "
          "to read /tmp/da_rerun_batch_id.txt instead of /tmp/full_batch_id.txt.")


if __name__ == "__main__":
    main()
