"""Merge every REAL Illinois DSO-location source into `dso_locations`.

Zero-fabrication seeder. Unions three independently-sourced, address-level
inputs — all government-data or DSO-own-website derived, none hand-typed:

  1. NPPES brand-mine        data/il_dso_nppes_mined.json
     (federal practice rows whose registered name matches a known DSO brand)
  2. NPPES friendly-PC clusters  expanded live from `practices` for the
     web-search-VERIFIED corporate org names in
     data/dso_research/il_cluster_ownership_verified_20260530.json
     (this is the floor-undercount source: DSOs operating under local P.C.
      names that brand-matching can't see)
  3. Brand-forward web locators  data/dso_research/il_dso_web_locations.json
     (Aspen BFF API, Affordable API, Midwest/1st Family/Dental360 DOM, etc.)

Records are deduped across sources by (normalized street, zip5). The 11
web-search-verified INDEPENDENT groups and 2 unknown clusters are NOT expanded,
so they can never be mislabelled corporate. Output is written into the SQLite
`dso_locations` overlay table (idempotent: prior `il_seed:%` rows are cleared
first; the 202 existing out-of-state ADSO rows are untouched).

This seeds the DSO-office OVERLAY only — it does NOT move the headline corporate
floor. It additionally REPORTS how many currently-independent watched-ZIP GP
locations sit at these verified-corporate addresses, so the user can make the
(gated) decision to reclassify and raise the documented floor toward reality.

Run:  python3 -m scrapers.seed_il_dso_locations
"""
import json
import os
import re
import sqlite3
from collections import defaultdict

DB = "data/dental_pe_tracker.db"
NPPES_MINE = "data/il_dso_nppes_mined.json"
CLUSTERS = "data/dso_research/il_cluster_ownership_verified_20260530.json"
WEB = "data/dso_research/il_dso_web_locations.json"


def norm_addr(addr, zip_):
    """Dedup key: lowercase street, drop suite/unit noise, + zip5."""
    if not addr:
        return None
    a = addr.lower().strip()
    a = re.sub(r"\b(suite|ste|unit|apt|#|fl|floor|bldg|room|rm)\b.*$", "", a)
    a = re.sub(r"[^\w\s]", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    z = (zip_ or "")[:5]
    return f"{a}|{z}" if a else None


_DIRS = {"n", "s", "e", "w", "ne", "nw", "se", "sw", "north", "south",
         "east", "west", "northeast", "northwest", "southeast", "southwest"}


def xref_key(addr, zip_):
    """Abbreviation-proof match key for comparing a DSO street against
    practice_locations.normalized_address: house number + zip5 + first
    non-directional street word (first 6 chars). 'Road' vs 'rd', 'Avenue' vs
    'ave', period/suite noise all collapse out; collisions within one ZIP are
    rare, so a hit is high-confidence."""
    if not addr:
        return None
    a = re.sub(r"[^\w\s]", " ", addr.lower())
    toks = a.split()
    if not toks or not re.match(r"^\d{1,6}$", toks[0]):
        return None
    num = toks[0]
    rest = [t for t in toks[1:] if t not in _DIRS]
    if not rest:
        return None
    z = (zip_ or "")[:5]
    return f"{num}|{z}|{rest[0][:6]}"


def ncore(s):
    """Normalize an org name to its distinctive core (strip punctuation + one
    trailing legal-entity token) for exact-match cluster expansion."""
    s = re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper())
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+(PC|P C|LLC|L L C|LTD|INC|CORP|PLLC|PA|SC)$", "", s).strip()
    return s


def load_json(path):
    if not os.path.exists(path):
        print(f"  (missing: {path})")
        return None
    with open(path) as f:
        return json.load(f)


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    watched = {r[0] for r in c.execute(
        "SELECT zip_code FROM watched_zips WHERE state='IL'")}

    # canonical record: keyed by (norm street, zip). value carries best provenance.
    merged = {}

    def ingest(rec):
        addr = (rec.get("address") or "").strip()
        z = (rec.get("zip") or "")[:5]
        key = norm_addr(addr, z)
        if not key:
            return
        cur = merged.get(key)
        if cur is None:
            rec["_sources"] = {rec["source"]}
            rec["zip"] = z
            rec["in_watched"] = z in watched
            merged[key] = rec
        else:
            cur["_sources"].add(rec["source"])
            # prefer a non-null phone / canonical brand if we lacked one
            if not cur.get("phone") and rec.get("phone"):
                cur["phone"] = rec["phone"]
            if not cur.get("pe_sponsor") and rec.get("pe_sponsor"):
                cur["pe_sponsor"] = rec["pe_sponsor"]

    # ---- Source 1: NPPES brand-mine ----
    n1 = 0
    mine = load_json(NPPES_MINE) or []
    for r in mine:
        if (r.get("state") or "").upper() != "IL":
            continue
        ingest({"dso_name": r["dso_name"], "location_name": None,
                "pe_sponsor": r.get("pe_sponsor"), "address": r["address"],
                "city": r.get("city"), "zip": r.get("zip"), "phone": r.get("phone"),
                "confidence": "high", "source": "nppes_brand"})
        n1 += 1

    # ---- Source 2: verified friendly-PC clusters (expanded from practices) ----
    n2 = 0
    cl = load_json(CLUSTERS) or {}
    clusters = cl.get("clusters", [])
    # build core->cluster map for verified-CORPORATE clusters only
    core_map = {ncore(x["name"]): x for x in clusters}
    il_orgs = c.execute("""
        SELECT npi, practice_name, address, city, zip, phone
        FROM practices
        WHERE state='IL' AND practice_name IS NOT NULL
    """).fetchall()
    for r in il_orgs:
        core = ncore(r["practice_name"])
        hit = core_map.get(core)
        if not hit:
            continue
        ingest({"dso_name": hit["canonical_brand"],
                "location_name": r["practice_name"],
                "pe_sponsor": hit.get("pe_sponsor"), "address": r["address"],
                "city": r["city"], "zip": r["zip"], "phone": r["phone"],
                "confidence": hit.get("confidence", "high"),
                "source": "nppes_cluster"})
        n2 += 1

    # ---- Source 3: brand-forward web locators ----
    n3 = 0
    web = load_json(WEB) or []
    for r in web:
        if (r.get("state") or "").upper() != "IL":
            continue
        ingest({"dso_name": r["dso_name"], "location_name": r.get("office_name"),
                "pe_sponsor": r.get("pe_sponsor"), "address": r.get("address"),
                "city": r.get("city"), "zip": r.get("zip"), "phone": r.get("phone"),
                "confidence": "high", "source": r.get("source", "web_locator")})
        n3 += 1

    locs = list(merged.values())
    watched_locs = [l for l in locs if l["in_watched"]]
    print(f"\nSource rows ingested: nppes_brand={n1}  nppes_cluster={n2}  web_locator={n3}")
    print(f"Deduped IL DSO locations: {len(locs)}  (in watched ZIPs: {len(watched_locs)})")

    # per-brand summary
    by_brand = defaultdict(lambda: [0, 0])
    for l in locs:
        by_brand[l["dso_name"]][0] += 1
        if l["in_watched"]:
            by_brand[l["dso_name"]][1] += 1
    print(f"\n{'DSO BRAND':40} {'IL':>4} {'watched':>8}  sponsor")
    print("-" * 88)
    for b in sorted(by_brand, key=lambda b: -by_brand[b][0]):
        tot, w = by_brand[b]
        sp = next((l["pe_sponsor"] for l in locs
                   if l["dso_name"] == b and l.get("pe_sponsor")), None) or "—"
        print(f"{b[:40]:40} {tot:4d} {w:8d}  {sp}")

    # ---- floor-undercount cross-reference ----
    # how many of these verified-corporate addresses sit at a watched-ZIP
    # location currently classified INDEPENDENT in practice_locations?
    print("\n" + "=" * 88)
    print("FLOOR-UNDERCOUNT CROSS-REFERENCE (watched-ZIP, currently-independent)")
    INDEP = ("solo_established", "solo_new", "solo_inactive", "solo_high_volume",
             "family_practice", "small_group", "large_group")
    # build a lookup of watched-ZIP location addresses + their classification
    ploc = c.execute("""
        SELECT pl.location_id, pl.normalized_address, pl.zip, pl.entity_classification
        FROM practice_locations pl
        JOIN watched_zips w ON substr(pl.zip,1,5)=w.zip_code
        WHERE w.state='IL'
    """).fetchall()
    ploc_by_key = {}
    for r in ploc:
        k = xref_key(r["normalized_address"], r["zip"])
        if k:
            ploc_by_key[k] = r["entity_classification"]
    hits_indep, hits_corp, hits_other, no_match = [], 0, 0, 0
    for l in watched_locs:
        k = xref_key(l["address"], l["zip"])
        ec = ploc_by_key.get(k)
        if ec is None:
            no_match += 1
        elif ec in INDEP:
            hits_indep.append((l, ec))
        elif ec in ("dso_regional", "dso_national"):
            hits_corp += 1
        else:
            hits_other += 1
    print(f"  watched verified-corporate locations:        {len(watched_locs)}")
    print(f"    already classified corporate:              {hits_corp}")
    print(f"    classified INDEPENDENT (floor undercount): {len(hits_indep)}")
    print(f"    other class (specialist/non_clinical):     {hits_other}")
    print(f"    no practice_locations address match:       {no_match}")
    if hits_indep:
        print("\n  Independent-but-actually-corporate (sample, up to 25):")
        for l, ec in hits_indep[:25]:
            print(f"    {l['address'][:34]:34} {l.get('city','')[:16]:16} {l['zip']}"
                  f"  [{ec}] -> {l['dso_name']}")

    # ---- write into SQLite dso_locations (idempotent) ----
    cur = c.cursor()
    cur.execute("DELETE FROM dso_locations WHERE source_url LIKE 'il_seed:%'")
    deleted = cur.rowcount
    ins = 0
    for l in locs:
        prov = (f"il_seed:{'+'.join(sorted(l['_sources']))}"
                f"|conf={l.get('confidence','?')}"
                f"|sponsor={l.get('pe_sponsor') or 'none'}")
        cur.execute("""
            INSERT INTO dso_locations
              (dso_name, location_name, address, city, state, zip, phone,
               scraped_at, source_url)
            VALUES (?,?,?,?,?,?,?,datetime('now'),?)
        """, (l["dso_name"], l.get("location_name"), l["address"],
              l.get("city"), "IL", l["zip"], l.get("phone"), prov))
        ins += 1
    c.commit()
    total_il = c.execute("SELECT COUNT(*) FROM dso_locations WHERE state='IL'").fetchone()[0]
    total_all = c.execute("SELECT COUNT(*) FROM dso_locations").fetchone()[0]
    print("\n" + "=" * 88)
    print(f"WROTE to SQLite dso_locations: cleared {deleted} prior seed rows, "
          f"inserted {ins}.")
    print(f"  dso_locations now: {total_il} IL rows, {total_all} total "
          f"(202 out-of-state ADSO rows preserved).")
    print("  Next: python3 -m scrapers._sync_dso_locations_only   (push to Supabase)")
    c.close()

    # dump the merged set for provenance/inspection
    out = "data/dso_research/il_dso_locations_merged.json"
    for l in locs:
        l["_sources"] = sorted(l["_sources"])
    with open(out, "w") as f:
        json.dump(locs, f, indent=2, default=str)
    print(f"  merged provenance dump -> {out}")


if __name__ == "__main__":
    main()
