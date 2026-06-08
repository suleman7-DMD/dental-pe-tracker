"""Phase B1 — Same-name multi-ZIP chain detector (stealth-DSO candidate finder).

A dental brand that operates offices across 3+ distinct watched ZIPs is a
structural signal of a multi-location group/chain — exactly the thing that the
name/EIN classifier misses when a DSO keeps each office's locally-flavored name.
This detector groups watched practices by a NORMALIZED brand key, counts the
distinct ZIPs each brand spans, and emits the multi-ZIP chains as CANDIDATES.

IMPORTANT — this is a *candidate* finder, not a promoter. A shared name alone can
be coincidence (two unrelated "Family Dental Care" offices). So we:
  * require a distinctive (non-generic) token in the brand key,
  * attach corroboration signals (shared EIN / shared parent_company across ZIPs),
  * report the current classification mix (how many offices are ALREADY corporate
    vs still independent — the independents are the opportunity),
and leave the actual independent->corporate promotion to the Phase C verification
gate (web-search confirmation) + reclassify_verified_corporate_il.py.

READ-ONLY: opens its own SQLite connection, runs SELECTs only, writes a JSON
candidate file. Safe to run anytime (never touches practices/zip_scores).

Output: data/dso_research/chain_candidates_b1.json
Usage:  python3 scrapers/detect_name_chains.py [--min-zips 3] [--state IL|MA|all]
"""
import argparse
import json
import os
import re
import sqlite3
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
OUT = os.path.join(ROOT, "data", "dso_research", "chain_candidates_b1.json")

CORPORATE = ("dso_regional", "dso_national")
INDEP = ("solo_established", "solo_new", "solo_inactive", "solo_high_volume",
         "family_practice", "small_group", "large_group", "org_only_npi")

# Legal-form + filler tokens stripped before building the brand key.
LEGAL_SUFFIX = {
    "LTD", "LLC", "PLLC", "PC", "PLC", "INC", "CORP", "CO", "LP", "LLP",
    "PA", "SC", "DDS", "DMD", "MD", "DENTAL", "DENTISTRY", "DENTAL'S",
}
# Tokens that are too generic to identify a chain on their own. A brand key made
# up of ONLY these is dropped (collision-prone). Note "DENTAL"/"DENTISTRY" are in
# LEGAL_SUFFIX above (stripped entirely); these remain in the key but don't count
# as "distinctive".
GENERIC = {
    "CARE", "FAMILY", "GENERAL", "GROUP", "ASSOCIATES", "ASSOCIATION",
    "CENTER", "CENTERS", "CENTRE", "OFFICE", "OFFICES", "SMILE", "SMILES",
    "COSMETIC", "IMPLANT", "IMPLANTS", "MODERN", "GENTLE", "COMPLETE",
    "ADVANCED", "PREMIER", "PROFESSIONAL", "COMMUNITY", "AFFORDABLE",
    "OF", "AND", "THE", "AT", "FOR", "A", "TOTAL", "BRIGHT", "HEALTHY",
    "COMFORT", "CARING", "BEAUTIFUL", "PERFECT", "QUALITY", "TODAY",
    "ARTS", "ART", "STUDIO", "CLINIC", "PRACTICE", "PEDIATRIC", "CHILDREN",
    "CHILDRENS", "ORTHODONTICS", "ORTHODONTIC", "ENDODONTICS", "PERIODONTICS",
    "ORAL", "SURGERY", "MAXILLOFACIAL",
}
_PUNCT = re.compile(r"[^A-Z0-9 ]+")
_WS = re.compile(r"\s+")

# Placeholder/sentinel EINs that Data Axle (and some NPPES rows) emit; matching on
# these would fabricate phantom chains. Mirrors detect_corporate_clusters._clean_ein.
_EIN_JUNK = {"123456789", "987654321", "111111111", "000000000"}


def _clean_ein(v):
    """Normalize an EIN to 9 trailing digits; reject sentinels / degenerate values."""
    if not v:
        return None
    d = re.sub(r"\D", "", str(v))
    if len(d) < 9:
        return None
    d = d[-9:]
    if d in _EIN_JUNK or d == "000000000":
        return None
    # any single digit repeated 6+ times is a placeholder, not a real EIN
    if max(d.count(c) for c in set(d)) >= 6:
        return None
    return d


def _eins_of(m):
    """All distinct, cleaned EINs carried by one member row (primary + DA secondary)."""
    out = set()
    for col in ("ein", "da_ein2", "da_ein3"):
        try:
            v = m[col]
        except (IndexError, KeyError):
            v = None
        e = _clean_ein(v)
        if e:
            out.add(e)
    return out


def _legal_of(m):
    """Cleaned corporate legal-entity name behind a member (da_legal_name)."""
    try:
        v = m["da_legal_name"]
    except (IndexError, KeyError):
        return None
    if not v:
        return None
    s = _WS.sub(" ", str(v).upper()).strip()
    return s or None


def normalize_brand(name):
    """Brand key: uppercase, drop punctuation, drop legal-form tokens, collapse."""
    if not name:
        return None, []
    s = _PUNCT.sub(" ", name.upper())
    s = _WS.sub(" ", s).strip()
    # Drop legal-form tokens AND standalone single letters left over from
    # "P.C."/"S.C."/"P.A." once punctuation is gone (P, C, S, A, ...).
    toks = [t for t in s.split(" ")
            if t and t not in LEGAL_SUFFIX and len(t) > 1]
    if not toks:
        return None, []
    key = " ".join(toks)
    distinctive = [t for t in toks if t not in GENERIC and not t.isdigit()]
    return key, distinctive


def main(min_zips=3, state="all"):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    where_state = "" if state == "all" else f"AND w.state = '{state}'"
    # Phase A backfill populated da_ein2/da_ein3 (secondary tax IDs) and
    # da_legal_name (the corporate legal entity behind a local-name office), plus
    # filled parent_company when it had been NULL. Fold all of them into the
    # corroboration signals so a chain that shares a SECONDARY EIN or a common
    # legal entity across ZIPs is recognised as corporate-corroborated, not just
    # one that happens to share the primary EIN. Columns are absent on a pre-
    # Phase-A DB, so probe the schema and degrade gracefully.
    have = {r[1] for r in conn.execute("PRAGMA table_info(practices)").fetchall()}
    da_ein2 = "p.da_ein2" if "da_ein2" in have else "NULL AS da_ein2"
    da_ein3 = "p.da_ein3" if "da_ein3" in have else "NULL AS da_ein3"
    da_legal = "p.da_legal_name" if "da_legal_name" in have else "NULL AS da_legal_name"
    rows = conn.execute(f"""
        SELECT p.npi, p.practice_name, p.doing_business_as, p.entity_type,
               p.zip, p.city, p.state, p.entity_classification, p.ein,
               p.parent_company, p.address, {da_ein2}, {da_ein3}, {da_legal}
        FROM practices p
        JOIN watched_zips w ON p.zip = w.zip_code
        WHERE p.entity_type = 'organization'
          AND p.practice_name IS NOT NULL
          {where_state}
    """).fetchall()

    # Group by normalized brand key.
    groups = defaultdict(list)
    for r in rows:
        key, distinctive = normalize_brand(r["practice_name"])
        if not key or not distinctive:
            continue  # all-generic / empty -> too collision-prone
        if len(key) < 5:
            continue
        groups[key].append(r)

    candidates = []
    for key, members in groups.items():
        zips = sorted({m["zip"] for m in members})
        if len(zips) < min_zips:
            continue
        # Per-member EIN sets (primary + DA secondary) and legal-entity names.
        member_eins = {m["npi"]: _eins_of(m) for m in members}
        eins = sorted(set().union(*member_eins.values())) if members else []
        parents = sorted({m["parent_company"] for m in members if m["parent_company"]})
        legals = sorted({lg for m in members if (lg := _legal_of(m))})
        classes = defaultdict(int)
        for m in members:
            classes[m["entity_classification"] or "NULL"] += 1
        corp_n = sum(v for k, v in classes.items() if k in CORPORATE)
        indep_n = sum(v for k, v in classes.items() if k in INDEP)
        # Corroboration: the SAME tax ID (primary or DA-secondary) spanning 2+ ZIPs
        # is a strong shared-back-office signal. Also flag a shared corporate legal
        # entity (da_legal_name) appearing across 2+ ZIPs — a DSO holding co behind
        # local-name offices.
        ein_multi_zip = False
        for e in eins:
            ez = {m["zip"] for m in members if e in member_eins[m["npi"]]}
            if len(ez) >= 2:
                ein_multi_zip = True
                break
        legal_multi_zip = False
        for lg in legals:
            lz = {m["zip"] for m in members if _legal_of(m) == lg}
            if len(lz) >= 2:
                legal_multi_zip = True
                break
        candidates.append({
            "brand_key": key,
            "display_name": members[0]["practice_name"],
            "zip_count": len(zips),
            "zips": zips,
            "npi_count": len(members),
            "npis": [m["npi"] for m in members],
            "cities": sorted({m["city"] for m in members if m["city"]}),
            "state": members[0]["state"],
            "class_breakdown": dict(classes),
            "already_corporate": corp_n,
            "still_independent": indep_n,
            "distinct_eins": eins,
            "distinct_parents": parents,
            "distinct_legal_names": legals,
            "shared_ein_multi_zip": ein_multi_zip,
            "shared_legal_multi_zip": legal_multi_zip,
            "shared_parent": len(parents) >= 1,
            # Strength heuristic for the verifier's triage queue. A tax ID OR a
            # corporate legal entity spanning multiple ZIPs, or a named parent, is
            # strong corroboration; a wide-but-unbacked name chain is medium.
            "corroboration": (
                "strong" if (ein_multi_zip or legal_multi_zip or parents) else
                "medium" if len(zips) >= 5 else "weak"),
            "sample_addresses": [
                {"npi": m["npi"], "name": m["practice_name"], "addr": m["address"],
                 "city": m["city"], "zip": m["zip"], "class": m["entity_classification"]}
                for m in members[:8]
            ],
        })
    conn.close()

    # Sort: most ZIPs first, then independents-still-to-capture (the opportunity).
    candidates.sort(key=lambda c: (c["zip_count"], c["still_independent"]), reverse=True)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({
            "generated_by": "detect_name_chains.py (Phase B1)",
            "min_zips": min_zips, "state": state,
            "candidate_count": len(candidates),
            "total_independent_offices_in_chains":
                sum(c["still_independent"] for c in candidates),
            "candidates": candidates,
        }, f, indent=2)

    print(f"B1 chain detector: {len(candidates)} multi-ZIP brand chains "
          f"(>= {min_zips} ZIPs, state={state})")
    print(f"  total still-independent offices inside chains: "
          f"{sum(c['still_independent'] for c in candidates)}")
    print(f"  written -> {OUT}\n")
    print(f"  {'BRAND':<34} {'ZIPs':>4} {'NPIs':>4} {'indep':>5} {'corp':>4}  corrob")
    for c in candidates[:30]:
        print(f"  {c['brand_key'][:34]:<34} {c['zip_count']:>4} {c['npi_count']:>4} "
              f"{c['still_independent']:>5} {c['already_corporate']:>4}  {c['corroboration']}")
    return candidates


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-zips", type=int, default=3)
    ap.add_argument("--state", default="all", choices=["all", "IL", "MA"])
    a = ap.parse_args()
    main(min_zips=a.min_zips, state=a.state)
