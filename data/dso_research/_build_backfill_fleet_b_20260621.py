"""
Fleet B — non-AO evidence-gap backfill builder (locator_exact 22 + practice_intel 21 = 43).
READ-ONLY on the DB. Writes ONE validator-native evidence queue + nothing else.
NO DB writes, NO LEDGER/PROGRESS writes, NO consolidation.

Source of truth for the 43 rows: /tmp/backfill_evidence_dump.json (built earlier this
session from consolidation_candidate_manifest_20260621.json evidence_gap_backfill_queue,
lanes locator_exact + practice_intel; the AO_network lane is Main's, untouched).

Every evidence_url / evidence_artifact below is transcribed from on-disk data
(practice_intel.verification_urls, practice_locations fields, il_cluster_ownership_verified_20260530.json,
dso_locations). NO invented URLs. Uncertain rows stay needs_verification (assigned_tier=undetermined).
No inferred name_chain / AO rescue.
"""
import json, os

DR = "/Users/suleman/dental-pe-tracker/data/dso_research"
DUMP = "/tmp/backfill_evidence_dump.json"
OUT = os.path.join(DR, "ownership_evidence_queue_fleet_b_backfill_20260621.json")

dump = {r["lid"]: r for r in json.load(open(DUMP))}

# durable artifact shared by the 19 Heartland friendly-PC locator rows
HEARTLAND_ART = ("NPPES org legal name 'DENTAL PROFESSIONALS OF ILLINOIS PC' web-verified as "
                 "Heartland Dental friendly-PC (sponsor KKR) in "
                 "il_cluster_ownership_verified_20260530.json; practice_locations.affiliated_dso="
                 "'Heartland Dental'; dso_locations has exact street+ZIP match to Heartland Dental "
                 "(source_url il_seed:nppes_cluster)")

# ---- per-location adjudication ---------------------------------------------
# tuple: (assigned_tier, status, basis, urls, artifacts, conf, pe, proposed,
#         owner, net, reasoning, qa)
NV = "needs_verification"; CL = "classified"; UND = "undetermined"

ADJ = {
  # ===================== practice_intel lane — CLASSIFIED (9) ==================
  "a31ca3008c75ab1f": ("institutional", CL, "web_verified",
    ["https://tap360health.org/", "https://www.charitynavigator.org/ein/363843377"], [],
    "high", False, "institutional", "Tapestry 360 Health (FQHC)", None,
    "Federally-funded community health center: tap360health.org + Charity Navigator EIN 36-3843377 "
    "confirm a nonprofit safety-net org, not a DSO.", None),
  "047ce502ad2a0371": ("institutional", CL, "web_verified",
    ["https://www.guidestar.org/profile/36-3843377",
     "https://npino.com/dental-clinic/1215258116-heartland-health-center---clark/"], [],
    "medium", False, "institutional", "Heartland International Health Center (FQHC)", None,
    "Heartland International Health Center FQHC dental site at 4740 N Clark: GuideStar EIN 36-3843377 "
    "+ npino dental-clinic listing — a community health center, not Heartland Dental.",
    "Same EIN as Tapestry 360 (merged FQHCs); 'Heartland' here = Heartland International Health "
    "Center nonprofit, NOT Heartland Dental DSO."),
  "dd7e21c547e01ae8": ("institutional", CL, "web_verified",
    ["https://www.northshore.org/dentistry",
     "https://programs.adea.org/PASS/programs/evanston-hospital-general-practice-residency"], [],
    "medium", False, "institutional", "NorthShore/Endeavor Health (Evanston Hospital)", None,
    "Hospital-based dental center: northshore.org/dentistry + ADEA Evanston Hospital general-practice "
    "residency; parent_org_lbn=ENDEAVOR HEALTH — academic hospital, not a DSO.", None),
  "2ec73146fbeb2f8c": ("institutional", CL, "web_verified",
    ["https://powersandsons.com/2025/01/21/advocate-illinois-masonic-medical-center-dental-clinic-now-open/",
     "https://doctors.advocatehealth.com/i-james-d-benz-chicago-dentistry-general"], [],
    "medium", False, "institutional", "Advocate Health (Illinois Masonic dental clinic)", None,
    "Advocate Illinois Masonic Medical Center dental clinic at 913 W Wellington "
    "(powersandsons.com opening announcement + doctors.advocatehealth.com provider page) — hospital "
    "system clinic.", None),
  "bdc26d3a17c9da40": ("true_independent", CL, "web_verified",
    ["https://www.chicagodentaltouch.com/", "https://www.healthgrades.com/dentist/dr-sylvia-guerrero-x5ltk"], [],
    "high", False, "true_independent", "Dr. Sylvia Guerrero", None,
    "Single owner-dentist Dr. Sylvia Guerrero at one location (Dental Touch, chicagodentaltouch.com); "
    "verified dossier found no DSO/MSO/parent — positively earned independent.", None),
  "899d05f409fe0dd6": ("true_independent", CL, "web_verified",
    ["https://smileleaguedental.com",
     "https://www.bbb.org/us/il/joliet/profile/dentist/smile-league-dental-0654-90025826"], [],
    "medium", False, "true_independent", "Dr. Morolayo Oluyemi", None,
    "Owner-operated single-location practice (smileleaguedental.com, Dr. Oluyemi) with its own BBB "
    "profile and no DSO/MSO signal.",
    "Verified dossier noted a recent owner-to-owner transition (no DSO involvement found) — verify no MSO."),
  "2eccce6b14d310cd": ("dentist_multi", CL, "intel_dossier",
    ["https://www.nsdentist.com", "https://www.yelp.com/biz/north-suburban-dental-of-highland-park-highland-park"], [],
    "medium", False, "dentist_multi", "Dr. Zieba (North Suburban Dental)", "brand:north_suburban_dental",
    "Dentist-owned North Suburban Dental operating 3 IL locations (nsdentist.com); verified dossier "
    "shows owner-operated with NO MSO/management company — dentist_multi, not DSO.",
    "Former DBA 'Webster Dental Care' per dossier — verify no residual Webster MSO structure."),
  "0476ac933c798a82": ("dentist_multi", CL, "intel_dossier",
    ["https://forever-dental.com/sell-your-chicago-area-dental-practice/", "https://dentistschicago.com/"], [],
    "medium", False, "dentist_multi", "Dr. Reshma Dhake (Forever Dental)", "brand:forever_dental",
    "Dentist-owned Forever Dental multi-location group (forever-dental.com); Dr. Dhake's own "
    "'sell your Chicago-area practice' page documents owner-driven acquisition, no MSO/PE platform.", None),
  "ba379b6aa4cf3678": ("dentist_multi", CL, "intel_dossier",
    ["https://www.forever-dental.com", "https://forever-dental.com/sell-your-chicago-area-dental-practice/"], [],
    "medium", False, "dentist_multi", "Dr. Reshma Dhake (Forever Dental)", "brand:forever_dental",
    "Second Forever Dental location (5738 W Belmont) under the same dentist-owner Dr. Dhake "
    "(forever-dental.com) — dentist-owned multi-location, no MSO.", None),

  # ===================== practice_intel lane — NEEDS_VERIFICATION (12) =========
  "144d631a4c4dce2b": (UND, NV, "none", [], [], "low", False, "institutional",
    "Infant Welfare Society of Chicago", None,
    "Name 'Infant Welfare Society of Chicago' strongly implies a nonprofit safety-net clinic, but no "
    "on-disk dossier/URL confirms institutional status — needs web verification.", None),
  "d803fcfe4618e8a3": (UND, NV, "none", [], [], "low", False, "institutional",
    "Heartland International Health Center (FQHC)", None,
    "Heartland International Health Center at 845 W Wilson — same FQHC org as the verified 4740 N Clark "
    "site (EIN 36-3843377), but this address has no on-disk dossier URL; needs its own institutional source.",
    "'Heartland' = Heartland International Health Center FQHC, NOT Heartland Dental."),
  "e957561c107de91a": (UND, NV, "none", [], [], "low", False, "institutional",
    "Heartland Health Outreach (Heartland Alliance)", None,
    "'Heartland Health Outreach' is the health arm of Heartland Alliance (nonprofit safety-net), not "
    "Heartland Dental; no on-disk URL — needs an institutional source.",
    "BRAND-SUBSTRING TRAP — Heartland Alliance nonprofit, NOT Heartland Dental DSO."),
  "b7499322a2416c5d": (UND, NV, "intel_dossier",
    ["https://www.healthgrades.com/dentist/dr-paulina-jova-3ggg7"], [], "medium", False, "true_independent",
    "Dr. Paulina Jova", None,
    "Named solo owner Dr. Paulina Jova (Crown Dental Center) with no DSO signal, but dossier is partial "
    "— true_independent lead pending a positive owner-confirmation source.", None),
  "499c18e0f7c7ad12": (UND, NV, "intel_dossier",
    ["https://www.bbb.org/us/il/chicago/profile/dentist/lillian-obucina-dds-pc-0654-88501480"], [],
    "low", False, "true_independent", "Dr. Lillian Obucina", None,
    "Solo Dr. Lillian Obucina DDS PC, no DSO signal, but an address/ZIP anomaly blocks classification.",
    "DB address '111 N Wabash' (Chicago Loop) vs ZIP 60202 (Evanston) mismatch — resolve before tiering."),
  "0a318ab399f418de": (UND, NV, "intel_dossier",
    ["https://findadentist.ada.org/il/cook/chicago/general-practice/dr-rosa-d-bellido-griffin-4103834",
     "https://drrosabgdental.weebly.com/"], [], "medium", False, "true_independent",
    "Dr. Rosa Bellido-Griffin", None,
    "Named solo owner Dr. Rosa Bellido-Griffin with her own site (weebly) and ADA listing, no DSO — "
    "strong true_independent lead but dossier is partial; verify owner-occupancy.", None),
  "d2e5c43e4975ddb4": (UND, NV, "structural", [],
    ["practice_locations.affiliated_dso='Midwest Dental'; entity_classification=dso_national "
     "(2720 W 15th St, 60608)"], "medium", False, "branded_dso", None, "brand:midwest_dental",
    "affiliated_dso='Midwest Dental' + ec=dso_national point to the Midwest Dental DSO brand, but "
    "affiliated_dso alone isn't final — needs a Midwest Dental locator URL at this exact address.",
    "MANIFEST MIS-BUCKET — manifest proposed_tier=institutional; this is a DSO brand, re-propose branded_dso."),
  "2bf590b5092f1e8e": (UND, NV, "structural", [],
    ["practice_locations.affiliated_dso='Aspen Dental'; entity_classification=dso_national "
     "(1040 W Randolph, 60607); prior audit: parent ADMI Corp / Aspen Dental Mgmt, PE Leonard Green"],
    "medium", True, "branded_dso", None, "brand:aspen_dental",
    "affiliated_dso='Aspen Dental' + ec=dso_national indicate an Aspen-managed friendly-PC (ADMI Corp, "
    "Leonard Green), but needs an Aspen locator URL at exact address to classify.",
    "MANIFEST MIS-BUCKET — manifest proposed_tier=institutional; this is Aspen DSO, re-propose "
    "branded_dso, pe_backed=true."),
  "598cc9dae498795b": (UND, NV, "structural", [],
    ["practice_locations.affiliated_dso='Western Dental' (POSSIBLE 'Northwestern'-contains-'western' "
     "substring false-match); website northwesterndental.com; 201 E Huron, Streeterville 60611"],
    "low", False, "branded_dso", None, None,
    "affiliated_dso='Western Dental' may be a substring false-positive on 'Northwestern Dental Center' "
    "(own site northwesterndental.com, beside Northwestern Memorial) — cannot tier until the Western "
    "Dental tie is confirmed or rejected.",
    "MANIFEST MIS-BUCKET + SUBSTRING RISK — verify whether truly Western Dental/Sonrava or an "
    "independent/NU-affiliated practice mislabeled."),
  "9068c4de3bbdb4b4": (UND, NV, "intel_dossier",
    ["https://www.greatlakesdentalpartners.com/news/2019/10/30/chicagoland-smile-group-continues-growth-with-winnetka-dental-arts-partnership/",
     "https://www.winnetkadentalarts.com/"], [], "medium", True, "stealth_dso",
    "Dr. George Warga (Winnetka Dental Arts)", "brand:great_lakes_dental_partners",
    "Verified dossier ties Dr. Warga / Winnetka Dental Arts to Great Lakes Dental Partners (Chicagoland "
    "Smile Group, Shore Capital) via GLDP's own partnership press release — strong stealth_dso lead, but "
    "a DB address discrepancy (465 Chestnut St) needs reconciliation before classifying.",
    "Address discrepancy (DB 465 Chestnut St vs Winnetka Dental Arts) — verify exact location; PE "
    "sponsor Shore Capital is platform-level."),
  "7b61d1c9b5e65057": (UND, NV, "structural", [],
    ["practice_locations.website=batchelordental.com; greenwoodfamilydental.com is Indiana-focused "
     "(cross-state contamination risk); Heartland/Orahh Care lead in prose unconfirmed"],
    "low", False, "stealth_dso", "Dr. Garfield Batchelor", None,
    "Greenwood Family Dentistry (Dr. Batchelor, 3500 W 111th) shows a possible Heartland/Orahh Care lead "
    "in prose, but greenwoodfamilydental.com is Indiana-focused — IN/Chicago practice confusion blocks "
    "any tier.",
    "CROSS-STATE CONTAMINATION — batchelordental.com (Chicago) vs greenwoodfamilydental.com (Indiana); "
    "verify which entity owns the 60655 site."),
  "5404b210ff43f176": (UND, NV, "structural", [],
    ["practice_intel: 350 N Clark St Ste 600 = Dental Dreams LLC corporate HQ "
     "(zoominfo.com/c/dental-dreams-llc + dentaldreams.com)"], "low", False, "branded_dso",
    "Kang Dental", "brand:dental_dreams",
    "Kang Dental shares 350 N Clark Ste 600 with Dental Dreams LLC corporate HQ, but HQ co-location is "
    "not proof this NPI is a Dental Dreams clinic — needs confirmation the practice operates under "
    "Dental Dreams.",
    "HQ CO-LOCATION AMBIGUITY — verify Kang Dental is a Dental Dreams office vs an unrelated tenant at "
    "the HQ building."),

  # ===================== locator_exact lane — CLASSIFIED (2) ==================
  "34235da38acd2bfd": ("branded_dso", CL, "locator",
    ["https://orlandsquare.dentalworks.com"], [], "medium", True, "branded_dso",
    "DentalWorks (Sonrava Health / Western Dental)", "brand:dentalworks_sonrava",
    "DentalWorks Orland Square brand location (orlandsquare.dentalworks.com) with "
    "practice_locations.parent_company=SONRAVA HEALTH + affiliated_dso=Western Dental — established "
    "DSO/platform brand.",
    "pe_backed via Sonrava Health (New Mountain Capital platform) — sponsor is platform-level."),
  "5cd692a50e5c32b7": ("branded_dso", CL, "locator",
    ["https://dentologie.com/our-locations/chicago/river-north",
     "https://www.chicagobusiness.com/health-care/dentologie-dentist-office-expands-chicago-seattle"], [],
    "medium", True, "branded_dso", "Dentologie (River North)", "brand:dentologie",
    "NPI resolves to Dentologie River North per official locator dentologie.com/our-locations/chicago/"
    "river-north; Crain's documents the DSO/multi-location model and CB Insights/PitchBook show "
    "institutional funding — branded_dso platform.",
    "DB practice_name 'Schock Dental' vs resolved 'Dentologie River North' — name discrepancy, verify "
    "Schock→Dentologie acquisition/rebrand."),

  # ===================== locator_exact lane — Forever Family (1 NV) ============
  "e669559ebe8a9d4a": (UND, NV, "structural", [],
    ["practice_locations.affiliated_dso='Dental Care Alliance (DCA)'; entity_classification=dso_regional; "
     "local brand 'Forever Family Dental of New Lenox'/familydentistnewlenox.com (202 Vancina Ln, 60451)"],
    "medium", True, "stealth_dso", None, "brand:dental_care_alliance",
    "'Forever Family Dental of New Lenox' (familydentistnewlenox.com) carries affiliated_dso='Dental "
    "Care Alliance (DCA)' + ec=dso_regional — a DCA-managed friendly-practice lead, but affiliated_dso "
    "alone isn't final; needs a DCA source URL.",
    "DCA is a DSO/management company; pe sponsor platform-level."),
}

# ---- the 19 Heartland friendly-PC locator rows (all NV, proposed branded_dso) ----
HEARTLAND_LIDS = ["d4d827860b4132cb", "4afceaeeaa164e94", "bdc1c2d27954f752", "bf7a26c4684ee32a",
                  "46c4e7116d0046a8", "a0b36b77759aefe3", "f2bf548446e774e6", "629e6c24236f7dc1",
                  "cbde3ee6f46acad7", "093fbea9e8c840df", "6dba925c21c398ce", "fff9fbbb819f006a",
                  "90aa8ae6b599ba7d", "1237e7c94d53bab9", "589308e9a6bcacf7", "be7ff941b871d3db",
                  "b5941b7e437e95f1", "1b931a8e9c2675a9", "8a3addfc27e73bbf"]
for lid in HEARTLAND_LIDS:
    d = dump[lid]
    addr = d.get("addr"); zp = d.get("zip"); site = d.get("loc_website")
    art = HEARTLAND_ART + (f"; practice website {site}" if site else "")
    urls, qa = [], None
    if lid == "cbde3ee6f46acad7":
        qa = ("Already audited-promoted to dso_national=Heartland on 2026-06-19 "
              "(il_verified_locator_promotions_20260619.json); ownership_tier was reset to NULL so it "
              "re-appears in backfill. NB the '450 N Weber' Great Lakes Dental Partners hit is a "
              "direction false-match (this is 450 S Weber) — exclude.")
    if lid == "8a3addfc27e73bbf":
        urls = ["https://www.dnb.com/business-directory/company-profiles.dental_professionals_of_illinois_pc.3af220e3b67d0419180bf6b2aa2c6449.html"]
        art += ("; D&B lists 'Dental Professionals of Illinois PC' (Effingham HQ, 331 employees, "
                "$17.51M revenue) — corporate-structure artifact; actual tenant Boulevard Place Dental Care")
    ADJ[lid] = (UND, NV, "structural", urls, [art], "medium", True, "branded_dso", None,
                "brand:heartland_dental",
                f"Heartland Dental friendly-PC ('Dental Professionals of Illinois PC') at {addr}, {zp}; "
                "legal-name->Heartland mapping is web-verified and dso_locations matches this street+ZIP, "
                "but no per-location Heartland official locator URL is on disk — strengthened branded_dso "
                "lead held as needs_verification per the no-name-chain-rescue rule.", qa)

# ---- assemble validator-native rows ----------------------------------------
rows, qa_flags = [], []
for lid, a in ADJ.items():
    (tier, status, basis, urls, arts, conf, pe, proposed, owner, net, reasoning, qa) = a
    d = dump[lid]
    disp = "ready" if status == CL else "needs_verification"
    row = {
        "location_id": lid,
        "assigned_tier": tier,
        "status": status,
        "evidence_basis": basis,
        "evidence_urls": urls,
        "evidence_artifacts": arts,
        "confidence": conf,
        "reasoning": reasoning,
        "proposed_tier": proposed,
        "disposition": disp,
        "pe_backed": pe,
        "owner_identity": owner,
        "network_id": net,
        "signal": {"type": ("locator" if basis == "locator" else
                            "practice_intel" if basis == "intel_dossier" else
                            "affiliated_dso" if basis == "structural" else "other"),
                   "details": d.get("hint")},
        "exact_address_match": basis == "locator",
        "practice_name": d.get("name"), "address": d.get("addr"),
        "city": None, "zip": d.get("zip"),
        "lane": d.get("lane"),
        "agent": "fleet_b", "reviewed_at": "2026-06-21",
    }
    rows.append(row)
    if qa:
        qa_flags.append({"location_id": lid, "practice_name": d.get("name"), "flag": qa})

by_status = {}
by_tier = {}
for r in rows:
    by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    key = r["assigned_tier"] if r["status"] == CL else f"proposed:{r['proposed_tier']}"
    by_tier[key] = by_tier.get(key, 0) + 1

out = {
    "_meta": {
        "session": "fleet-b-backfill-2026-06-21",
        "source_manifest": "consolidation_candidate_manifest_20260621.json",
        "lanes": "locator_exact (22) + practice_intel (21) = 43; AO_network lane untouched (Main's)",
        "rule": ("transcribe/verify missing documentary URL or durable artifact per location; "
                 "no inferred name_chain/AO rescue; uncertain -> needs_verification; "
                 "candidate evidence only, NOT final truth; ZERO DB writes"),
        "counts": {"total": len(rows), "by_status": by_status, "by_tier": by_tier},
        "_qa_flags": qa_flags,
    },
    "classifications": rows,
}
json.dump(out, open(OUT, "w"), indent=1)
print(f"wrote {OUT}")
print(f"total rows: {len(rows)}")
print(f"by_status: {by_status}")
print(f"by_tier:   {by_tier}")
print(f"qa_flags:  {len(qa_flags)}")
