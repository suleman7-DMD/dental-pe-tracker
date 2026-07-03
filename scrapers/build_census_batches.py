"""
Build ownership-census batches for the agent teams. READ-ONLY.
For a set of IL watched ZIPs, emit every GP location with PRE-COMPUTED ownership
context from the federal data, so research agents spend web searches only on the
hard last mile (stealth-DSO / multi-location confirmation), not on facts the data
already settles.

Per practice context:
  base       : location_id, npis, name, dba, address, city, zip, phone, ein,
               authorized official, entity_classification, affiliated_dso,
               parent_company, year_established, provider_count
  owner_reach: # distinct watched-IL GP locations sharing this authorized official
               (the mini-DSO / dentist_multi signal) + the ZIPs they span
  ein_reach  : # distinct locations sharing this EIN across >=2 ZIPs
  brand_hint : matched known DSO/PE brand (from name/dba/affiliated_dso/parent_company)
  has_intel  : whether a practice_intel dossier exists for the primary NPI

Output: data/dso_research/census_batches_<date>.json
Usage:  python3 scrapers/build_census_batches.py [--zips 60614,60622,...] [--max N]
"""
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

ROOT = "/Users/suleman/dental-pe-tracker"
DB = os.path.join(ROOT, "data", "dental_pe_tracker.db")
DATE = "20260620"
OUT = os.path.join(ROOT, "data", "dso_research", f"census_batches_{DATE}.json")
HOME = os.path.join(ROOT, "data", "dso_research", "RESEARCH_HOME")
LEDGER = os.path.join(HOME, "LEDGER.jsonl")  # canonical census done-state (NOT DB ownership_tier)
CHUNK = 18  # practices per agent batch

EXCLUDED = {"specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location"}

# Known DSO / PE brand fragments (lowercased substring match). NOT proof — a hint
# the agent must confirm. Ortho-only brands are tagged so agents exclude them from GP.
BRANDS = {
    "heartland": ("Heartland Dental", "KKR", False),
    "aspen dental": ("Aspen Dental", "ADMI/Leonard Green", False),
    "dental dreams": ("Dental Dreams", None, False),
    "western dental": ("Western Dental (Sonrava)", "New Mountain", False),
    "great lakes dental": ("Great Lakes Dental Partners", "Shore Capital", False),
    "great expressions": ("Great Expressions", None, False),
    "1st family": ("1st Family Dental", None, False),
    "first family dental": ("1st Family Dental", None, False),
    "all family": ("All Family Dental (UDP)", None, False),
    "dental 360": ("Dental 360", None, False),
    "brite": ("Brite Dental", None, False),
    "webster": ("Webster Dental", None, False),
    "comfort dental": ("Comfort Dental", None, False),
    "midwest dental": ("Midwest Dental", "Gryphon", False),
    "smile brands": ("Smile Brands", None, False),
    "pacific dental": ("Pacific Dental Services", None, False),
    "dental care alliance": ("Dental Care Alliance", None, False),
    "familydental": ("Family Dental Care", None, False),
    "family dental care": ("Family Dental Care", None, False),
    "dentology": ("Dentology", None, False),
    "precision dental": ("Precision Dental Care", None, False),
    "orthodontic experts": ("Orthodontic Experts", None, True),
    "smile doctors": ("Smile Doctors", None, True),
}
# Institutional fragments
INSTITUTIONAL = ["fqhc", "community health", "health center", "hospital", "medical center",
                 "university", "county", "v a ", "veterans", "school of dental",
                 "public health", "infant welfare", "lurie", "cook county"]

GENERIC_AO = {"", "DENTAL", "SMILE", "FAMILY", "PATEL", "SMITH", "LEE", "KIM", "PARK"}


def norm(s):
    return (s or "").strip().lower()


def ledger_classified_location_ids():
    """Canonical census done-state = VERIFIED LEDGER rows, NOT DB ownership_tier.

    HAZARD FIX (2026-06-21): this script previously treated
    `practice_locations.ownership_tier IS NOT NULL` as "already classified" for
    --exclude-classified. That is unsafe: the DB ownership_tier column can hold
    candidate / unverified writes, and the 2026-06-21 reset cleared 349 such
    candidate rows to NULL. The append-only LEDGER is the source of truth.

    A location counts as classified (and is excluded from re-batching) only when it
    has a LEDGER line with status == 'classified'. Rows that are 'undetermined' or
    'needs_verification' are deliberately NOT excluded — they must be re-queued for
    more work, per CENSUS_PROTOCOL.

    Returns (set_of_location_ids, ledger_has_real_rows: bool).
    """
    ids = set()
    real_rows = 0
    if not os.path.exists(LEDGER):
        return ids, False
    with open(LEDGER) as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            if not isinstance(rec, dict) or "_meta" in rec:
                continue  # skip the schema/header line
            lid = rec.get("location_id")
            if not lid:
                continue
            real_rows += 1
            if rec.get("status") == "classified":
                ids.add(lid)
    return ids, real_rows > 0


def main():
    target_zips = None
    cap = None
    all_il = False
    exclude_classified = False
    out_override = None
    for i, a in enumerate(sys.argv):
        if a == "--zips" and i + 1 < len(sys.argv):
            target_zips = [z.strip() for z in sys.argv[i + 1].split(",") if z.strip()]
        if a == "--max" and i + 1 < len(sys.argv):
            cap = int(sys.argv[i + 1])
        if a == "--all-il":
            all_il = True
        if a == "--exclude-classified":   # skip locations whose ownership_tier is already set
            exclude_classified = True
        if a == "--out" and i + 1 < len(sys.argv):
            out_override = sys.argv[i + 1]

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    il_zips = [r[0] for r in c.execute("SELECT zip_code FROM watched_zips WHERE state='IL'")]

    if all_il:
        target_zips = list(il_zips)
    if not target_zips:
        # Wave-1 default: dense/affluent zero-corp ZIPs (likely-missed corporate) +
        # known-corporate calibration ZIPs.
        target_zips = ["60614", "60622", "60068", "60062", "60187", "60005",
                       "60565", "60634", "60302", "60540"]

    # location_ids already classified through the census — skip them. SOURCE OF
    # TRUTH = the verified LEDGER (status=='classified' rows), NOT DB ownership_tier.
    # DB ownership_tier is unsafe as a done-state: it can hold candidate/unverified
    # writes and is wiped by a reset (2026-06-21). See ledger_classified_location_ids().
    done_ids = set()
    if exclude_classified:
        done_ids, ledger_has_rows = ledger_classified_location_ids()
        if not ledger_has_rows:
            print("WARNING: --exclude-classified requested but the LEDGER has no rows "
                  "(header-only / missing). Excluding NOTHING. DB ownership_tier is "
                  "intentionally NOT used as census done-state.", file=sys.stderr)
        else:
            print(f"--exclude-classified: excluding {len(done_ids)} location_ids with a "
                  f"status=='classified' LEDGER row (LEDGER-based, not DB ownership_tier).")
    qm = ",".join("?" * len(il_zips))
    exq = ",".join("?" * len(EXCLUDED))

    # ── global context maps over ALL watched-IL GP locations ──────────────
    # location -> authorized official (from primary_npi, fallback org_npi)
    locs = c.execute(f"""
        SELECT pl.location_id, pl.zip, pl.city, pl.normalized_address, pl.practice_name,
               pl.doing_business_as, pl.primary_npi, pl.org_npi, pl.phone, pl.ein,
               pl.entity_classification, pl.affiliated_dso, pl.parent_company,
               pl.provider_count, pl.year_established
        FROM practice_locations pl
        WHERE pl.state='IL' AND pl.zip IN ({qm})
          AND pl.entity_classification NOT IN ({exq})
    """, il_zips + sorted(EXCLUDED)).fetchall()

    # AO lookup per npi
    npis = set()
    for r in locs:
        if r["primary_npi"]:
            npis.add(str(r["primary_npi"]))
        if r["org_npi"]:
            npis.add(str(r["org_npi"]))
    ao_by_npi = {}
    intel_npis = set()
    if npis:
        nq = ",".join("?" * len(npis))
        for r in c.execute(f"""SELECT npi, authorized_official_last_name l,
                authorized_official_first_name f FROM practices WHERE npi IN ({nq})""",
                list(npis)):
            ao_by_npi[str(r["npi"])] = (norm(r["l"]).upper(), norm(r["f"]).upper())
        for r in c.execute(f"SELECT DISTINCT npi FROM practice_intel WHERE npi IN ({nq})", list(npis)):
            intel_npis.add(str(r["npi"]))

    def ao_of(row):
        for k in (row["primary_npi"], row["org_npi"]):
            if k and str(k) in ao_by_npi:
                ao = ao_by_npi[str(k)]
                if ao[0] and ao[0] not in GENERIC_AO:
                    return ao
        return None

    # owner reach: AO -> set(location_id), set(zip)
    ao_locs = defaultdict(set)
    ao_zips = defaultdict(set)
    ein_locs = defaultdict(set)
    ein_zips = defaultdict(set)
    for r in locs:
        ao = ao_of(r)
        if ao:
            ao_locs[ao].add(r["location_id"])
            ao_zips[ao].add(r["zip"])
        e = (r["ein"] or "").strip()
        if e and e not in ("0", "000000000", "00-0000000"):
            ein_locs[e].add(r["location_id"])
            ein_zips[e].add(r["zip"])

    def brand_of(row):
        hay = " ".join(norm(row[k]) for k in
                       ("practice_name", "doing_business_as", "affiliated_dso", "parent_company"))
        for frag, (label, sponsor, is_ortho) in BRANDS.items():
            if frag in hay:
                return {"brand": label, "pe_sponsor": sponsor, "is_ortho": is_ortho}
        return None

    def institutional_hint(row):
        hay = " " + " ".join(norm(row[k]) for k in ("practice_name", "doing_business_as")) + " "
        return any(frag in hay for frag in INSTITUTIONAL)

    # ── assemble batches for target ZIPs ──────────────────────────────────
    zip_city = {r["location_id"]: r["city"] for r in locs}
    by_zip = defaultdict(list)
    for r in locs:
        if r["zip"] not in target_zips:
            continue
        if r["location_id"] in done_ids:   # already classified in a prior wave
            continue
        ao = ao_of(r)
        ein = (r["ein"] or "").strip()
        rec = {
            "location_id": r["location_id"],
            "primary_npi": r["primary_npi"], "org_npi": r["org_npi"],
            "name": r["practice_name"], "dba": r["doing_business_as"],
            "address": r["normalized_address"], "city": r["city"], "zip": r["zip"],
            "phone": r["phone"], "ein": ein or None,
            "entity_classification": r["entity_classification"],
            "affiliated_dso": r["affiliated_dso"], "parent_company": r["parent_company"],
            "provider_count": r["provider_count"], "year_established": r["year_established"],
            "ctx": {
                "authorized_official": (f"{ao[1]} {ao[0]}".strip() if ao else None),
                "owner_reach_locations": (len(ao_locs[ao]) if ao else 1),
                "owner_reach_zips": (sorted(ao_zips[ao]) if ao else [r["zip"]]),
                "ein_reach_locations": (len(ein_locs[ein]) if ein in ein_locs else (1 if ein else 0)),
                "ein_reach_zips": (sorted(ein_zips[ein]) if ein in ein_zips else []),
                "brand_hint": brand_of(r),
                "institutional_hint": institutional_hint(r),
                "has_intel_dossier": (str(r["primary_npi"]) in intel_npis if r["primary_npi"] else False),
            },
        }
        by_zip[r["zip"]].append(rec)

    # chunk into agent batches
    batches = []
    total = 0
    for z in target_zips:
        rows = by_zip.get(z, [])
        if cap and total >= cap:
            break
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i:i + CHUNK]
            if cap and total + len(chunk) > cap:
                chunk = chunk[:cap - total]
            if not chunk:
                continue
            batches.append({
                "batch_id": f"{z}-{i//CHUNK+1}",
                "zip": z, "city": chunk[0]["city"], "n": len(chunk),
                "practices": chunk,
            })
            total += len(chunk)

    out = {
        "_meta": {"date": DATE, "target_zips": target_zips, "chunk_size": CHUNK,
                  "n_batches": len(batches), "n_practices": total, "read_only_source": True,
                  "excluded_already_classified": len(done_ids)},
        "batches": batches,
    }
    out_path = out_override or OUT
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {out_path}")
    print(f"ZIPs={len(target_zips)}  batches={len(batches)}  practices={total}")
    # brand/institutional/multi-loc preview
    nb = sum(1 for b in batches for p in b["practices"] if p["ctx"]["brand_hint"])
    ni = sum(1 for b in batches for p in b["practices"] if p["ctx"]["institutional_hint"])
    nm = sum(1 for b in batches for p in b["practices"] if p["ctx"]["owner_reach_locations"] >= 2)
    print(f"brand_hint={nb}  institutional_hint={ni}  multi_loc_owner(>=2)={nm}")


if __name__ == "__main__":
    main()
