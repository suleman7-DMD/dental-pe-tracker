"""Demote 18 web-verified FALSE-corporate watched-IL GP locations back to their
true independent classes, lowering the documented corporate FLOOR accordingly.

Background (2026-06-10 Chicagoland data-integrity audit): a PE-specialist agent
fleet web-verified every suspicious corporate location. Root causes of the false
positives:

  1. EVENLY TECHNOLOGIES ("EVENLY ORTHODONTICS DUPONT") — an orthodontics-in-a-box
     SERVICE PARTNER for independent GPs that owns ZERO practices. Data Axle's
     parent_iusa='000000000' placeholder caused Pass 6 to link 13 independent
     practices to it as a "corporate parent."
  2. Landlord/PE-name confusion — "CALERA CAPITAL" (building landlord, not owner)
     and "JLL PARTNERS" (false positive) on 2 locations.
  3. Bad United Dental Partners seed rows — 2 locations where the UDP locator
     address didn't actually match the practice at that address (e.g., UDP's
     Arlington Heights office is at 1044 W Rand Rd, NOT 201 N Arlington Heights
     Rd where the independent Arlington Heights Dental Group sits).

The corporate number is a documented FLOOR: only hard-evidence locations count.
No hard evidence => independent. Two locations with ambiguous-but-unproven
signals (Favia, Veterans Square) are demoted under that principle and flagged
needs_reverification in the audit file for a future paid verification pass.

3 of the 21 reviewed locations were CONFIRMED corporate and are KEPT (recorded
in the audit file, untouched here).

Writes data/dso_research/il_false_corporate_demotions_20260612.json — both the
audit trail AND the exclusion list that reclassify_verified_corporate_il.py
honors so the 2 demoted locations present in the UDP seed file can never be
re-promoted by a re-run.

Idempotent: only touches rows currently classified dso_regional/dso_national;
after the first run those rows are independent classes, so a re-run finds
nothing to flip and the zip_scores recompute (a COUNT of current dso_* per ZIP)
is stable. Durable: dso_classifier Pass 3 is NULL-only and merge_and_score
recomputes the floor FROM practice_locations, so weekly refresh preserves this.
"""
import json
import sqlite3
import sys

DB = "data/dental_pe_tracker.db"
AUDIT = "data/dso_research/il_false_corporate_demotions_20260612.json"
RUN_DATE = "2026-06-12"

# location_id -> (new entity_classification, evidence, needs_reverification)
DEMOTIONS = {
    "feaa63bd7ced2c0e": ("solo_established",
        "Evenly-only linkage (parent_iusa=000000000 placeholder); Evenly is a service partner, owns no practices", False),
    "4ca83acbcd91a330": ("small_group",
        "Evenly-only linkage; independent multi-doctor office at Oakbrook Center", False),
    "1adac605c6abd972": ("family_practice",
        "Evenly-only linkage; Zaidi brothers' family practice", False),
    "58af66ee2bf4b9c6": ("large_group",
        "Bad UDP seed: UDP's Arlington Heights office is 1044 W Rand Rd, NOT 201 N Arlington Heights Rd; 5-provider independent group", False),
    "5ead583d8354e6e4": ("solo_established",
        "Evenly-only + junk affiliated_dso='General Dentistry'; 0 co-located providers; no corporate evidence (floor principle)", True),
    "e6ce96c5946ab89f": ("solo_established",
        "Bad UDP seed: web-verified independent (Vivirito Dental, Des Plaines)", False),
    "2cb946f04fa11798": ("small_group",
        "Evenly-only linkage", False),
    "42d1dfe2d92fb435": ("small_group",
        "CALERA CAPITAL is the building landlord, not the practice owner; no corporate evidence (floor principle)", True),
    "778740224402dbd4": ("solo_established",
        "Evenly-only linkage", False),
    "d3b3b09cc6ed98dd": ("solo_established",
        "Evenly-only linkage", False),
    "bb925c602eb1ffb6": ("solo_established",
        "Evenly-only linkage", False),
    "06559964fbcc65b8": ("small_group",
        "Evenly-only linkage + junk affiliated_dso='General Dentistry'", False),
    "cdcdf30342969078": ("family_practice",
        "Evenly-only linkage; 3 Bader brothers' family practice", False),
    "c0d81e7b77101c7a": ("small_group",
        "JLL PARTNERS linkage is a false positive; independent office", False),
    "10350cbe9ba08042": ("large_group",
        "Evenly-only linkage; 9-provider independent group", False),
    "4cdf3ef029ab464c": ("solo_established",
        "Evenly-only linkage", False),
    "83edaeef42709b35": ("solo_established",
        "Evenly-only linkage + junk affiliated_dso='General Dentistry'", False),
    "541ae39cadc867b6": ("solo_established",
        "Evenly-only linkage", False),
}

# Org NPIs registered at an address with zero co-located individual providers
# get org_only_npi (billing/admin shell), not the location's clinical class.
ORG_ONLY_NPIS = {"1851083182"}  # Favia Family Dental org NPI, prov_cnt=0

# Reviewed and CONFIRMED corporate — kept, recorded for the audit trail.
KEPT = [
    {"location_id": "ce3f980988601d21", "name": "WHEATLAND SLEEP SOLUTION",
     "evidence": "UDP/Calera confirmed via app.nexhealth.com/appt/unitedentalpartners"},
    {"location_id": "c6078e6641ef7f48", "name": "CHICAGO DENTAL COSMETICS",
     "evidence": "Operating as Advanced Family Dental; United Dental Partners confirmed"},
    {"location_id": "cedf0257b26ccce2", "name": "Oral Health Ctr (Maywood)",
     "evidence": "Loyola Medicine / Trinity Health hospital-affiliated clinic"},
]

CORP = ("dso_regional", "dso_national")


def main(apply=True):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    cur = c.cursor()

    gp, corp0 = c.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    npi0 = c.execute(
        """SELECT COUNT(*) FROM practices p JOIN watched_zips w ON p.zip=w.zip_code
           WHERE p.entity_classification IN ('dso_regional','dso_national')"""
    ).fetchone()[0]
    print(f"BEFORE  corporate floor = {corp0}/{gp} = {100*corp0/gp:.2f}%   corp NPIs = {npi0}")

    audit_rows = []
    npis_to_flip = {}   # npi -> new_ec
    skipped = 0
    for lid, (new_ec, evidence, reverify) in DEMOTIONS.items():
        r = c.execute("""SELECT location_id, practice_name, normalized_address, zip,
                         entity_classification, affiliated_dso, primary_npi, org_npi,
                         provider_npis FROM practice_locations WHERE location_id=?""",
                      (lid,)).fetchone()
        if not r:
            print(f"  !! {lid} MISSING — skipped")
            skipped += 1
            continue
        if r["entity_classification"] not in CORP:
            print(f"  -- {lid} {r['practice_name'][:30]} already {r['entity_classification']} — skipped (idempotent)")
            skipped += 1
            continue

        npis = [r["primary_npi"], r["org_npi"]]
        if r["provider_npis"]:
            try:
                npis += json.loads(r["provider_npis"])
            except Exception:
                pass
        loc_npis = sorted({n for n in npis if n})
        for n in loc_npis:
            npis_to_flip.setdefault(n, "org_only_npi" if n in ORG_ONLY_NPIS else new_ec)

        audit_rows.append({
            "location_id": lid, "name": r["practice_name"], "zip": r["zip"],
            "address": r["normalized_address"],
            "old_class": r["entity_classification"],
            "old_affiliated_dso": r["affiliated_dso"],
            "new_class": new_ec, "evidence": evidence,
            "needs_reverification": reverify, "npis": loc_npis,
        })
        print(f"  [{r['entity_classification']:13}->{new_ec:16}] {r['practice_name'][:34]:34} "
              f"{r['zip'][:5]}  npis={len(loc_npis)}{'  REVERIFY' if reverify else ''}")

    print(f"DEMOTE {len(audit_rows)} locations, flip {len(npis_to_flip)} NPI rows"
          f"{f' ({skipped} skipped)' if skipped else ''}")

    if not apply:
        print("(dry run — nothing written)")
        c.close()
        return

    # ---- practice_locations ----
    for a in audit_rows:
        reason = (f"False-corporate demotion {RUN_DATE}: {a['evidence']}; was "
                  f"{a['old_class']} (2026-06-10 audit: Evenly parent_iusa placeholder / "
                  f"landlord-name / bad-seed false positives). Web-verified independent.")
        cur.execute("""
            UPDATE practice_locations
               SET entity_classification=?, ownership_status='independent',
                   affiliated_dso=NULL, affiliated_pe_sponsor=NULL,
                   classification_reasoning=?, classification_confidence=85,
                   updated_at=datetime('now')
             WHERE location_id=?""", (a["new_class"], reason, a["location_id"]))

    # ---- underlying practices NPIs (only rows currently corporate) ----
    # updated_at bump is REQUIRED: raw sqlite3 bypasses the ORM's onupdate, and a
    # stale updated_at hides the flip from incremental sync + the audit trail.
    flipped = 0
    for npi, new_ec in npis_to_flip.items():
        res = cur.execute("""
            UPDATE practices
               SET entity_classification=?, ownership_status='independent',
                   affiliated_dso=NULL, affiliated_pe_sponsor=NULL,
                   updated_at=datetime('now')
             WHERE npi=? AND entity_classification IN ('dso_regional','dso_national')""",
                          (new_ec, npi))
        flipped += res.rowcount

    # ---- recompute zip_scores from practice_locations (FRACTION scale, the
    # canonical scale per merge_and_score.compute_saturation_metrics) ----
    for r in c.execute("SELECT zip_code FROM zip_scores WHERE state='IL'").fetchall():
        z = r["zip_code"]
        n = c.execute("""SELECT COUNT(*) FROM practice_locations
            WHERE substr(zip,1,5)=? AND entity_classification
            IN ('dso_regional','dso_national')""", (z,)).fetchone()[0]
        cur.execute("""UPDATE zip_scores
            SET corporate_location_count=?,
                corporate_share_pct=CASE WHEN total_gp_locations>0
                    THEN ROUND(1.0*?/total_gp_locations,4) ELSE 0 END
            WHERE zip_code=?""", (n, n, z))
    c.commit()

    gp2, corp1 = c.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores"
    ).fetchone()
    npi1 = c.execute(
        """SELECT COUNT(*) FROM practices p JOIN watched_zips w ON p.zip=w.zip_code
           WHERE p.entity_classification IN ('dso_regional','dso_national')"""
    ).fetchone()[0]
    print(f"AFTER   corporate floor = {corp1}/{gp2} = {100*corp1/gp2:.2f}%  "
          f"({corp1-corp0:+d} locations)   corp NPIs = {npi1} ({npi1-npi0:+d})")
    print(f"  practices NPI rows flipped: {flipped}")

    with open(AUDIT, "w") as f:
        json.dump({
            "run_date": RUN_DATE,
            "summary": ("18 false-corporate watched-IL GP locations demoted to verified "
                        "independent classes; 3 reviewed locations confirmed corporate and "
                        "kept. Root causes: Evenly Technologies parent_iusa=000000000 "
                        "placeholder (x13), landlord/PE-name confusion (x2), bad UDP seed "
                        "rows (x2), no-hard-evidence floor principle (x2 of the above, "
                        "flagged needs_reverification)."),
            "floor_before": {"corporate": corp0, "gp": gp, "pct": round(100*corp0/gp, 2)},
            "floor_after": {"corporate": corp1, "gp": gp2, "pct": round(100*corp1/gp2, 2)},
            "npi_corporate_before": npi0, "npi_corporate_after": npi1,
            "demotions": audit_rows,
            "kept_corporate": KEPT,
            "_note": ("reclassify_verified_corporate_il.py excludes every location_id in "
                      "'demotions' from future promotion runs — 2 of these (58af66ee2bf4b9c6, "
                      "e6ce96c5946ab89f) appear in the UDP seed file and would otherwise be "
                      "re-promoted."),
        }, f, indent=1)
    print(f"  audit + exclusion file written: {AUDIT}")
    print("\nNEXT: bump FLOOR/FLOOR_NPI guards in scripts/check_data_invariants.py,")
    print("      recompute CONFIRMED_PER_DENTIST_CORPORATE, then sync floor tables to Supabase.")
    c.close()


if __name__ == "__main__":
    main(apply="--dry-run" not in sys.argv)
