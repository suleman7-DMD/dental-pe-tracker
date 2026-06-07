"""Phase B7 — IDFPR Professional-Service-Corporation registry cross-reference.

Illinois' Corporate Practice of Dentistry rule forces DSOs into a friendly-PC
structure: a locally-named Professional Service Corporation owned on paper by a
captive dentist, run via a management agreement with the MSO. Every such PC must
hold an IDFPR "PROF SERVICE CORP" license. That registry is a free, no-key
Socrata dataset (data.illinois.gov/resource/pzzh-kp68.json) exposing the PC's
legal business_name + city/ZIP — 13,259 PSCs statewide, ~1,663 dental-named.

PSC presence alone does NOT prove corporate ownership — most dental PSCs are
ordinary independent practices that simply incorporated. So this detector does
NOT promote anything. It produces three CORROBORATION signals for the Phase C
verifier:

  1. multi_city_chains — the SAME PSC business_name licensed in 2+ distinct
     cities. A single legal entity operating across cities is a structural
     multi-location signal (e.g. "GROVE DENTAL ASSOCIATES PC" at both Wheaton
     and Downers Grove = NADG's Grove Dental, confirmed in the DSO scoreboard).
  2. watched_name_matches — PSC names whose normalized brand key matches a
     watched practice's name OR doing-business-as, annotated with that
     practice's current entity_classification. Cross-references BOTH the PSC's
     legal business_name AND its businessdba against BOTH the watched practice's
     practice_name AND doing_business_as — so a friendly-PC registered under
     either string is caught. Lets the verifier confirm a candidate is a real
     registered PC entity (and find its sibling offices).
  3. dba_brand_reveals — the strongest CPOD-pierce. Illinois requires the PC to
     register the assumed name (DBA) it operates under. When that DBA — or the
     legal name itself — contains a KNOWN national/regional DSO brand from the
     canonical registry (dso_brands.py), the locally-named PC is unmasked as
     that DSO's captive entity (e.g. "IL JUDGE DENTAL P.C. DBA ASPEN DENTAL",
     "TRU DENTAL ILLINOIS PC DBA TRU FAMILY DENTAL" = Heartland,
     "D2 DENTAL OF JEFFERY PC DBA DESTINY DENTAL" = Destiny). Also surfaces
     multi-entity clusters where 2+ distinct legal names share one DBA.

READ-ONLY. Hits the public Socrata API (no key) + opens SQLite SELECT-only.
Network-tolerant: on API failure it writes an empty result with an error note
rather than raising. Output: data/dso_research/psc_candidates_b7.json

Usage: python3 scrapers/detect_psc_registry.py [--include-lapsed]
"""
import argparse
import json
import os
import sqlite3
import urllib.parse
import urllib.request
from collections import defaultdict

from detect_name_chains import normalize_brand  # shared brand normalizer
from dso_brands import match_dso_brand  # canonical DSO-brand registry (name+dba aware)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
OUT = os.path.join(ROOT, "data", "dso_research", "psc_candidates_b7.json")
SOCRATA = "https://data.illinois.gov/resource/pzzh-kp68.json"

# Dental-relevant name tokens. PSC license type is profession-agnostic, so we
# filter to dental/ortho/specialty-named entities.
NAME_KEYWORDS = ("DENTAL", "DENTIST", "ORTHODON", "ENDODON", "PERIODON",
                 "PROSTHODON", "PEDODON", "ORAL SURG", "MAXILLOFACIAL", "SMILE",
                 "TOOTH", "TEETH", "DDS", "DMD")

# match_dso_brand() is a loose substring matcher (shared with the live
# classifier, which we must not alter mid-pipeline). It happily matches
# "midwest dental" inside "MIDWEST DENTAL SLEEP CENTER" — a solo dental-sleep-
# medicine practice that is NOT the Midwest Dental DSO. These descriptor tokens,
# when present, recharacterize the entity as an ancillary/descriptive practice
# rather than a DSO retail office, so they VETO a DBA brand reveal. Phase C would
# catch the false positive anyway, but this keeps the high tier trustworthy.
NON_DSO_CONTEXT = {"SLEEP", "LAB", "LABORATORY", "SUPPLY", "SUPPLIES", "ACADEMY",
                   "SCHOOL", "COLLEGE", "UNIVERSITY", "SOCIETY", "ASSOCIATION",
                   "FOUNDATION", "MUSEUM", "SEMINAR", "ANESTHESIA", "RADIOLOGY",
                   "PATHOLOGY", "BILLING"}


def _has_non_dso_context(*names):
    toks = set()
    for n in names:
        if n:
            toks |= {t for t in str(n).upper().replace(",", " ").split()}
    return bool(toks & NON_DSO_CONTEXT)


def fetch_dental_psc(include_lapsed=False):
    """Paginate the Socrata API for dental-named PROF SERVICE CORP rows."""
    like = " OR ".join(
        f"upper(business_name) like '%25{k.replace(' ', '%20')}%25'"
        for k in NAME_KEYWORDS)
    where = f"({like})"
    if not include_lapsed:
        where += " AND license_status='ACTIVE'"
    rows, offset, page = [], 0, 1000
    for _ in range(20):  # hard cap: 20k rows
        params = {
            "license_type": "PROF SERVICE CORP",
            "$where": where,
            "$select": "business_name,businessdba,city,state,zip,county,"
                       "license_status,original_issue_date",
            "$limit": page, "$offset": offset,
            "$order": "business_name",
        }
        url = SOCRATA + "?" + urllib.parse.urlencode(params, safe="()%'")
        req = urllib.request.Request(url, headers={"User-Agent": "dental-pe-tracker/B7"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            batch = json.loads(resp.read().decode("utf-8"))
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return rows


def main(include_lapsed=False):
    result = {
        "generated_by": "detect_psc_registry.py (Phase B7)",
        "source": SOCRATA, "include_lapsed": include_lapsed,
    }
    try:
        psc = fetch_dental_psc(include_lapsed)
    except Exception as e:
        result.update({"error": f"socrata fetch failed: {e}", "dental_psc_count": 0,
                       "multi_city_chains": [], "watched_name_matches": []})
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w") as f:
            json.dump(result, f, indent=2)
        print(f"B7 PSC detector: API FETCH FAILED ({e}). Wrote empty result -> {OUT}")
        return result

    # Group PSCs by normalized brand key.
    by_brand = defaultdict(list)
    for r in psc:
        key, distinctive = normalize_brand(r.get("business_name"))
        if not key or not distinctive:
            continue
        by_brand[key].append(r)

    # Signal 1: same brand key licensed across 2+ distinct cities.
    multi_city = []
    for key, members in by_brand.items():
        cities = sorted({(m.get("city") or "").upper() for m in members if m.get("city")})
        if len(cities) >= 2:
            multi_city.append({
                "brand_key": key,
                "display_name": members[0].get("business_name"),
                "city_count": len(cities),
                "cities": cities,
                "zips": sorted({(m.get("zip") or "")[:5] for m in members if m.get("zip")}),
                "statuses": sorted({m.get("license_status") for m in members}),
                "row_count": len(members),
            })
    multi_city.sort(key=lambda c: c["city_count"], reverse=True)

    # Signal 2: cross-ref vs watched practices by normalized brand key. We index
    # watched orgs under BOTH their practice_name key AND their doing_business_as
    # key, and probe with BOTH the PSC's business_name AND businessdba keys — so
    # a friendly-PC registered under either string matches either string.
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    watched = conn.execute("""
        SELECT p.npi, p.practice_name, p.doing_business_as, p.zip, p.city,
               p.entity_classification
        FROM practices p JOIN watched_zips w ON p.zip = w.zip_code
        WHERE p.entity_type='organization' AND p.practice_name IS NOT NULL
          AND w.state='IL'
    """).fetchall()
    conn.close()
    watched_by_key = defaultdict(dict)  # key -> {npi: row}  (dedup multi-key hits)
    for r in watched:
        for src in (r["practice_name"], r["doing_business_as"]):
            key, distinctive = normalize_brand(src)
            if key and distinctive:
                watched_by_key[key][r["npi"]] = dict(r)

    name_matches = []
    seen_match_keys = set()
    for psc_key, members in by_brand.items():
        # probe keys: the brand key from business_name (psc_key) plus the key
        # derived from businessdba on any member row.
        probe = {psc_key}
        for m in members:
            dk, dd = normalize_brand(m.get("businessdba"))
            if dk and dd:
                probe.add(dk)
        matched = {}
        for pk in probe:
            for npi, row in watched_by_key.get(pk, {}).items():
                matched[npi] = row
        if not matched:
            continue
        dedup_key = (psc_key, tuple(sorted(matched)))
        if dedup_key in seen_match_keys:
            continue
        seen_match_keys.add(dedup_key)
        wm = list(matched.values())
        cities = sorted({(m.get("city") or "").upper() for m in members if m.get("city")})
        name_matches.append({
            "brand_key": psc_key,
            "psc_name": members[0].get("business_name"),
            "psc_dbas": sorted({m.get("businessdba") for m in members
                                if m.get("businessdba")}),
            "psc_cities": cities,
            "psc_multi_city": len(cities) >= 2,
            "watched_matches": [
                {"npi": m["npi"], "name": m["practice_name"],
                 "dba": m.get("doing_business_as"), "zip": m["zip"],
                 "city": m["city"], "class": m["entity_classification"]}
                for m in wm
            ],
            "still_independent": sum(
                1 for m in wm if (m["entity_classification"] or "") not in
                ("dso_regional", "dso_national")),
        })
    name_matches.sort(key=lambda c: (c["psc_multi_city"], c["still_independent"]),
                      reverse=True)

    # Signal 3: dba_brand_reveals — PSC rows whose legal name OR DBA contains a
    # KNOWN DSO brand from the canonical registry. This is the cleanest
    # CPOD-pierce: the assumed name the captive PC operates under is the DSO's
    # public brand. Each hit is a confirmed friendly-PC candidate for Phase C.
    brand_reveals = []
    by_dba = defaultdict(list)  # normalized DBA key -> rows (multi-entity cluster)
    for r in psc:
        bn = r.get("business_name")
        dba = r.get("businessdba")
        hit = match_dso_brand(bn, dba)
        # Veto substring collisions: an ancillary/descriptive entity (e.g.
        # "MIDWEST DENTAL SLEEP CENTER") is not the DSO it shares a token with.
        if hit and _has_non_dso_context(bn, dba):
            hit = None
        # We only want rows where the DSO brand is the REVEAL — i.e. the brand
        # token isn't already the obvious legal name. match_dso_brand already
        # covers both; record the matched canonical + which field carried it.
        if hit:
            canon, sponsor = hit
            in_name = match_dso_brand(bn) is not None
            in_dba = bool(dba) and match_dso_brand(None, dba) is not None
            brand_reveals.append({
                "business_name": bn,
                "businessdba": dba,
                "matched_dso": canon,
                "pe_sponsor": sponsor,
                "revealed_by": "dba" if (in_dba and not in_name) else
                               ("name" if in_name and not in_dba else "both"),
                "city": (r.get("city") or "").upper(),
                "zip": (r.get("zip") or "")[:5],
                "status": r.get("license_status"),
            })
        # cluster: distinct legal names sharing one assumed name
        if dba:
            dkey, ddist = normalize_brand(dba)
            if dkey and ddist:
                by_dba[dkey].append(r)
    brand_reveals.sort(key=lambda x: (x["matched_dso"], x["city"]))

    shared_dba_clusters = []
    for dkey, rows in by_dba.items():
        names = sorted({(r.get("business_name") or "").upper() for r in rows
                        if r.get("business_name")})
        cities = sorted({(r.get("city") or "").upper() for r in rows if r.get("city")})
        if len(names) >= 2:  # 2+ distinct legal entities under one DBA
            dba_disp = rows[0].get("businessdba")
            md = match_dso_brand(None, dba_disp)
            if md and _has_non_dso_context(dba_disp):
                md = None
            shared_dba_clusters.append({
                "dba_key": dkey,
                "dba_display": dba_disp,
                "distinct_legal_names": names,
                "legal_name_count": len(names),
                "cities": cities,
                "matched_dso": (md or (None, None))[0],
            })
    shared_dba_clusters.sort(key=lambda c: c["legal_name_count"], reverse=True)

    result.update({
        "dental_psc_count": len(psc),
        "multi_city_chain_count": len(multi_city),
        "watched_name_match_count": len(name_matches),
        "dba_brand_reveal_count": len(brand_reveals),
        "shared_dba_cluster_count": len(shared_dba_clusters),
        "multi_city_chains": multi_city[:120],
        "watched_name_matches": name_matches[:200],
        "dba_brand_reveals": brand_reveals,
        "shared_dba_clusters": shared_dba_clusters[:80],
    })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)

    print(f"B7 PSC detector: {len(psc)} dental PSC rows "
          f"({'incl lapsed' if include_lapsed else 'ACTIVE only'})")
    print(f"  multi-city chains: {len(multi_city)}   watched name-matches: {len(name_matches)}")
    print(f"  DBA brand reveals: {len(brand_reveals)}   shared-DBA clusters: {len(shared_dba_clusters)}")
    print(f"  written -> {OUT}\n")
    print(f"  --- DBA brand reveals (known-DSO unmasked friendly-PCs) ---")
    for c in brand_reveals[:24]:
        nm = (c["business_name"] or "")[:34]
        dba = (c["businessdba"] or "")[:22]
        print(f"  {nm:<34} DBA {dba:<22} -> {c['matched_dso']:<24} "
              f"[{c['revealed_by']}] {c['city']}")
    print(f"\n  --- shared-DBA clusters (2+ legal entities, one DBA) ---")
    for c in shared_dba_clusters[:12]:
        tag = f"-> {c['matched_dso']}" if c["matched_dso"] else ""
        print(f"  {(c['dba_display'] or '')[:34]:<34} {c['legal_name_count']:>2} entities "
              f"{','.join(c['cities'][:3]):<28} {tag}")
    print(f"\n  --- top multi-city PSC chains ---")
    for c in multi_city[:14]:
        print(f"  {c['brand_key'][:40]:<40} {c['city_count']:>2} cities  "
              f"{','.join(c['cities'][:4])}")
    print(f"\n  --- watched name-matches (still-independent first) ---")
    for c in name_matches[:14]:
        flag = "MULTI-CITY" if c["psc_multi_city"] else ""
        print(f"  {c['brand_key'][:38]:<38} indep={c['still_independent']:>2} "
              f"matches={len(c['watched_matches']):>2} {flag}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-lapsed", action="store_true",
                    help="include NOT RENEWED / lapsed PSC licenses")
    a = ap.parse_args()
    main(include_lapsed=a.include_lapsed)
