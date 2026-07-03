"""
READ-ONLY. Build the targeted evidence-gathering queue for the evidence-first census
(per Codex's 2026-06-21 handoff). Opens the DB read-only (mode=ro) — ZERO writes, so it
is safe to run while Codex stabilizes the DB. Emits three target sets the agents turn
into documentary evidence rows:

  dso_suspects : IL GP locations whose name/dba/affiliated_dso/parent_company hits a known
                 DSO/PE brand fragment -> exact-address locator confirmation candidates.
  ao_clusters  : authorized officials owning >=2 distinct watched-IL GP locations
                 (dentist_multi / network candidates; PE tie must be web-confirmed for stealth).
  intel_leads  : IL GP NPIs with a practice_intel dossier (verified/partial) mentioning
                 ownership / DSO / group / acquisition language -> URL extraction candidates.

Output: data/dso_research/ownership_evidence_targets_20260621.json
The agents read THIS file and write evidence to data/dso_research/ownership_evidence_queue_*.json.
No ownership_tier is written by anything in this lane.
"""
import json
import os
import re
import sqlite3
from collections import defaultdict

ROOT = "/Users/suleman/dental-pe-tracker"
DB = f"file:{os.path.join(ROOT, 'data', 'dental_pe_tracker.db')}?mode=ro"
OUT = os.path.join(ROOT, "data", "dso_research", "ownership_evidence_targets_20260621.json")

EXCLUDED = {"specialist", "non_clinical", "da_unverified", "org_only_npi", "duplicate_location"}

# Known DSO / PE brand fragments (lowercased substring). A HINT — the agent must confirm
# exact-address against the official locator before any branded_dso/stealth_dso final.
BRANDS = {
    "heartland": ("Heartland Dental", "KKR"),
    "dental professionals of illinois": ("Heartland Dental (friendly-PC)", "KKR"),
    "tru dental": ("Heartland Dental (friendly-PC)", "KKR"),
    "aspen dental": ("Aspen Dental", "ADMI/Leonard Green"),
    "dental dreams": ("Dental Dreams", None),
    "dental experts": ("Dental Dreams (Dental Experts LLC)", None),
    "western dental": ("Western Dental (Sonrava)", "New Mountain"),
    "great lakes dental": ("Great Lakes Dental Partners", "Shore Capital"),
    "great expressions": ("Great Expressions", None),
    "1st family": ("1st Family Dental", None),
    "first family dental": ("1st Family Dental", None),
    "all family": ("All Family Dental (UDP)", None),
    "dental 360": ("Dental 360", None),
    "brite": ("Brite Dental", None),
    "webster": ("Webster Dental", None),
    "comfort dental": ("Comfort Dental", None),
    "midwest dental": ("Midwest Dental", "Gryphon"),
    "smile brands": ("Smile Brands", "Gryphon"),
    "decisionone": ("DecisionOne Dental (Smile Brands)", "Gryphon"),
    "pacific dental": ("Pacific Dental Services", None),
    "dental care alliance": ("Dental Care Alliance", None),
    "family dental care": ("Family Dental Care", None),
    "familydental": ("Family Dental Care", None),
    "precision dental": ("Precision Dental Care", None),
    "destiny": ("Destiny Dental / ProSmile", "ProSmile sponsor"),
    "prosmile": ("ProSmile", None),
    "sonrisa": ("Sonrisa Dental", None),
    "dentologie": ("Dentologie", None),
    "park place": ("Park Place Dental (multi-brand)", None),
}
INSTITUTIONAL = ["fqhc", "community health", "health center", "hospital", "medical center",
                 "university", "county", "veterans", "school of dental", "public health",
                 "infant welfare", "lurie", "cook county", " v a "]
# generic surnames that should NOT alone anchor an AO cluster (too common)
GENERIC_AO = {"", "DENTAL", "SMILE", "FAMILY", "PATEL", "SMITH", "LEE", "KIM", "PARK",
              "CHEN", "KWON", "SHAH", "NGUYEN"}
INTEL_TERMS = ["dso", "acqui", "merg", "partner", "group", "private equity", " pe ",
               "platform", "consolidat", "msо", "mso", "backed", "sold", "joined"]


def norm(s):
    return (s or "").strip().lower()


def main():
    c = sqlite3.connect(DB, uri=True)
    c.row_factory = sqlite3.Row
    il_zips = [r[0] for r in c.execute("SELECT zip_code FROM watched_zips WHERE state='IL'")]
    qm = ",".join("?" * len(il_zips))
    exq = ",".join("?" * len(EXCLUDED))
    locs = c.execute(f"""
        SELECT location_id, zip, city, normalized_address, practice_name, doing_business_as,
               primary_npi, org_npi, phone, ein, entity_classification, affiliated_dso,
               parent_company, provider_count, year_established, ownership_tier
        FROM practice_locations
        WHERE state='IL' AND zip IN ({qm}) AND entity_classification NOT IN ({exq})
    """, il_zips + sorted(EXCLUDED)).fetchall()

    # AO lookup per npi
    npis = set()
    for r in locs:
        for k in ("primary_npi", "org_npi"):
            if r[k]:
                npis.add(str(r[k]))
    ao_by_npi, intel_by_npi = {}, {}
    if npis:
        nq = ",".join("?" * len(npis))
        for r in c.execute(f"""SELECT npi, authorized_official_last_name l,
                authorized_official_first_name f FROM practices WHERE npi IN ({nq})""", list(npis)):
            ao_by_npi[str(r["npi"])] = (norm(r["l"]).upper(), norm(r["f"]).upper())
        # discover practice_intel columns at runtime (schema-agnostic)
        cur = c.execute("SELECT * FROM practice_intel LIMIT 0")
        intel_cols = [d[0] for d in cur.description]
        text_cols = [col for col in intel_cols if col not in ("id", "npi", "created_at", "updated_at")]
        sel = ",".join(["npi"] + text_cols)
        for r in c.execute(f"SELECT {sel} FROM practice_intel WHERE npi IN ({nq})", list(npis)):
            blob = " ".join(str(r[col]).strip().lower() for col in r.keys()
                            if col != "npi" and r[col] is not None)
            vq = (r["verification_quality"] if "verification_quality" in r.keys() else "") or ""
            if any(t in blob for t in INTEL_TERMS):
                intel_by_npi[str(r["npi"])] = {"verification_quality": vq,
                                               "hit_terms": sorted({t.strip() for t in INTEL_TERMS if t in blob})}

    def ao_of(row):
        for k in ("primary_npi", "org_npi"):
            if row[k] and str(row[k]) in ao_by_npi:
                ao = ao_by_npi[str(row[k])]
                if ao[0] and ao[0] not in GENERIC_AO:
                    return ao
        return None

    ao_locs = defaultdict(list)
    for r in locs:
        ao = ao_of(r)
        if ao:
            ao_locs[ao].append(r)

    def brand_of(row):
        hay = " ".join(norm(row[k]) for k in
                       ("practice_name", "doing_business_as", "affiliated_dso", "parent_company"))
        for frag, (label, sponsor) in BRANDS.items():
            if frag in hay:
                return {"brand": label, "pe_sponsor": sponsor, "matched_fragment": frag}
        return None

    def inst_of(row):
        hay = " " + " ".join(norm(row[k]) for k in ("practice_name", "doing_business_as")) + " "
        return any(f in hay for f in INSTITUTIONAL)

    def base(row):
        return {
            "location_id": row["location_id"], "name": row["practice_name"],
            "dba": row["doing_business_as"], "address": row["normalized_address"],
            "city": row["city"], "zip": row["zip"], "phone": row["phone"],
            "ein": (row["ein"] or None), "primary_npi": row["primary_npi"],
            "org_npi": row["org_npi"], "entity_classification": row["entity_classification"],
            "affiliated_dso": row["affiliated_dso"], "parent_company": row["parent_company"],
            "provider_count": row["provider_count"], "year_established": row["year_established"],
        }

    dso_suspects, institutional = [], []
    for r in locs:
        b = brand_of(r)
        if b:
            rec = base(r); rec["brand_hint"] = b
            dso_suspects.append(rec)
        if inst_of(r):
            institutional.append(base(r))

    ao_clusters = []
    for ao, members in ao_locs.items():
        if len(members) >= 2:
            zips = sorted({m["zip"] for m in members})
            ao_clusters.append({
                "authorized_official": f"{ao[1]} {ao[0]}".strip(),
                "network_id": f"ao:{ao[0]}_{ao[1]}".strip("_"),
                "reach": len(members), "zips": zips,
                "locations": [base(m) for m in members],
            })
    ao_clusters.sort(key=lambda x: -x["reach"])

    intel_leads = []
    for r in locs:
        for k in ("primary_npi", "org_npi"):
            npi = str(r[k]) if r[k] else None
            if npi and npi in intel_by_npi:
                rec = base(r); rec["intel"] = intel_by_npi[npi]; rec["intel_npi"] = npi
                intel_leads.append(rec)
                break

    out = {
        "_meta": {
            "date": "2026-06-21", "read_only_source": True,
            "il_gp_rows": len(locs),
            "counts": {"dso_suspects": len(dso_suspects), "ao_clusters": len(ao_clusters),
                       "ao_cluster_locations": sum(len(x["locations"]) for x in ao_clusters),
                       "institutional": len(institutional), "intel_leads": len(intel_leads)},
            "rule": "Agents confirm exact address+ZIP against official sources; emit documentary "
                    "evidence rows only. No DB writes in this lane. No ADA anchor. IL only.",
        },
        "dso_suspects": dso_suspects,
        "ao_clusters": ao_clusters,
        "institutional": institutional,
        "intel_leads": intel_leads,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {OUT}")
    print(json.dumps(out["_meta"]["counts"], indent=2))
    print("\nTop AO clusters (reach desc):")
    for x in ao_clusters[:12]:
        print(f"  {x['authorized_official']:<28} reach={x['reach']} zips={x['zips']}")


if __name__ == "__main__":
    main()
