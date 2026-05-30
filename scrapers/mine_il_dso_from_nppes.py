"""Mine REAL Illinois DSO locations from NPPES federal data we already hold.

This is the highest-reliability, zero-fabrication DSO source: every IL dental
practice in `practices` carries its federally-registered name + address. We
match those names against the curated DSO brand list (scrapers/dso_brands.py)
to surface every IL location operating under a known DSO brand — no scraping,
no guessing, government-sourced.

Output is a deduped-by-address location set, reported by brand and by watched
ZIP, plus a JSON dump for the downstream seeder. Read-only — writes nothing.
"""
import json
import re
import sqlite3
from collections import defaultdict

from scrapers.dso_brands import KNOWN_DSOS, match_dso_brand

DB = "data/dental_pe_tracker.db"


def norm_addr(addr, zip_):
    """Normalize an address for dedup: lowercase, collapse whitespace, strip
    suite/unit noise so '123 Main St Ste 4' and '123 MAIN STREET, SUITE 4'
    collapse to one location."""
    if not addr:
        return None
    a = addr.lower().strip()
    a = re.sub(r"\b(suite|ste|unit|apt|#|fl|floor|bldg)\b.*$", "", a)
    a = re.sub(r"[^\w\s]", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    return f"{a}|{(zip_ or '')[:5]}"


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    # Watched IL ZIPs (Chicagoland priority scope)
    watched = {r[0] for r in c.execute(
        "SELECT w.zip_code FROM watched_zips w WHERE w.state='IL'")}

    rows = c.execute("""
        SELECT npi, practice_name, doing_business_as, address, city, zip,
               phone, latitude, longitude, parent_company, ein, franchise_name,
               entity_classification, entity_type
        FROM practices
        WHERE state='IL' AND taxonomy_code LIKE '1223%'
    """).fetchall()

    # brand -> {addr_key: location dict}
    by_brand = defaultdict(dict)
    sponsor_of = {}

    for r in rows:
        hit = match_dso_brand(r["practice_name"], r["doing_business_as"])
        if not hit:
            continue
        brand, sponsor = hit
        sponsor_of[brand] = sponsor
        key = norm_addr(r["address"], r["zip"])
        if not key:
            continue
        loc = by_brand[brand].get(key)
        if loc is None:
            by_brand[brand][key] = {
                "dso_name": brand,
                "pe_sponsor": sponsor,
                "address": r["address"],
                "city": r["city"],
                "state": "IL",
                "zip": (r["zip"] or "")[:5],
                "phone": r["phone"],
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "npis": [r["npi"]],
                "source": "nppes_brand_match",
                "in_watched_zip": (r["zip"] or "")[:5] in watched,
            }
        else:
            loc["npis"].append(r["npi"])

    # Flatten + report
    all_locs = []
    print(f"{'BRAND':32} {'IL locs':>8} {'watched':>8}  sponsor")
    print("-" * 78)
    grand = grand_watched = 0
    for brand in sorted(by_brand, key=lambda b: -len(by_brand[b])):
        locs = list(by_brand[brand].values())
        w = sum(1 for l in locs if l["in_watched_zip"])
        grand += len(locs); grand_watched += w
        all_locs.extend(locs)
        sp = sponsor_of.get(brand) or "—"
        print(f"{brand:32} {len(locs):8d} {w:8d}  {sp}")
    print("-" * 78)
    print(f"{'TOTAL':32} {grand:8d} {grand_watched:8d}  ({len(by_brand)} brands)")

    out = "data/il_dso_nppes_mined.json"
    with open(out, "w") as f:
        json.dump(all_locs, f, indent=2)
    print(f"\nWrote {len(all_locs)} deduped IL DSO locations -> {out}")
    print(f"  in watched (Chicagoland) ZIPs: {grand_watched}")


if __name__ == "__main__":
    main()
