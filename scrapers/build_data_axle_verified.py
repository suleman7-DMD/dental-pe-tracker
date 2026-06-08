#!/usr/bin/env python3
"""Phase 4: turn the verified subset of the Data-Axle-powered flip queue into the
il_dso_data_axle_verified.json promotion file that reclassify_verified_corporate_il
unions and applies.

Every location written here cleared a documentary-evidence bar (recorded per row in
`_evidence`):
  * HIGH tier  : known PE/DSO brand, web-verified (Heartland/ProSmile/Dental Dreams/DCA).
  * da_corporate_parent: the NPI's OWN parent_company/da_legal_name IS a known DSO.
  * EIN cluster: a Data Axle tax ID shared across 3+ ZIPs, EITHER web-confirmed as a
    multi-location operator OR validated by >=1 already-corporate member at that EIN
    (proves the EIN is a real corporate operator's, not a building/billing artifact).

Adversarially REJECTED (NOT written) and why — recorded in the file's `_rejected`:
  * EIN 363676741 (Mt Prospect): Pollina (Suite 4, pediatric) + Ryan (Suite 9, perio)
    are SEPARATE specialty practices in one building; shared EIN is a building/Data-Axle
    artifact, single-ZIP, not a chain.
  * DAMAIL 1730 Park St #106 (Two Rivers mgmt office): shared *mailing* only, 0 already-
    corporate corroboration; only 1 of 4 members (Two Rivers Elgin) is confirmable —
    the rest could share a third-party billing service. Held for paid verification.

Output schema mirrors il_dso_locations_merged.json so reclassify can union it:
  {dso_name, address (= the location's normalized_address), zip, in_watched,
   pe_sponsor, _sources, _evidence}
"""
import json
import sqlite3

from scrapers.seed_il_dso_locations import xref_key

DB = "data/dental_pe_tracker.db"
QUEUE = "data/dso_research/flip_queue_b_union.json"
B2 = "data/dso_research/cluster_candidates_b2.json"
OUT = "data/dso_research/il_dso_data_axle_verified.json"

GP_INDEP = {"solo_established", "solo_new", "solo_inactive", "solo_high_volume",
            "family_practice", "small_group", "large_group"}
CORP = ("dso_regional", "dso_national")

# EIN clusters confirmed corporate (brand assigned manually from web verification /
# already-corporate members). pe_sponsor None => dentist-owned regional group
# (ownership_status 'dso-affiliated', still corporate for the floor).
EIN_CLUSTERS = {
    "363554595": {"brand": "Family Dental Care", "sponsor": None,
                  "why": "web: largest privately-owned dental group in Chicago, 8 loc/50+ docs (familydentalcare.com); 16 already-corporate members at this EIN"},
    "731689410": {"brand": "Dental 360 / Brite Dental", "sponsor": None,
                  "why": "web: Dental 360 (15 loc) + Brite Dental (multi-loc Pulaski/Belmont/Kimball); 5 already-corporate members at this EIN"},
    "465833863": {"brand": "Precision Dental Care", "sponsor": None,
                  "why": "web: 6-location LLC chain under Dr R. Chang (Belmont/Pulaski/Ashland/Cermak/Diversey); numbered-LLC franchise pattern, shared EIN 3+ ZIPs"},
    "471741822": {"brand": "Park Place Dental Group (multi-brand)", "sponsor": None,
                  "why": "multi-brand stealth DSO: Park Place Dental + Village Smiles + Meadow Lake Dental already corporate at this EIN; Second Street/Parker/PPD share it across 3 cities"},
    "204557390": {"brand": "Sonrisa Family Dental (Community Dental Centers of America)", "sponsor": None,
                  "why": "web: Community Dental Centers of America operates 11 offices under local names incl. Sonrisa Family Dental; 2 already-corporate Sonrisa members at this EIN"},
}
# EIN clusters adversarially rejected.
EIN_REJECTED = {
    "363676741": "Mt Prospect single-building: Pollina (pediatric, Ste 4) + Ryan (perio, Ste 9) are separate specialty practices; shared EIN is a building/Data-Axle artifact, single-ZIP, not a chain.",
}
MAILING_REJECTED = {
    "DAMAIL:1730 PARK ST 106 60563": "Two Rivers mgmt office; shared mailing only, 0 already-corporate corroboration; only Two Rivers Elgin confirmable of 4 members. Held for paid verification.",
}


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    q = json.load(open(QUEUE))["candidates"]
    b2raw = json.load(open(B2))
    clusters = b2raw["clusters"] if isinstance(b2raw, dict) else b2raw

    # candidate index by npi (GP-indep, still-independent location only)
    cand = {x["npi"]: x for x in q
            if x.get("location_id") and x["location_current_class"] in GP_INDEP}

    # location_id -> {brand, sponsor, source_tag, evidence}
    promote = {}

    def add(npi, brand, sponsor, source_tag, evidence):
        x = cand.get(npi)
        if not x:
            return
        lid = x["location_id"]
        if lid in promote:
            promote[lid]["evidence"].setdefault("npis", []).append(npi)
            return
        promote[lid] = {
            "location_id": lid, "name": x.get("name"),
            "brand": brand, "sponsor": sponsor, "source_tag": source_tag,
            "evidence": {"queue_tier": x["tier"], "signals": x.get("signals"),
                         "da_structural_kinds": x.get("da_structural_kinds"),
                         "why": evidence, "npis": [npi]},
        }

    # (1) HIGH tier — brand web-verified DSOs (GP-indep only; specialists excluded by filter)
    for x in q:
        if x["tier"] != "high":
            continue
        if x["location_current_class"] not in GP_INDEP:
            continue
        add(x["npi"], x.get("proposed_dso") or "Verified DSO (high tier)",
            x.get("pe_sponsor"), "data_axle_structural_verified",
            f"HIGH tier brand web-verified ({'+'.join(x.get('signals') or [])})")

    # (2) MEDIUM da_corporate_parent — NPI's OWN parent/legal name IS a known DSO
    for x in q:
        if x["tier"] != "medium":
            continue
        if x["location_current_class"] not in GP_INDEP:
            continue
        if "da_corporate_parent" in (x.get("da_structural_kinds") or []) and x.get("proposed_dso"):
            add(x["npi"], x["proposed_dso"], x.get("pe_sponsor"),
                "data_axle_structural_verified",
                "da_corporate_parent: own parent_company/da_legal_name matched a known DSO")

    # (3) EIN clusters — validated corporate tax IDs
    for cl in clusters:
        co = cl.get("corroboration") or {}
        key = cl.get("cluster_key") or ""
        # extract EIN from DAEIN:NNN or EIN:NNN keys
        ein = key.split(":", 1)[1] if ":" in key else None
        if ein not in EIN_CLUSTERS:
            continue
        meta = EIN_CLUSTERS[ein]
        for npi in cl.get("all_npis") or []:
            add(npi, meta["brand"], meta["sponsor"], "data_axle_structural_verified",
                f"shared EIN {ein}: {meta['why']}")

    # Build a watched-IL practice_locations xref index (mirrors reclassify's
    # first-wins map) so we can annotate each verified row with whether its
    # building (xref_key) ALREADY carries a corporate sibling row — those
    # corroborate the detection but are already counted in the location-deduped
    # floor, so reclassify (correctly) won't double-count them.
    xref_corp = {}
    for r in c.execute("""SELECT pl.normalized_address, pl.zip, pl.entity_classification
        FROM practice_locations pl JOIN watched_zips w ON substr(pl.zip,1,5)=w.zip_code
        WHERE w.state='IL'"""):
        k = xref_key(r["normalized_address"], r["zip"])
        if k and r["entity_classification"] in CORP:
            xref_corp[k] = r["entity_classification"]

    # ---- emit in MERGED schema (address = location's normalized_address) ----
    out = []
    new_promotions = 0
    already_counted = 0
    for lid, p in promote.items():
        r = c.execute("""SELECT normalized_address, zip, entity_classification, city
                         FROM practice_locations WHERE location_id=?""", (lid,)).fetchone()
        if not r:
            continue
        if r["entity_classification"] not in GP_INDEP:
            continue  # already corporate — skip (idempotent)
        k = xref_key(r["normalized_address"], r["zip"])
        sibling_corp = xref_corp.get(k)
        if sibling_corp:
            xref_status = "already_corporate_at_building"  # corroborates, won't add to floor
            already_counted += 1
        else:
            xref_status = "new_promotion"  # adds 1 to the location-deduped floor
            new_promotions += 1
        out.append({
            "dso_name": p["brand"],
            "address": r["normalized_address"],
            "zip": r["zip"],
            "city": r["city"],
            "in_watched": True,
            "pe_sponsor": p["sponsor"],
            "_sources": [p["source_tag"]],
            "_evidence": p["evidence"],
            "_location_id": lid,
            "_was": r["entity_classification"],
            "_xref_status": xref_status,
            "_sibling_corp_class": sibling_corp,
        })

    payload = {
        "generated_by": "build_data_axle_verified.py (Phase 4)",
        "note": ("Verified-corporate IL GP locations surfaced by the Data-Axle-powered "
                 "detector fleet (B1 name-chain + B2 EIN/parent + B7 PSC) and confirmed "
                 "by free WebSearch and/or already-corporate EIN members. Every row "
                 "carries documentary evidence in _evidence. Adversarially-rejected "
                 "clusters listed in _rejected."),
        "verified_location_count": len(out),
        "new_promotions": new_promotions,
        "already_corporate_at_building": already_counted,
        "_xref_note": ("new_promotions add to the location-deduped floor; "
                       "already_corporate_at_building rows are detector-CORROBORATED "
                       "but share an xref_key with an existing dso_* sibling row, so "
                       "they're already counted — reclassify (first-wins xref) holds "
                       "them out to keep the floor strictly location-deduped."),
        "_rejected": {**{f"EIN:{k}": v for k, v in EIN_REJECTED.items()},
                      **MAILING_REJECTED},
        "locations": out,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)

    # ---- audit print ----
    from collections import Counter
    by_brand = Counter(o["dso_name"] for o in out)
    print(f"Wrote {len(out)} verified-corporate GP-indep locations -> {OUT}")
    print(f"  new_promotions (add to floor):            {new_promotions}")
    print(f"  already_corporate_at_building (corrob.):  {already_counted}\n")
    print("By brand:")
    for b, n in by_brand.most_common():
        print(f"  {n:3}  {b}")
    print(f"\nRejected clusters: {len(EIN_REJECTED)+len(MAILING_REJECTED)} "
          f"({', '.join(list(EIN_REJECTED)+list(MAILING_REJECTED))})")
    c.close()


if __name__ == "__main__":
    main()
