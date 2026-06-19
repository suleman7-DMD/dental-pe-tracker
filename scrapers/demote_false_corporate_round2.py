"""Round-2 false-corporate demotions + attribution corrections (2026-06-12).

Follow-up to demote_false_corporate_il.py (round 1). Every verdict here was
web-verified inline during the 2026-06-12 Chicagoland reality audit; sources
are recorded per row in the audit JSON this script writes.

What it does, in one auditable pass:
  1. DEMOTE 7 web-verified false-corporate locations (Gryphon/Shore EIN-crosswalk
     contamination + nonexistent-chain name matches) corporate -> independent or
     specialist, flipping their underlying dso_* NPI rows to match.
  2. KEEP-with-correction: rows whose corporate status is documentary (DSO's own
     locator page / press release) but whose affiliated_dso held a PE FUND name
     (GRYPHON INVESTORS / SHORE CAPITAL PARTNERS LLC) instead of the DSO brand —
     fund name moves to affiliated_pe_sponsor, brand goes in affiliated_dso.
     NOTE: this OVERRIDES the audit synthesis's demotion verdict for Dental Roots
     and Oradent — GLDP's own locator lists both addresses (seed provenance
     web_locator:generic in il_dso_locations_merged.json) = hard evidence.
  3. Specialist reclasses (audit-verified): Tamulis-Shea (ADA-verified pediatric),
     Specialty Dental Services / PerioCraft (19-provider perio group).
  4. practice_name fixes where the display name belongs to a DIFFERENT practice
     (Data-Axle address-crosswalk artifacts).
  5. 1st Family Dental normalization: real dentist-founded 10-location Chicago
     group -> keep corporate but dso_national -> dso_regional (not a national
     brand), unified affiliated_dso spelling.
  6. CLOSED/STALE flags appended to classification_reasoning for web-verified
     closed-or-moved rows (kept in DB per never-DELETE rule).
  7. Recompute IL zip_scores from practice_locations (fraction scale).

Idempotent: demotions only touch rows still in dso_*; attribution fixes are
plain value writes; reasoning appends are guarded by a marker substring.

Every UPDATE bumps updated_at (raw sqlite3 bypasses ORM onupdate — a stale
updated_at corrupts the audit trail; root cause of the 2026-06-10 staleness).

Audit output: data/dso_research/il_false_corporate_demotions_round2_20260612.json
reclassify_verified_corporate_il.py unions ALL il_false_corporate_demotions_*.json
files into its never-re-promote exclusion set — 4 of the demoted locations DO
appear in seed files (Comfort Dental name-FP, Choice Dental Group nonexistent
chain) and would re-promote without that exclusion.
"""
import json
import sqlite3
import sys

DB = "data/dental_pe_tracker.db"
AUDIT = "data/dso_research/il_false_corporate_demotions_round2_20260612.json"
MARKER = "[audit 2026-06-12 r2]"

# location_id -> demotion spec. npi_overrides lets one NPI land in a different
# class than the location (Stojanovic's provider-less org NPI -> org_only_npi).
DEMOTIONS = {
    "d44c43930b0f8d3c": dict(
        new_ec="solo_established", npi_overrides={"1881083624": "org_only_npi"},
        name="DR. ZORAN D. STOJANOVIC & ASSOCIATES, LTD", zip="60118",
        reason="40-yr independent solo practice (web-verified); GRYPHON INVESTORS "
               "attribution was Data-Axle EIN/address crosswalk contamination. Org "
               "NPI has 0 providers at address (individual NPI sits on sibling row).",
        evidence="practice website + Healthgrades; no Smile Brands/Gryphon listing"),
    "f5a7ad23598f31ca": dict(
        new_ec="small_group", npi_overrides={},
        name="CORE Dental (Sheehan)", zip="60174",
        reason="Family-owned CORE Dental, 3 providers (Sheehan + associates); "
               "GRYPHON attribution = crosswalk contamination.",
        evidence="coredentalgroup.com own site; no DSO affiliation disclosed"),
    "e6191892a75e8dc5": dict(
        new_ec="specialist", npi_overrides={},
        name="Barrington endodontics office (10 Executive Ct)", zip="60010",
        reason="Occupant is an independent endodontics practice (Scalia); "
               "'Barrington Smiles' name + GRYPHON attribution both wrong.",
        evidence="endodontics practice website at this address; no DSO"),
    "6af9e37687d09b08": dict(
        new_ec="small_group", npi_overrides={},
        name="1ST CHOICE DENTAL", zip=None,
        reason="Seeded as 'Choice Dental Group' — that chain does not exist "
               "(web-verified); 2-provider independent office.",
        evidence="no such DSO findable; practice's own site independent"),
    "96ef01b3b198c50b": dict(
        new_ec="family_practice", npi_overrides={},
        name="COMFORT DENTAL CARE LLC", zip="60193",
        reason="Name-string FP: Comfort Dental franchise has ZERO IL locations; "
               "this is the Patel family's independent practice.",
        evidence="comfortdental.com locator (no IL); practice site Drs. B & A Patel"),
    "6f43af650c0b840d": dict(
        new_ec="small_group", npi_overrides={},
        name="CHARLES LOCKHART DDS / Midwest Dental Sleep Center", zip="60611",
        reason="Independent sleep-dentistry clinic; 'Midwest Dental' NAME-STRING "
               "false-match to the Midwest Dental chain propagated GRYPHON.",
        evidence="midwestdentalsleepcenter.com — independent, no chain affiliation"),
    "b6c85d93ce43a853": dict(
        new_ec="specialist", npi_overrides={},
        name="TOOTH FAIRY WORLD PC", zip="60615",
        reason="Founder-owned pediatric practice (Dr. Vitiello, est. 1989, 2 "
               "offices); no Shore/GLDP evidence anywhere. Org NPI taxonomy "
               "1223P0221X (pediatric) -> specialist.",
        evidence="toothfairyworlddentistry.com + Yelp; GLDP locator does NOT list it"),
}

# Extra NPI-only demotions not covered by a demoted location.
NPI_DEMOTIONS = {
    "1568533867": dict(new_ec="specialist",
        reason="Works at JP Orthodontics (specialist location, 60103); "
               "dso_national + 'EVENLY ORTHODONTICS DUPONT' was placeholder-"
               "linkage junk (parent_iusa='000000000')."),
    "1659468221": dict(new_ec="specialist",
        reason="ADA-verified board-certified pediatric dentist (Tamulis-Shea); "
               "taxonomy 122300000X is mis-entered GP."),
    "1922175223": dict(new_ec="specialist", reason="Tooth Fairy World org NPI, taxonomy 1223P0221X pediatric."),
    "1538558408": dict(new_ec="specialist", reason="Dr. Vitiello, founder of Tooth Fairy World pediatric practice (web-verified pediatric despite GP taxonomy)."),
}

# Locations: keep class (or cosmetic re-split), fix attribution / name / reasoning.
# Fields: dso, sponsor, ec (optional override), name (optional), note (optional append).
KEEPS = {
    # Midwest Dental (Smile Brands / Gryphon Investors) — fund name -> sponsor.
    "1b23d9ac9894df13": dict(dso="Midwest Dental (Smile Brands)", sponsor="Gryphon Investors"),
    "78ed9776d81fc92d": dict(dso="Midwest Dental (Smile Brands)", sponsor="Gryphon Investors"),
    "b6f0158e932b879c": dict(dso="Midwest Dental (Smile Brands)", sponsor="Gryphon Investors"),
    "b9e995cf85a64d91": dict(dso="Midwest Dental (Smile Brands)", sponsor="Gryphon Investors",
                             ec="dso_national", name="Midwest Dental - Elgin",
                             note="Web-verified: 1530 N Randall Rd Ste 100 is Midwest "
                                  "Dental's Elgin office (sharecare/midwest-dental.com); "
                                  "row was named after an employed associate."),
    # Great Lakes Dental Partners (Shore Capital) — GLDP's own locator lists these.
    "c088f2d83fe13d65": dict(dso="Great Lakes Dental Partners", sponsor="Shore Capital Partners",
                             note="Manus Dental acquired by GLDP 2017 (GLDP press release)."),
    "41a086c9bd03fa91": dict(dso="Great Lakes Dental Partners", sponsor="Shore Capital Partners",
                             note="GLDP-acquired Dec 2018 (press release); PERMANENTLY "
                                  "CLOSED April 2023 per sunrisedentalcare.com — kept "
                                  "per never-DELETE rule; NPPES-staleness limitation."),
    "25d611ece46470e6": dict(dso="Great Lakes Dental Partners", sponsor="Shore Capital Partners",
                             note="6258 N Lincoln Ave on GLDP's own locator page (seed "
                                  "web_locator:generic) — audit demotion verdict OVERRIDDEN "
                                  "by documentary provenance."),
    "9550d33a7efdafdd": dict(dso="Great Lakes Dental Partners", sponsor="Shore Capital Partners",
                             note="4015 Plainfield-Naperville Rd Ste 106 on GLDP's own "
                                  "locator page — audit 'no hard evidence' verdict "
                                  "OVERRIDDEN by documentary provenance."),
    # NADG — audit-verified 2021 acquisition; was Gryphon-contaminated.
    "ce91352555d1a5e7": dict(dso="North American Dental Group", sponsor=None,
                             note="NADG acquired Affiliated Dental Specialists 2021 "
                                  "(web-verified); prior NULL/Gryphon attribution wrong."),
    # Aspen Bolingbrook — Evenly placeholder junk in affiliated_dso.
    "45ab58a401772b06": dict(dso="Aspen Dental", sponsor=None),
}

# 1st Family Dental: real dentist-founded ~10-office Chicago group. Corporate
# under the floor's brand-across-3+-ZIPs definition, but NOT a national brand:
# normalize all rows dso_national -> dso_regional + one canonical spelling.
FIRST_FAMILY_DSO = "1st Family Dental"
FIRST_FAMILY_NOTE = ("dentist-founded multi-location Chicago group (10 watched "
                     "offices) — corporate per brand-across-3+-ZIPs floor rule; "
                     "dso_regional not dso_national (not a national brand).")
FIRST_FAMILY_NAME_FIX = {
    # Data-Axle crosswalk wrote a competitor's name on this row: 2511 N Milwaukee
    # is 1st Family Dental of Logan Square; Dentologie is at 1625 N Milwaukee.
    "be2a1cd5ebe9d302": "1st Family Dental of Logan Square",
}

# NPI-level attribution fixes (keep class). npi -> (dso, sponsor)
NPI_ATTRIBUTION = {
    "1861415952": ("Midwest Dental (Smile Brands)", "Gryphon Investors"),
    "1750481115": ("Midwest Dental (Smile Brands)", "Gryphon Investors"),
    "1619133345": ("Midwest Dental (Smile Brands)", "Gryphon Investors"),
    "1417086877": ("Midwest Dental (Smile Brands)", "Gryphon Investors"),
    "1104816958": ("Midwest Dental (Smile Brands)", "Gryphon Investors"),
    "1295801611": ("Great Lakes Dental Partners", "Shore Capital Partners"),
    "1225252687": ("Great Lakes Dental Partners", "Shore Capital Partners"),
    "1619049905": ("Great Lakes Dental Partners", "Shore Capital Partners"),
    "1164836912": ("Great Lakes Dental Partners", "Shore Capital Partners"),
    "1881683076": ("North American Dental Group", None),
    "1639609340": ("Aspen Dental", None),
}

# Zager: independent OMS in a 49-provider Loop building where GLDP also has an
# office — fund-name attribution unsupported at provider level. Class stays
# specialist (not in floor); clear the bogus dso + ownership.
ZAGER_NPI = "1245227867"

# Other practice_name fixes (wrong-practice display names from address crosswalk).
NAME_FIXES = {
    "fcf40ad38b38a300": ("Gallery Park Family & Pediatric Dentistry",
                         "2501 Compass Rd is Dr. Jayna Shah's Gallery Park practice; "
                         "'Mopper Hartlieb & Assoc' is at 2601 (web-verified)."),
}

# CLOSED/STALE flags (no class change; web-verified during audit).
CLOSED_FLAGS = {
    "b77c247e6be90e1e": "CLOSED ~March 2026 (web-verified); real Advanced Family Dental chain location while open.",
    "035326fadc731101": "STALE: NPPES record last meaningful update 2019; address now operates as Dental Shop of Elk Grove.",
    "3753fd053d6eb301": "CLOSED (web-verified): East Side Dental Office & Lab no longer operating.",
    "fca3ad421cdeee00": "MOVED (web-verified): practice relocated to 9235 Skokie Blvd.",
}

REVIEWED_NO_CHANGE = [
    dict(location_id="46736b187ceba600", verdict="keep large_group",
         why="audit's website check shows 2 providers but NPPES registers 6 NPIs "
             "at the address — NPPES evidence supports large_group; both classes "
             "are independent so no KPI impact"),
    dict(location_id="d9e1cbf0d6b6b005", verdict="keep location large_group / NPI org_only_npi",
         why="org NPI with 0 individual NPIs registered at address — org_only_npi "
             "is correct BY DEFINITION; practice is real, dentists register elsewhere"),
    dict(location_id="4f95e6d5f0037303", verdict="keep large_group (NO promotion)",
         why="Smile Partners USA affiliation could NOT be verified (site JS-only; "
             "all directories show Dr. Jeffrey Zeller independent, est. 2014) — "
             "binding rule: no corporate flip without documentary evidence"),
    dict(location_id="18d18c5b67810364", verdict="keep specialist (building-level row)",
         why="25 E Washington houses 49 specialist providers incl. one GLDP office; "
             "suite-level attribution impossible — Zager's fund-name tag cleared"),
]

CORP = ("dso_regional", "dso_national")


def loc_npis(row):
    out = []
    for col in ("primary_npi", "org_npi"):
        if row[col]:
            out.append(row[col])
    if row["provider_npis"]:
        try:
            out += [n for n in json.loads(row["provider_npis"]) if n]
        except Exception:
            pass
    return list(dict.fromkeys(out))


def main(apply=True):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    cur = c.cursor()

    gp0, corp0 = c.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores").fetchone()
    npi0 = c.execute("""SELECT COUNT(*) FROM practices p JOIN watched_zips w
        ON substr(p.zip,1,5)=w.zip_code
        WHERE p.entity_classification IN ('dso_regional','dso_national')""").fetchone()[0]
    print(f"BEFORE  floor={corp0}/{gp0}={100*corp0/gp0:.2f}%  corp NPIs={npi0}")

    audit = {"_generated": "2026-06-12", "_method": "inline web verification (WebSearch/WebFetch), "
             "audit-synthesis triage + seed-provenance cross-check",
             "demotions": [], "npi_demotions": [], "attribution_fixes": [],
             "name_fixes": [], "closed_flags": [], "reviewed_no_change": REVIEWED_NO_CHANGE}

    # ---- 1. location demotions + their NPI flips ----
    for lid, spec in DEMOTIONS.items():
        row = c.execute("SELECT * FROM practice_locations WHERE location_id=?", (lid,)).fetchone()
        if not row:
            print(f"  !! missing location {lid}"); continue
        old = row["entity_classification"]
        flips = []
        if old in CORP:
            reason = f"{MARKER} DEMOTED {old}->{spec['new_ec']}: {spec['reason']} Evidence: {spec['evidence']}"
            if apply:
                cur.execute("""UPDATE practice_locations SET entity_classification=?,
                    ownership_status='independent', affiliated_dso=NULL,
                    affiliated_pe_sponsor=NULL, classification_reasoning=?,
                    classification_confidence=90, updated_at=datetime('now')
                    WHERE location_id=?""", (spec["new_ec"], reason, lid))
            for npi in loc_npis(row):
                target = spec["npi_overrides"].get(npi, spec["new_ec"])
                if apply:
                    r = cur.execute("""UPDATE practices SET entity_classification=?,
                        ownership_status='independent', affiliated_dso=NULL,
                        affiliated_pe_sponsor=NULL, updated_at=datetime('now')
                        WHERE npi=? AND entity_classification IN ('dso_regional','dso_national')""",
                        (target, npi))
                    if r.rowcount:
                        flips.append({"npi": npi, "to": target})
                else:
                    cls = c.execute("SELECT entity_classification FROM practices WHERE npi=?", (npi,)).fetchone()
                    if cls and cls[0] in CORP:
                        flips.append({"npi": npi, "to": target})
        else:
            print(f"  (already demoted: {lid} is {old})")
        audit["demotions"].append({"location_id": lid, "name": spec["name"],
                                   "old": old, "new": spec["new_ec"],
                                   "reason": spec["reason"], "evidence": spec["evidence"],
                                   "npi_flips": flips})
        print(f"  DEMOTE {lid} {old}->{spec['new_ec']}  npis={[f['npi'] for f in flips]}")

    # ---- 2. NPI-only demotions ----
    for npi, spec in NPI_DEMOTIONS.items():
        if apply:
            r = cur.execute("""UPDATE practices SET entity_classification=?,
                ownership_status='independent', affiliated_dso=NULL,
                affiliated_pe_sponsor=NULL, updated_at=datetime('now')
                WHERE npi=? AND entity_classification != ?""",
                (spec["new_ec"], npi, spec["new_ec"]))
            if r.rowcount:
                audit["npi_demotions"].append({"npi": npi, "to": spec["new_ec"], "reason": spec["reason"]})
                print(f"  NPI {npi} -> {spec['new_ec']}")

    # Tamulis-Shea + Specialty Dental Services locations -> specialist
    for lid, why in (("8355b631297f3f01", "ADA-verified board-certified pediatric dentist"),
                     ("ca1805a873d6fd05", "PerioCraft 19-provider periodontics group; NPI row already specialist")):
        if apply:
            cur.execute("""UPDATE practice_locations SET entity_classification='specialist',
                classification_reasoning=? || ' ' || COALESCE(classification_reasoning,''),
                updated_at=datetime('now')
                WHERE location_id=? AND entity_classification != 'specialist'""",
                (f"{MARKER} reclass->specialist: {why}.", lid))
            print(f"  LOC {lid} -> specialist ({cur.rowcount} row)")

    # ---- 3. keep-with-correction attribution fixes ----
    for lid, fix in KEEPS.items():
        row = c.execute("SELECT entity_classification, classification_reasoning, practice_name "
                        "FROM practice_locations WHERE location_id=?", (lid,)).fetchone()
        if not row:
            print(f"  !! missing keep {lid}"); continue
        new_ec = fix.get("ec") or row["entity_classification"]
        note = fix.get("note", "")
        reasoning = row["classification_reasoning"] or ""
        if note and MARKER not in reasoning:
            reasoning = f"{MARKER} {note} | {reasoning}"
        if apply:
            cur.execute("""UPDATE practice_locations SET affiliated_dso=?,
                affiliated_pe_sponsor=?, entity_classification=?,
                practice_name=COALESCE(?, practice_name), classification_reasoning=?,
                updated_at=datetime('now') WHERE location_id=?""",
                (fix["dso"], fix.get("sponsor"), new_ec, fix.get("name"), reasoning, lid))
        audit["attribution_fixes"].append({"location_id": lid, "dso": fix["dso"],
                                           "sponsor": fix.get("sponsor"), "ec": new_ec,
                                           "note": note})
        print(f"  KEEP  {lid} dso='{fix['dso']}' sponsor='{fix.get('sponsor')}'")

    # ---- 4. 1st Family Dental normalization ----
    if apply:
        cur.execute("""UPDATE practice_locations SET entity_classification='dso_regional',
            affiliated_dso=?, classification_reasoning=? || ' ' || COALESCE(classification_reasoning,''),
            updated_at=datetime('now')
            WHERE (affiliated_dso LIKE '%1ST FAMILY%' OR affiliated_dso LIKE '%1st Family%')
              AND entity_classification IN ('dso_regional','dso_national')""",
            (FIRST_FAMILY_DSO, f"{MARKER} {FIRST_FAMILY_NOTE}"))
        print(f"  1stFamily locations normalized: {cur.rowcount}")
        cur.execute("""UPDATE practices SET entity_classification='dso_regional',
            affiliated_dso=?, updated_at=datetime('now')
            WHERE (affiliated_dso LIKE '%1ST FAMILY%' OR affiliated_dso LIKE '%1st Family%')
              AND entity_classification IN ('dso_regional','dso_national')""",
            (FIRST_FAMILY_DSO,))
        print(f"  1stFamily NPIs normalized: {cur.rowcount}")
        for lid, name in FIRST_FAMILY_NAME_FIX.items():
            cur.execute("UPDATE practice_locations SET practice_name=?, updated_at=datetime('now') "
                        "WHERE location_id=?", (name, lid))
            audit["name_fixes"].append({"location_id": lid, "name": name,
                                        "why": "address crosswalk wrote competitor name (Dentologie is at 1625 N Milwaukee)"})

    # ---- 5. NPI attribution fixes + Zager cleanup ----
    for npi, (dso, sponsor) in NPI_ATTRIBUTION.items():
        if apply:
            cur.execute("""UPDATE practices SET affiliated_dso=?, affiliated_pe_sponsor=?,
                updated_at=datetime('now')
                WHERE npi=? AND entity_classification IN ('dso_regional','dso_national')""",
                (dso, sponsor, npi))
    if apply:
        cur.execute("""UPDATE practices SET affiliated_dso=NULL, ownership_status='unknown',
            updated_at=datetime('now') WHERE npi=?""", (ZAGER_NPI,))
        print(f"  NPI attribution fixed: {len(NPI_ATTRIBUTION)} + Zager cleared")

    # ---- 6. other name fixes + CLOSED flags ----
    for lid, (name, why) in NAME_FIXES.items():
        if apply:
            cur.execute("UPDATE practice_locations SET practice_name=?, updated_at=datetime('now') "
                        "WHERE location_id=?", (name, lid))
        audit["name_fixes"].append({"location_id": lid, "name": name, "why": why})
    for lid, flag in CLOSED_FLAGS.items():
        if apply:
            cur.execute("""UPDATE practice_locations SET
                classification_reasoning=? || ' ' || COALESCE(classification_reasoning,''),
                updated_at=datetime('now')
                WHERE location_id=? AND COALESCE(classification_reasoning,'') NOT LIKE ?""",
                (f"{MARKER} {flag} |", lid, f"%{flag[:40]}%"))
        audit["closed_flags"].append({"location_id": lid, "flag": flag})

    if not apply:
        print("(dry-run: no writes)"); c.close(); return

    # ---- 7. recompute IL zip_scores (fraction scale — see reclassify script) ----
    for (z,) in c.execute("SELECT zip_code FROM zip_scores WHERE state='IL'").fetchall():
        n = c.execute("""SELECT COUNT(*) FROM practice_locations
            WHERE substr(zip,1,5)=? AND entity_classification IN ('dso_regional','dso_national')""",
            (z,)).fetchone()[0]
        gp = c.execute("""SELECT COUNT(*) FROM practice_locations
            WHERE substr(zip,1,5)=? AND entity_classification IN
            ('solo_established','solo_new','solo_inactive','solo_high_volume',
             'family_practice','small_group','large_group','dso_regional','dso_national')""",
            (z,)).fetchone()[0]
        cur.execute("""UPDATE zip_scores SET corporate_location_count=?, total_gp_locations=?,
            corporate_share_pct=CASE WHEN ?>0 THEN ROUND(1.0*?/?,4) ELSE 0 END
            WHERE zip_code=?""", (n, gp, gp, n, gp, z))
    c.commit()

    json.dump(audit, open(AUDIT, "w"), indent=1)
    gp1, corp1 = c.execute(
        "SELECT SUM(total_gp_locations), SUM(corporate_location_count) FROM zip_scores").fetchone()
    npi1 = c.execute("""SELECT COUNT(*) FROM practices p JOIN watched_zips w
        ON substr(p.zip,1,5)=w.zip_code
        WHERE p.entity_classification IN ('dso_regional','dso_national')""").fetchone()[0]
    il = c.execute("SELECT SUM(corporate_location_count), SUM(total_gp_locations) "
                   "FROM zip_scores WHERE state='IL'").fetchone()
    print(f"AFTER   floor={corp1}/{gp1}={100*corp1/gp1:.2f}%  (IL {il[0]}/{il[1]})  corp NPIs={npi1}")
    print(f"audit written: {AUDIT}")
    print("NEXT: re-baseline FLOOR guards, sync floor tables + surgical practices heal")
    c.close()


if __name__ == "__main__":
    main(apply="--dry-run" not in sys.argv)
