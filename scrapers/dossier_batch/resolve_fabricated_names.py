"""
resolve_fabricated_names.py — AI name resolution for fabricated "{Last} Dental" locations.

After the dedup pipeline fix (2026-04-27), 1,344 practice_locations still have
fabricated names because their underlying NPI-1 rows have no org NPI, no DBA,
and no Data Axle match. For these, the only option is to search the web.

KEY INSIGHT: Not every NPI-1 provider owns a practice. Many are associates or
employees at someone else's office. A location with 5 individual NPIs and zero
org NPI is probably a real practice that just never registered an NPI-2. The
fabricated "{Last} Dental" name is wrong — we need the real business name at
that physical address.

Strategy:
  Search 1 (address-based): "dentist {street address} {city} {state}"
  Search 2 (doctor-based):  "Dr. {name} dentist {city} {state}"

The AI cross-references both searches to determine:
  - The actual business name at that address
  - Whether the primary NPI is the owner or an associate

Cost: ~$0.005/practice (2 searches), ~$6.70 total for 1,344.

Usage:
    python3 scrapers/dossier_batch/resolve_fabricated_names.py --dry-run
    python3 scrapers/dossier_batch/resolve_fabricated_names.py --max 50
    python3 scrapers/dossier_batch/resolve_fabricated_names.py
    python3 scrapers/dossier_batch/resolve_fabricated_names.py --budget 8
"""
import argparse
import json
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

COST_PER_PRACTICE = 0.005
DEFAULT_BUDGET = 8.0

NAME_RESOLVE_SYSTEM = """You are a dental practice name resolver. Your job is to find the REAL business name of the dental office at a specific physical address.

CRITICAL CONTEXT:
- The US federal provider registry (NPPES) lists individual dentists by personal name (e.g., "KENNETH KIRSCH"). It does NOT always list the business name.
- Many dentists at an address are ASSOCIATES or EMPLOYEES, not owners. The practice they work at has its own business name.
- A location with multiple dentists and no organization record almost certainly has a real business name — it's just missing from federal data.
- We need the name of the PRACTICE AT THIS ADDRESS, regardless of who owns it.

SEARCH STRATEGY:
1. FIRST search: the street address + city + "dentist" (e.g., "123 Main St Naperville IL dentist")
   This finds the business AT that address — Google Maps, Yelp, Healthgrades listings.
2. SECOND search: "Dr. {name} dentist {city} {state}"
   This finds what practice the named provider is associated with.
3. Cross-reference both results. The address search is MORE authoritative for the business name.

OUTPUT FORMAT (strict JSON, no prose, no markdown):
{
  "business_name": "The Real Practice Name" or null,
  "source_url": "https://primary-source-url" or null,
  "confidence": "high" or "medium" or "low",
  "provider_role": "owner" or "associate" or "unknown",
  "practice_status": "active" or "closed" or "unknown",
  "notes": "brief note — e.g., 'provider is associate at multi-doctor group' or 'address is a hospital dental clinic'"
}

RULES:
- "high" confidence: Practice name confirmed on its own website, Google Business Profile, or multiple directories at the exact address
- "medium" confidence: Name found in one directory listing or insurance page for this address
- "low" confidence: Uncertain — address didn't match cleanly, or conflicting results
- provider_role "owner": search results indicate this doctor owns/founded the practice (solo, name in business name, listed as owner)
- provider_role "associate": doctor appears to work at a practice owned by someone else (listed as "associate", "associate dentist", multiple doctors listed, practice name doesn't match doctor name)
- provider_role "unknown": can't determine from search results
- If the practice genuinely IS named "{Last} Dental" or "{Last} Family Dentistry", return that name — it's a real confirmation
- If the address is a hospital, dental school, community health center, or large clinic, return THAT name (e.g., "Rush University Dental Clinic")
- If practice is closed/retired, set practice_status to "closed" and business_name to the last known name if findable
- NEVER fabricate a name. If searches return nothing useful, return null with "low" confidence"""


def fetch_candidates(conn):
    """Pull fabricated-name locations with their underlying provider info."""
    rows = conn.execute("""
        SELECT pl.location_id, pl.practice_name AS fabricated_name,
               pl.primary_npi, pl.city, pl.state, pl.zip,
               pl.normalized_address, pl.provider_npis, pl.provider_count,
               pl.entity_classification,
               p.practice_name AS nppes_name,
               p.provider_last_name, p.address
        FROM practice_locations pl
        JOIN watched_zips wz ON pl.zip = wz.zip_code
        JOIN practices p ON p.npi = pl.primary_npi
        WHERE pl.practice_name LIKE '% Dental'
          AND pl.has_org_npi = 0
          AND pl.data_axle_enriched = 0
          AND pl.entity_classification NOT IN (
              'specialist','non_clinical','dso_national','dso_regional','org_only_npi'
          )
        ORDER BY
          pl.provider_count DESC,
          pl.zip, pl.practice_name
    """).fetchall()
    return rows


def _all_provider_names(conn, provider_npis_json):
    """Get all provider names at a location for context."""
    try:
        npis = json.loads(provider_npis_json) if provider_npis_json else []
    except (json.JSONDecodeError, TypeError):
        return []
    if not npis:
        return []
    placeholders = ",".join("?" for _ in npis[:10])
    rows = conn.execute(
        f"SELECT practice_name, provider_last_name FROM practices WHERE npi IN ({placeholders})",
        npis[:10],
    ).fetchall()
    return [
        (r["practice_name"] or "").title()
        for r in rows if r["practice_name"]
    ]


def build_batch(candidates, provider_names_map):
    """Build batch requests with address-first search strategy."""
    reqs = []
    for c in candidates:
        nppes = c["nppes_name"] or ""
        parts = nppes.split()
        first = parts[0].title() if parts else "Unknown"
        last = (c["provider_last_name"] or "").title() or (
            parts[-1].title() if len(parts) > 1 else "Unknown"
        )

        street = c["address"] or c["normalized_address"] or ""
        city = c["city"] or ""
        state = c["state"] or ""
        zip_code = c["zip"] or ""
        pcount = c["provider_count"] or 1

        other_names = provider_names_map.get(c["primary_npi"], [])
        other_ctx = ""
        if other_names and len(other_names) > 1:
            other_ctx = (
                f"\nOther dentists registered at this address ({pcount} total): "
                + ", ".join(other_names[:8])
            )
            if len(other_names) > 8:
                other_ctx += f" ... and {len(other_names) - 8} more"

        msg = (
            f"Find the actual dental practice at this address:\n"
            f"  Address: {street}, {city}, {state} {zip_code}\n"
            f"  Primary provider (from federal registry): {nppes.title()}\n"
            f"  Provider count at address: {pcount}\n"
            f"{other_ctx}\n\n"
            f"This provider may be the OWNER or just an ASSOCIATE/EMPLOYEE. "
            f"We need the real business name of whatever dental practice operates "
            f"at this physical address.\n\n"
            f"Search 1: \"{street} {city} {state} dentist\"\n"
            f"Search 2: \"Dr. {first} {last} dentist {city} {state}\""
        )

        reqs.append({
            "custom_id": f"name_{c['primary_npi']}",
            "params": {
                "model": MODEL_HAIKU,
                "max_tokens": 400,
                "system": [{"type": "text", "text": NAME_RESOLVE_SYSTEM,
                            "cache_control": {"type": "ephemeral"}}],
                "tools": [{"type": "web_search_20250305",
                           "name": "web_search", "max_uses": 2}],
                "messages": [{"role": "user", "content": msg}],
                "tool_choice": {"type": "tool", "name": "web_search"},
            },
        })
    return reqs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=None)
    ap.add_argument("--budget", type=float, default=DEFAULT_BUDGET)
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    candidates = fetch_candidates(conn)

    provider_names_map = {}
    for c in candidates:
        names = _all_provider_names(conn, c["provider_npis"])
        provider_names_map[c["primary_npi"]] = names

    conn.close()

    print(f"Pool: {len(candidates)} fabricated-name locations in watched ZIPs")
    if not candidates:
        print("Nothing to resolve.")
        return

    multi = sum(1 for c in candidates if (c["provider_count"] or 1) >= 2)
    solo = len(candidates) - multi
    print(f"  Solo-provider locations:  {solo}")
    print(f"  Multi-provider locations: {multi} (likely associates/groups)")

    if args.max:
        candidates = candidates[:args.max]
        print(f"Capped at --max {args.max}")

    max_by_budget = int(args.budget / COST_PER_PRACTICE)
    if len(candidates) > max_by_budget:
        candidates = candidates[:max_by_budget]
        print(f"Trimmed to {len(candidates)} by budget cap ${args.budget:.2f}")

    est = len(candidates) * COST_PER_PRACTICE
    print(f"\nEstimated cost: ${est:.2f} (@ ${COST_PER_PRACTICE}/practice, "
          f"batch Haiku + 2 searches)")

    print(f"\nSample candidates (sorted by provider count desc):")
    for c in candidates[:10]:
        pc = c["provider_count"] or 1
        print(f"  {c['primary_npi']:>14} | {c['fabricated_name']:<25} | "
              f"{pc:>3} provs | {c['entity_classification']:<18} | "
              f"{c['city']}, {c['state']} {c['zip']}")

    if args.dry_run:
        print(f"\n--dry-run: would submit {len(candidates)} name resolution requests")
        return

    reqs = build_batch(candidates, provider_names_map)
    print(f"\nBuilt {len(reqs)} batch requests (2 web_search each, max_tokens=400)")

    eng = ResearchEngine(model=MODEL_HAIKU)
    print("Submitting to Anthropic Messages Batch API...")
    result = eng.submit_batch(reqs)
    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    batch_id = result.get("batch_id")
    print(f"\nBATCH SUBMITTED: {batch_id}")
    print(f"  {result.get('count')} requests, status={result.get('status')}")

    with open("/tmp/name_resolve_batch_id.txt", "w") as f:
        f.write(batch_id)
    with open("data/name_resolve_batch_id.json", "w") as f:
        json.dump({"batch_id": batch_id, "count": len(reqs)}, f)

    print(f"  batch_id saved to /tmp/name_resolve_batch_id.txt + data/name_resolve_batch_id.json")
    print(f"\nNext steps:")
    print(f"  1. Poll: python3 scrapers/dossier_batch/poll_name_resolve.py")
    print(f"  2. Re-dedup: python3 scrapers/dedup_practice_locations.py")
    print(f"  3. Re-sync: python3 scrapers/sync_to_supabase.py --tables practice_locations")


if __name__ == "__main__":
    main()
