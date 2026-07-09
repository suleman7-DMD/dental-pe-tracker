#!/usr/bin/env python3
"""Apply the R4 PM network rulings (DECISIONS_PM_20260709.md) to merged_1259_rows.json.

Idempotent: rows already carrying the PM marker in reasoning are skipped.
Respects consolidate_census.py validator constraints:
  - classified rows cannot keep confidence=low (ruled rows bump to medium)
  - classified + URL basis requires >=1 URL; artifact basis requires artifacts
  - DA_-synthetic rows are never in the ruling table (they stay undetermined)
"""
import json, sys

MERGED = "/private/tmp/claude-501/-Users-suleman/04294c63-97de-4d3e-b0fe-0aa37fbabc3f/scratchpad/census_results/merged_1259_rows.json"
MARKER = "[R4 PM ruling 2026-07-09 (Fable)"
URL_BASES = {"locator", "web_verified", "intel_dossier"}
ART_BASES = {"ein_cluster", "ao_cluster", "name_chain", "structural"}

def N(tier, net, pe, owner, note, conf=None):
    return {"tier": tier, "net": net, "pe": pe, "owner": owner, "note": note, "conf": conf}

FD1 = N("branded_dso", "brand:1st_family_dental", False,
        "Dr. Ghassan Abboud (founder; 1st Family Dental / Dental Corporate USA)",
        "1st Family Dental => T5 branded_dso; founder self-describes DSO, 15-16 locations, Dental Corporate USA entity, COO Belkic; no PE")
UDP = N("stealth_dso", "brand:united_dental_partners", False,
        "United Dental Partners (dentist-founded DSO)",
        "United Dental Partners => T4 stealth_dso; self-described DSO, ~22-25 offices under local member brands; no PE confirmed")
GLDP = N("stealth_dso", "brand:great_lakes_dental_partners", True,
         "Great Lakes Dental Partners (Shore Capital Partners)",
         "GLDP => T4 stealth_dso pe_backed=true (Shore Capital); AFD&O merged into GLDP 2018")
NADG = N("stealth_dso", "brand:nadg", True,
         "North American Dental Group (Grove Dental Associates)",
         "Grove Dental => NADG (acquired 2019, PE-backed) => T4 stealth_dso pe_backed=true")
GPS = N("stealth_dso", "brand:gps_dental", True,
        "GPS Dental (Main Post Partners)",
        "GPS Dental => T4 stealth_dso pe_backed=true (Main Post Partners; Becker's Q2 2024 addition)")
SPU = N("stealth_dso", "brand:smile_partners_usa", False,
        "Smile Partners USA",
        "Smile Partners USA => T4 stealth_dso; self-described MSO behind 124-130 practices; no PE sponsor documented")
FAM = N("branded_dso", "brand:familia_dental", True,
        "Familia Dental (The Halifax Group)",
        "Familia Dental => T5 branded_dso pe_backed=true (Halifax Group, ~31 clinics)")
DTL = N("branded_dso", "brand:dentologie", True,
        "Dentologie (Beringea-backed)",
        "Dentologie => T5 branded_dso pe_backed=true (Beringea $25M Series B; 13+ Chicago offices)")
AQEL = N("dentist_multi", "brand:dental360", False,
         "Dr. Fadi Aqel (Brite Dental / Dental 360 / Absolute Dentistry Ltd)",
         "Brite Dental/Dental 360 (Aqel) => T3 dentist_multi; dentist President/owner, no MSO/PE control found; resolves AQEL hold")
SON = N("dentist_multi", "brand:sonrisa_family_dental", False,
        "Dr. Jason Korkus (Sonrisa Family Dental)",
        "Sonrisa (Korkus) => T3 dentist_multi; founder-led 11-12 IL locations, CDCoA is Korkus-led; confidence capped medium", conf="medium")
SWEIS = N("dentist_multi", "ao:SWEIS_JUBRAIL", False,
          "Dr. Jubrail Sweis",
          "Sweis network => T3 dentist_multi; 10-location IL reach, no PE/MSO signal; resolves SWEIS hold")
EFD = N("dentist_multi", "brand:everyones_family_dental", False,
        "Dr. Funmi Adeleke-Babatunde (Everyone's Family Dental)",
        "Everyone's Family Dental => T3 dentist_multi; dentist-owned 12+ IL locations; Sweis/Babatunde attribution overlap noted")
GRAND = N("dentist_multi", "brand:grand_dental_group", False,
          "Dr. Steve Napier + partner dentists (Grand Dental Group)",
          "Grand Dental Group => T3 dentist_multi; 12 offices, self-described 100% dentist-owned")
WEB = N("dentist_multi", "brand:webster_dental_care", False,
        "Dr. Steven Rempas (Webster Dental Care)",
        "Webster Dental Care => T3 dentist_multi; founder-led 9-12 offices")
SHAFI = N("dentist_multi", "ao:SHAFI_REEM", False,
          "Dr. Reem Shafi (Two Rivers / Ashton / Troy / Simply Dental)",
          "Reem Shafi network => T3 dentist_multi per ratified SHAFI ruling extension")
TDG = N("branded_dso", "brand:smile_obsession", False,
        "Transparent Dental Group / Smile Obsession (Dr. Viren Patel)",
        "Smile Obsession/Transparent Dental Group => T5 branded_dso; self-described dentist-owned DSO platform, 17-18 branded locations; pe=false")
IDC = N("dentist_multi", "brand:illinois_dental_centers", False,
        "Dr. Jacob Lake (Illinois Dental Centers)",
        "Illinois Dental Centers => T3 dentist_multi; dentist-founded 10-location network")
P1 = N("stealth_dso", "brand:p1_dental_partners", True,
       "P1 Dental Partners (ex-Cornerstone Dental Partners)",
       "Cornerstone->P1 Dental Partners => T4 stealth_dso pe_backed=true (Prairie Capital/Centerfield/Huntington; acquired Dec 2021)")
IMG = N("stealth_dso", "brand:imagen_dental_partners", False,
        "Imagen Dental Partners",
        "Imagen Dental Partners => T4 stealth_dso; own About page 'An Imagen Partner Practice', ~100 practices; no PE sponsor documented")
ARIA = N("stealth_dso", "brand:aria_care_partners", True,
         "Aria Care Partners / SeniorWell (Serent Capital)",
         "SeniorWell/Aria => T4 stealth_dso pe_backed=true (Serent Capital)")
SAP = N("stealth_dso", "brand:smile_america_partners", True,
        "Smile America Partners (Morgan Stanley Capital Partners)",
        "Smile America Partners => T4 stealth_dso pe_backed=true (Morgan Stanley Capital Partners; mobile dentistry)")
ELITE = N("stealth_dso", "brand:elite_dental_partners", True,
          "Elite Dental Partners (Cressey & Company)",
          "Elite Dental Partners => T4 stealth_dso pe_backed=true (Cressey & Co, 75+ practices)")
RTD = N("stealth_dso", "brand:rising_tide_dental_partners", False,
        "Rising Tide Dental Partners",
        "Rising Tide => T4 stealth_dso; 27-practice MSO, no PE sponsor documented")
SEC = N("dentist_multi", "brand:secure_dental", False,
        "Drs. Jafri & Liu (Secure Dental)",
        "Secure Dental => T3 dentist_multi; own site names dentist CEO/owner, ~11 offices, no MSO evidence")
GOLD = N("dentist_multi", "ao:GOLDMAN_SCOTT", False,
         "Dr. Scott D. Goldman",
         "Goldman network => T3 dentist_multi; single dentist owner, 10+ IL locations")
BID = N("dentist_multi", "brand:best_image_dental", False,
        "Dr. Mary Cavitt (Best Image Dental, Inc.)",
        "Best Image Dental => T3 dentist_multi; BBB names Cavitt president, 20 IL locations")
MAT = N("dentist_multi", "ao:MATARIA_AHMED", False,
        "Dr. Ahmed Mataria (New Millennium Smiles / Optimal Dental Care)",
        "Mataria network => T3 dentist_multi; AO owns/operates multi-brand 10+ IL cities")

RULES = {}
for lid in ["26d1830e863c29a0","b69f42937eb58e41","00283d0319728697","35d7239a6e507cba",
            "d46481314c1f830f","76b01c890765d33f","0b9debb68c723377","0de79b98f75b7128",
            "6f685dcd203ff3d2","e286a73df0d2541b","dddb5ba57c531064","f4d9376d568f7c43",
            "57f43b2b4923beb3","e0ee6d4ff57ad085","6a7337dc1388e15d"]:
    RULES[lid] = FD1
for lid in ["58af66ee2bf4b9c6","c6078e6641ef7f48","16564b68153a5c2c","6e2b945110c94d8b"]:
    RULES[lid] = UDP
for lid in ["544fce1bec289d3d","b77c247e6be90e1e","8f706d83e1aa4a82"]:
    RULES[lid] = GLDP
for lid in ["10dccf210be5a4af","979a18327d3c4595","1f6f116f4cfa533c","a56a841f0923d8aa","424e826f072b9279"]:
    RULES[lid] = NADG
for lid in ["846f31472fc7c11b","9874849021fddd6e"]:
    RULES[lid] = GPS
for lid in ["ed76f164091c7729","89f740688dc5eaf6","2a8e213de1788f9e"]:
    RULES[lid] = SPU
RULES["5f0c2cdb83dd003b"] = FAM
for lid in ["2870e1613ba5f0c2","30ffe0bf981ce460","dd51cb95b974f2ad","776c5f72a94f91a8",
            "e91aa173076b6cad","ef66b532aff030ca","887ec97162de3481"]:
    RULES[lid] = DTL
for lid in ["120e9b88cb476518","fdadc941d3a84cc1","a34490266101cbd2","64e57c66fd098eed",
            "401b88a09170a38e","0d76d8f9105e394d","8256bfff559b0760","a2fc3deda0b02a10",
            "88ef34deb23c8a00","e24bd9e2dcfa6932","3e7a3d11d88cb223","8c6cbd8b8b3e4877"]:
    RULES[lid] = AQEL
for lid in ["6179a9d5365bda56","a9dd854c0381b93f","a8464775598ce6d5","81f0d806c51a0633",
            "51e7cceaef85634f","4c77253121d38b15","5287843d3b6853ff","3d7c80e61cc1b18d",
            "1354bc2b8dff1d69"]:
    RULES[lid] = SON
RULES["e16ff3a9b55a8492"] = SWEIS
RULES["2f2c3b89c49c6169"] = EFD
for lid in ["03bb2bf2ff66a46b","72b44a0858116792"]:
    RULES[lid] = GRAND
for lid in ["3c41e9f7f44640fa","f94fb29cc7d444cd"]:
    RULES[lid] = WEB
for lid in ["895ecae72eb372df","1df260dc64a9a060","f3ebd80e2f52cab2"]:
    RULES[lid] = SHAFI
for lid in ["14a15d38fb5c7e3c","4002b8b6e7fbf4ba","17f32d3b4a0767ce"]:
    RULES[lid] = TDG
RULES["70527352573c9f62"] = IDC
for lid in ["2eccce6b14d310cd","93aac5767437ad29"]:
    RULES[lid] = P1
for lid in ["b6a94ee5a4fbd9fc","05b991e55884d858"]:
    RULES[lid] = IMG
RULES["4ec51b1b725a84ed"] = ARIA
RULES["5a195c1eb06b40b4"] = SAP
RULES["79699d37d4b4c43b"] = ELITE
RULES["333d2094fc1d15e0"] = RTD
RULES["49d9c36c9fe9abb8"] = SEC
RULES["8bb56d655fd949a6"] = GOLD
RULES["996738adba46646b"] = BID
RULES["1ce540833d8db997"] = MAT

# rows agents classified with high conf where the ruling keeps high
KEEP_HIGH = {"c6078e6641ef7f48", "544fce1bec289d3d", "14a15d38fb5c7e3c"}

# slug normalizations on already-classified sibling rows (network_id only)
NORMALIZE = {
    "c42bbfd07106f9f2": "brand:1st_family_dental",
    "be2a1cd5ebe9d302": "brand:1st_family_dental",
    "9d4cd058e4525078": "brand:universal_dental_clinics",
    "c08edf0c9ab2cced": "brand:aspen_dental",
}

# ruled-undetermined: append audit note only, no field changes
UNDET_NOTES = {
    "b6add6f8267c27d4": "residential address, not an operating 1FD office",
    "1235b8bbd036a88e": "residential condo; dentist works at 1FD elsewhere",
    "68c9e0fd8b50aa12": "location turned over to Perla Dental",
    "13b38618b4b921be": "First Dental Image is a separate practice from 1FD",
    "c1526a81500dbd53": "1FD membership not corroborated for this address",
    "86f0b24aac6e0fff": "evidence refuted on verify pass",
    "35b6fa4bbd145b65": "UDP member in fact, but DA_ synthetic NPI bars classified status",
    "9ca6b48c01456b3a": "UDP member in fact, but DA_ synthetic NPI bars classified status",
    "080318c2c0d71ff9": "residential address, sole proprietor; not UDP",
    "42d1dfe2d92fb435": "no UDP link found; ownership unresolved",
    "9550d33a7efdafdd": "GLDP locator negative for this address; row-level evidence refuted",
    "4f102207d0880e37": "address not on GLDP locator; membership unconfirmed",
    "eb68bac52463172c": "GLDP/CSG membership not documented at row level",
    "fec14748d3270a63": "location closed (First American Dental)",
    "173ffa7cc8c3e198": "Al Mufti / britedental.org attribution ambiguous, low confidence",
    "57d1141d853072c0": "address not on Sonrisa locator",
    "5e92660ad5b32980": "EFD/Sweis attribution conflict, low confidence",
    "e86d6e38d85a9aef": "Adeleke/Babatunde surname-variant reach unresolved",
    "93287e7e58ead8af": "address now CLEAR Immediate Care (non-dental)",
    "a331657307319086": "ProCare member but DA_ synthetic NPI bars classified status",
    "8e6296c2589af5ef": "ProCare member but DA_ synthetic NPI bars classified status",
    "719b01502f151a50": "Cicero address not on ProCare locator",
    "072dc7c20b5c2575": "operating status contested",
    "d99bc2c4d6d3f44a": "SAP role via LinkedIn only; entity tie not documentary",
    "e8cb889012ab1fc9": "DentalWorks office relocated; census location no longer operates",
    "7edec4151f858c23": "StomatCare claim low confidence",
    "a09e9abb956dba36": "smilesandco.com was a Data-Axle mismatch; low confidence",
    "81bef17f185df275": "Lyric National is a benefits company, not a clinic",
    "8d81d4516f493d1e": "R6 fail-closed stands (IL SOS interactive-only)",
    "647bd437d43d0cb4": "joined United Dental Centers of Whiting IN; Chicago status unknown",
    "d4d827860b4132cb": "Partners in Care ownership unresolved; DPI PC claim refuted",
    "0f917daa7d21b189": "legal-entity question open, low confidence",
    "501c41b213c7102f": "everisdental.com evidence refuted (parked domain)",
    "c761b821046ed157": "everisdental.com evidence refuted (parked domain)",
    "6a762fd2de039d6e": "Aspen affiliation unconfirmed",
    "35cbbce74d2ff7c5": "3-location brand, DSO claim refuted, no owner identified",
    "b389a8c579980410": "ClearChoice per ratified R2: implant-only specialist brand",
    "5259c8f5d8576019": "association management entity (DA_ synthetic), not patient-facing",
}

data = json.load(open(MERGED))
rows = data["classifications"] if isinstance(data, dict) else data
by = {r["location_id"]: r for r in rows}

missing = [l for l in list(RULES) + list(NORMALIZE) + list(UNDET_NOTES) if l not in by]
if missing:
    sys.exit(f"FATAL: location_ids not in merged file: {missing}")

applied = skipped = 0
bumped, errors = [], []
for lid, R in sorted(RULES.items()):
    r = by[lid]
    if MARKER in (r.get("reasoning") or ""):
        skipped += 1
        continue
    urls = [u for u in (r.get("evidence_urls") or []) if u]
    arts = [a for a in (r.get("evidence_artifacts") or []) if a]
    basis = r.get("evidence_basis") or "none"
    if urls:
        if basis not in URL_BASES and basis not in ART_BASES:
            basis = "web_verified"
    elif arts:
        if basis not in ART_BASES:
            errors.append(f"{lid}: no URLs and basis {basis} not artifact-based")
            continue
    else:
        errors.append(f"{lid}: ruled row has neither URLs nor artifacts")
        continue
    if str(r.get("primary_npi", "")).startswith("DA_"):
        errors.append(f"{lid}: DA_ synthetic in ruling table (should not happen)")
        continue
    conf = r.get("confidence") or "medium"
    if lid in KEEP_HIGH:
        conf = "high"
    elif R["conf"] == "medium" or conf == "low":
        if conf == "low":
            bumped.append(lid)
        conf = "medium"
    r["assigned_tier"] = R["tier"]
    r["network_id"] = R["net"]
    r["pe_backed"] = R["pe"]
    r["status"] = "classified"
    r["confidence"] = conf
    r["evidence_basis"] = basis
    if not r.get("owner_identity"):
        r["owner_identity"] = R["owner"]
    r["reasoning"] = (r.get("reasoning") or "").rstrip() + f" {MARKER}: {R['note']}]"
    applied += 1

norm = 0
for lid, net in NORMALIZE.items():
    r = by[lid]
    if r.get("network_id") != net:
        r["network_id"] = net
        if MARKER not in (r.get("reasoning") or ""):
            r["reasoning"] = (r.get("reasoning") or "").rstrip() + f" {MARKER}: network_id normalized to {net}]"
        norm += 1

noted = 0
for lid, why in UNDET_NOTES.items():
    r = by[lid]
    if MARKER in (r.get("reasoning") or ""):
        continue
    r["reasoning"] = (r.get("reasoning") or "").rstrip() + f" {MARKER}: remains undetermined — {why}]"
    noted += 1

if errors:
    print("ERRORS (rows NOT classified):")
    for e in errors:
        print("  " + e)

json.dump(data, open(MERGED, "w"), indent=1)
from collections import Counter
tiers = Counter(r["assigned_tier"] for r in rows)
print(f"applied={applied} skipped(idempotent)={skipped} normalized={norm} undet_noted={noted} conf_bumped_low_to_medium={len(bumped)}")
print("tier tally:", dict(tiers.most_common()))
print("bumped:", bumped)
