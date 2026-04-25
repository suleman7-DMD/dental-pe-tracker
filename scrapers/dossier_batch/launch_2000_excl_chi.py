"""
Big-pool launcher: 2000 unresearched independent Chicagoland practices,
EXCLUDING Chicago proper (zip LIKE '606%'). Priority-ordered, bulletproofed prompts.
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

TARGET_COUNT = 2000
COST_CAP_USD = 250.0
COST_PER_PRACTICE_EST = 0.080  # conservative; April-25 run was $0.075/practice

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT p.npi, p.practice_name, p.doing_business_as, p.address, p.city,
           p.state, p.zip, p.entity_type, p.taxonomy_code,
           p.ownership_status, p.entity_classification,
           p.buyability_score, p.year_established, p.employee_count,
           p.estimated_revenue, p.provider_last_name, p.phone, p.website
    FROM practices p
    WHERE p.zip IN (SELECT zip_code FROM watched_zips WHERE metro_area LIKE '%Chicago%')
      AND p.zip NOT LIKE '606%'
      AND p.ownership_status IN ('independent', 'likely_independent', 'unknown')
      AND p.npi NOT IN (SELECT npi FROM practice_intel)
      AND p.entity_classification IN ('solo_high_volume','solo_established','solo_inactive',
                                       'family_practice','small_group','large_group')
    ORDER BY
        CASE p.entity_classification
            WHEN 'solo_high_volume' THEN 1
            WHEN 'solo_established' THEN 2
            WHEN 'solo_inactive' THEN 3
            WHEN 'family_practice' THEN 4
            WHEN 'small_group' THEN 5
            WHEN 'large_group' THEN 6
        END,
        p.buyability_score DESC NULLS LAST,
        p.year_established ASC NULLS LAST,
        p.zip
""").fetchall()
conn.close()

print(f"Pool: {len(rows)} unresearched independents (Chicagoland, excl. 606xx Chicago proper)")

picks = [dict(r) for r in rows[:TARGET_COUNT]]
zip_set = {p["zip"] for p in picks}
print(f"Picked top {len(picks)} by priority across {len(zip_set)} ZIPs")

# Classification breakdown
from collections import Counter
cl = Counter(p["entity_classification"] for p in picks)
print("\nClassification breakdown:")
for k in ("solo_high_volume", "solo_established", "solo_inactive",
         "family_practice", "small_group", "large_group"):
    print(f"  {k:<20} {cl.get(k, 0)}")

# Sample preview
print("\nFirst 8 picks:")
for p in picks[:8]:
    print(f"  {p['zip']} | {(p['practice_name'] or '')[:40]:<40} "
          f"| {p['entity_classification']:<18} | bs={p['buyability_score']}")

# Cost estimate
est_cost = len(picks) * COST_PER_PRACTICE_EST
print(f"\nEstimated cost: ${est_cost:.2f} (@ ${COST_PER_PRACTICE_EST}/practice; cap=${COST_CAP_USD})")

if est_cost > COST_CAP_USD:
    print(f"WARN: estimate exceeds ${COST_CAP_USD} — trimming to fit")
    keep = int(COST_CAP_USD / COST_PER_PRACTICE_EST)
    picks = picks[:keep]
    print(f"Trimmed to {len(picks)} picks (~${len(picks)*COST_PER_PRACTICE_EST:.2f})")

# Build batch items
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
with open("/tmp/full_batch_id.txt", "w") as f:
    f.write(batch_id)
print(f"   batch_id written to /tmp/full_batch_id.txt (poll.py reads from there)")
