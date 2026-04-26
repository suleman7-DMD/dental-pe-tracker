"""
Priority-zoned 2k launcher (2026-04-26):
  Zone 1 (kendall + adjacent exurbs):    Yorkville, Sugar Grove, Plano, Oswego, Aurora west
  Zone 2 (glenview + north shore):       Glenview, Northbrook, Wilmette, Winnetka, Glencoe,
                                          Highland Park, Deerfield
  Zone 3 (chicago proper):               all 606xx watched ZIPs

Pulls only untouched (NPI not in practice_intel) independents. Targets 2,000
practices total, fills zones in priority order, fills the remaining slots from
zone 3 ranked by entity-classification preference + buyability_score.

Cost cap: $18 (user has ~$20 left after the previous 2k batch). Uses the
calibrated $0.010/practice planning rate from CLAUDE.md cost-calibration block.
"""
import os
import sys
from collections import Counter

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
COST_CAP_USD = 20.0
COST_PER_PRACTICE_EST = 0.008  # post 2026-04-26 console calibration; real cost ~$0.005-0.010/practice

ZONE1_ZIPS = ("60560", "60554", "60545", "60543", "60502", "60503", "60504")
ZONE2_ZIPS = ("60025", "60026", "60062", "60093", "60091", "60022", "60015", "60035")

CLASS_PRIORITY = """
    CASE p.entity_classification
        WHEN 'solo_high_volume' THEN 1
        WHEN 'solo_established' THEN 2
        WHEN 'solo_inactive' THEN 3
        WHEN 'family_practice' THEN 4
        WHEN 'small_group' THEN 5
        WHEN 'large_group' THEN 6
    END
"""

BASE_FILTERS = """
    p.ownership_status IN ('independent', 'likely_independent', 'unknown')
    AND p.npi NOT IN (SELECT npi FROM practice_intel)
    AND p.entity_classification IN (
        'solo_high_volume','solo_established','solo_inactive',
        'family_practice','small_group','large_group'
    )
"""

SELECT_COLS = """
    p.npi, p.practice_name, p.doing_business_as, p.address, p.city,
    p.state, p.zip, p.entity_type, p.taxonomy_code,
    p.ownership_status, p.entity_classification,
    p.buyability_score, p.year_established, p.employee_count,
    p.estimated_revenue, p.provider_last_name, p.phone, p.website
"""


def fetch(conn, zone_clause, label):
    sql = f"""
        SELECT {SELECT_COLS}
        FROM practices p
        WHERE {zone_clause}
          AND {BASE_FILTERS}
        ORDER BY
          {CLASS_PRIORITY},
          p.buyability_score DESC NULLS LAST,
          p.year_established ASC NULLS LAST,
          p.zip
    """
    rows = conn.execute(sql).fetchall()
    print(f"  {label}: {len(rows)} untouched independents")
    return rows


conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print("Counting untouched independents per zone...")
zone1 = fetch(conn, f"p.zip IN {ZONE1_ZIPS}", "Zone 1 (Kendall+adjacent: Yorkville/Sugar Grove/Plano/Oswego/Aurora)")
zone2 = fetch(conn, f"p.zip IN {ZONE2_ZIPS}", "Zone 2 (Glenview+North Shore)")
zone3 = fetch(
    conn,
    f"p.zip LIKE '606%' AND p.zip IN (SELECT zip_code FROM watched_zips)",
    "Zone 3 (Chicago proper 606xx)",
)
conn.close()

# Pack in priority order
picks_z1 = [dict(r) for r in zone1]
picks_z2 = [dict(r) for r in zone2]
picks_z3 = [dict(r) for r in zone3]

remaining = TARGET_COUNT - len(picks_z1) - len(picks_z2)
if remaining < 0:
    remaining = 0
picks_z3 = picks_z3[:remaining]

picks = picks_z1 + picks_z2 + picks_z3
print(f"\nPacked priority queue: {len(picks)} total picks")
print(f"  Zone 1 (Kendall+adjacent): {len(picks_z1)}")
print(f"  Zone 2 (Glenview+North):   {len(picks_z2)}")
print(f"  Zone 3 (Chicago 606xx):    {len(picks_z3)}")

zip_set = {p["zip"] for p in picks}
print(f"  Unique ZIPs covered: {len(zip_set)}")

# Classification breakdown
cl = Counter(p["entity_classification"] for p in picks)
print("\nClassification breakdown:")
for k in (
    "solo_high_volume", "solo_established", "solo_inactive",
    "family_practice", "small_group", "large_group",
):
    print(f"  {k:<20} {cl.get(k, 0)}")

# Sample preview from each zone
print("\nFirst 4 picks per zone:")
for label, pool in (("Zone 1", picks_z1), ("Zone 2", picks_z2), ("Zone 3", picks_z3)):
    print(f"  --- {label} ---")
    for p in pool[:4]:
        print(
            f"    {p['zip']} | {(p['practice_name'] or '')[:40]:<40} "
            f"| {p['entity_classification']:<18} | bs={p['buyability_score']}"
        )

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
        "doctor_name": (
            p.get("practice_name", "") if p.get("entity_type") == "1"
            else (f"Dr. {p['provider_last_name']}" if p.get("provider_last_name") else "")
        ),
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
