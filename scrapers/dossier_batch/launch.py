"""
Top-1-per-ZIP launcher: pick the single highest-priority unresearched independent
practice in each Chicagoland watched ZIP, submit as one batch with the new
bulletproofed prompts.
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

# Pull all unresearched independents in Chicagoland, sorted by priority.
# Then in Python, pick first row per ZIP.
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT p.npi, p.practice_name, p.doing_business_as, p.address, p.city,
           p.state, p.zip, p.entity_type, p.taxonomy_code,
           p.ownership_status, p.entity_classification,
           p.buyability_score, p.year_established, p.employee_count,
           p.estimated_revenue, p.provider_last_name, p.phone, p.website
    FROM practices p
    WHERE p.zip IN (SELECT zip_code FROM watched_zips WHERE metro_area LIKE '%Chicagoland%')
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
""").fetchall()
conn.close()

print(f"Pool: {len(rows)} unresearched independents across Chicagoland")

# Pick first row per ZIP
seen_zips = set()
picks = []
for r in rows:
    z = r["zip"]
    if z in seen_zips:
        continue
    seen_zips.add(z)
    picks.append(dict(r))

print(f"Picked top 1 per ZIP: {len(picks)} practices across {len(seen_zips)} ZIPs")

# Sanity sample
print("\nFirst 10 picks:")
for p in picks[:10]:
    print(f"  {p['zip']} | {(p['practice_name'] or '')[:35]:<35} "
          f"| {p['entity_classification']:<18} | bs={p['buyability_score']}")

# Estimate cost (5 cents/practice from the test batch)
est_cost = len(picks) * 0.055
print(f"\nEstimated cost: ${est_cost:.2f} (@ $0.055/practice)")

if est_cost > 11.0:
    print(f"WARN: estimate exceeds $11 buffer — trimming to fit")
    keep = int(11.0 / 0.055)
    picks = picks[:keep]
    print(f"Trimmed to {len(picks)} picks (~${len(picks)*0.055:.2f})")

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
print(f"\nBuilt {len(reqs)} batch requests with bulletproofed prompts")

# Submit
print("Submitting...")
result = eng.submit_batch(reqs)
if "error" in result:
    print(f"ERROR: {result['error']}")
    sys.exit(1)

batch_id = result.get("batch_id")
print(f"\n✅ BATCH SUBMITTED: {batch_id}")
print(f"   {result.get('count')} requests, status={result.get('status')}")
# Persist batch_id for downstream poller — use data/ so it survives ephemeral /tmp
_batch_id_path = os.path.join(ROOT, "data", "last_batch_id.txt")
with open(_batch_id_path, "w") as f:
    f.write(batch_id)
print(f"   batch_id saved to {_batch_id_path}")
