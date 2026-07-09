# R4 PM Network Rulings — 2026-07-09 (Fable)

Centralized rulings for the protected networks (≥10 locations, or flagged for
one-network-one-decision) surfaced by the census completion wave
(`merged_1259_rows.json`, sessions census_fresh_20260708 / census_recovery_20260708).
Extends DECISIONS_PM_20260702.md (NITTINGER_RACHEL T5, LABINOV_BORIS T5,
SHAFI_SOHAIL T3 remain ratified). Rulings are applied to member rows by
`apply_pm_rulings_20260709.py`; membership requires row-level evidence (brand
locator / own-site / durable prior-research artifact). Rows whose membership
or operating status could not be confirmed stay `undetermined` — fail-closed.

Tier semantics used throughout: T3 dentist_multi = dentist-owned multi-location
group, no third-party MSO/PE control. T4 stealth_dso = MSO/DSO-controlled,
locations keep local/independent branding. T5 branded_dso = locations carry the
chain's consumer brand. pe_backed=true only with a named institutional sponsor
documented in evidence.

## DSO / corporate networks

| Network | Ruling | network_id | pe_backed | Basis |
|---|---|---|---|---|
| 1st Family Dental | **T5 branded_dso** | brand:1st_family_dental | false | Founder Dr. Ghassan Abboud self-describes it as "one of the first DSO in Chicagoland"; 15–16 locations under one consumer brand; legal entity DENTAL CORPORATE USA; non-dentist COO (Vesna Belkic — resolves the BELKIC held name). No PE sponsor found. |
| United Dental Partners | **T4 stealth_dso** | brand:united_dental_partners | false | Self-described dentist-founded DSO, ~22–25 offices under member brands (Smiles for Families, Advanced Family Dental, Smilelist/PVR). Members keep local brands → stealth. No Calera/PE link confirmed. |
| Great Lakes Dental Partners | **T4 stealth_dso** | brand:great_lakes_dental_partners | **true** (Shore Capital Partners) | GLDP locator + shorecp.com portfolio listing; 23 IL + 5 IN. Adjudication: Advanced Family Dental & Orthodontics (Rubis) merged into GLDP 2018 per press release → AFD&O flagship (Crest Hill) is GLDP. The Naperville row whose GLDP-locator check failed stays undetermined. |
| Grove Dental Associates → NADG | **T4 stealth_dso** | brand:nadg | **true** | Grove acquired 2019 by North American Dental Group (PitchBook/MergerLinks; NADG careers page); Grove keeps its local brand. |
| GPS Dental | **T4 stealth_dso** | brand:gps_dental | **true** (Main Post Partners) | Becker's: Romeoville Dental Center/USP Dental added to GPS Dental Q2 2024; AO Marcus Mercer = friendly-PC nominal owner. |
| Smile Partners USA | **T4 stealth_dso** | brand:smile_partners_usa | false | SPU self-describes as the MSO behind 124–130 practices; Perfect Smiles (Halikias, 7 IL) booking infrastructure tagged smile_partners_usa. No PE sponsor documented. |
| Familia Dental | **T5 branded_dso** | brand:familia_dental | **true** (The Halifax Group) | ~31 clinics under the Familia Dental brand. |
| Dentologie | **T5 branded_dso** | brand:dentologie | **true** (Beringea, $25M Series B) | 13+ Chicago offices + Seattle under the Dentologie brand; institutional growth capital documented (Crain's + beringea.com). |
| P1 Dental Partners (ex-Cornerstone) | **T4 stealth_dso** | brand:p1_dental_partners | **true** (Prairie Capital / Centerfield / Huntington) | Cornerstone Dental Partners (Zieba) acquired by P1 Dec 2021; 60+ locations; North Suburban Dental keeps local brand. |
| Imagen Dental Partners | **T4 stealth_dso** | brand:imagen_dental_partners | false | Village Green Dentistry's own About page: "An Imagen Partner Practice"; Imagen IL locator; ~100 practices. No PE sponsor documented in evidence. |
| Aria Care Partners / SeniorWell | **T4 stealth_dso** | brand:aria_care_partners | **true** (Serent Capital) | SeniorWell acquired by Aria 2021; corporate onsite senior dental delivery. |
| Smile America Partners | **T4 stealth_dso** | brand:smile_america_partners | **true** (Morgan Stanley Capital Partners) | National mobile dentistry (Mobile Dentists/Smile Programs). Applied only to the co-founder row with documentary URLs; the Dental-Director row (LinkedIn-only chain) stays undetermined. |
| Elite Dental Partners | **T4 stealth_dso** | brand:elite_dental_partners | **true** (Cressey & Company) | elitedentalpartners.com + cresseyco.com + PitchBook; 75+ practices. |
| Rising Tide Dental Partners | **T4 stealth_dso** | brand:rising_tide_dental_partners | false | 27 practices / 11 states; Fatland co-founder; MSO role documented (GDN + own site). No PE sponsor documented. |
| Transparent Dental Group / Smile Obsession | **T5 branded_dso** | brand:smile_obsession | false | Self-described dentist-owned DSO ("Powered by Transparent Dental Group"), 17–18 locations under the Smile Obsession brand (Dr. Viren Patel). Dentist-owned but an explicit DSO platform with chain branding → T5, pe=false. |

## Dentist-owned multi-location groups (T3 dentist_multi, pe_backed=false)

| Network | network_id | Basis |
|---|---|---|
| Brite Dental / Dental 360 (Dr. Fadi Aqel) — resolves AQEL held name | brand:dental360 | Aqel DDS is President/owner (Absolute Dentistry Ltd; BBB); ~12–17 IL offices across Brite Dental + legacy Dental 360 branding; agents found no MSO/PE control. Single network id (ledger precedent brand:dental360). |
| Sonrisa Family Dental (Dr. Jason Korkus) | brand:sonrisa_family_dental | Founder/President since 2004, 11–12 IL locations; CDCoA management arm is Korkus-led, no third-party MSO evidence. Confidence capped at medium network-wide (residual CDCoA structure ambiguity). |
| Jubrail Sweis network | ao:SWEIS_JUBRAIL | 10-location IL reach (Manhattan Dental Care etc.), no PE/MSO signal. |
| Everyone's Family Dental (Dr. Funmi Adeleke-Babatunde) | brand:everyones_family_dental | Des Plaines row: Funwal LLC under EFD, 12+ IL locations. Owner-attribution conflict (Sweis vs Babatunde town overlap: Dixon/Utica/Normal/Danville) noted; either attribution is a dentist-owner with no MSO signal → T3 stands; thin rows stay undetermined. |
| Grand Dental Group (Dr. Steve Napier + partners) | brand:grand_dental_group | 12 offices, self-described 100% dentist-owned, no outside affiliations. |
| Webster Dental Care (Dr. Steven Rempas) | brand:webster_dental_care | Founder-led 9–12 offices; management co is Rempas's own. Covers Klyber post-merger row and the Weiss/CDP row (verify pass re-attributed it from UDP to Webster). |
| Reem Shafi network (Two Rivers / Ashton / Troy / Simply) | ao:SHAFI_SOHAIL | Extends the ratified SHAFI T3 ruling; ~10–27 IL locations, dentist CEO (Reem Shafi). Slug unified to ao:SHAFI_SOHAIL per QA pass — matches the 18 live DB rows; the 3 legacy ao:SHAFI_REEM DB rows go on the slug-cleanup list. |
| ProCare Dental Group (Brunetti/Crowley) — resolves BRUNETTI held name | brand:procare_dental_group | Family-owned, dentist-led (CEO Crowley DDS, President Brunetti DDS), 10 IL locations since 1979. Note: 2 of 4 member rows are DA_ synthetics and 1 fails locator membership — only the artifact-backed row classifies. |
| Illinois Dental Centers (Dr. Jacob Lake) | brand:illinois_dental_centers | Dentist-founded 10-location network, active. |
| Secure Dental (Drs. Jafri & Liu) | brand:secure_dental | Own site names dentist CEO/owner; ~11 offices IL/IN/IA; no MSO evidence → T3 per the same standard as Sonrisa/Sweis. |
| Scott Goldman network | ao:GOLDMAN_SCOTT | Single dentist owner across 10+ IL locations (multi-directory corroboration). |
| Best Image Dental, Inc. (Dr. Mary Cavitt) | brand:best_image_dental | BBB: Cavitt is president; 20 IL locations, census row confirmed a member. |
| Ahmed Mataria network (New Millennium Smiles / Optimal Dental Care) | ao:MATARIA_AHMED | AO owns/operates under multiple brands across 10+ IL cities; row = his own Joliet office. |
| Universal Dental Clinics (Dr. Ahmed Ramaha) — resolves RAMAHA held name | brand:universal_dental_clinics | Ratifies the agent's dentist_multi classification (founder, 2007). The 1605 S Michigan row (now CLEAR Immediate Care, non-dental) stays undetermined. |

## Ruled-undetermined dispositions (fail-closed, unchanged rows)

- **Residential / registration-artifact addresses**: Alramli, Bakir, Trinh rows.
- **Closed / turned-over locations**: Perla Dental turnover, First American Dental (closed), DentalWorks Woodfield (relocated), Ramaha 1605 S Michigan (now urgent care).
- **Verify-refuted evidence**: 86f0b24aac6e0fff, Everis Dental pair (everisdental.com is a parked GoDaddy domain), d4d827860b4132cb (Partners in Care ownership unresolved), 9550d33a7efdafdd (GLDP locator negative).
- **Membership unconfirmed**: 4f102207d0880e37, eb68bac52463172c, c1526a81500dbd53, 719b01502f151a50 (Cicero not on ProCare locator), 57d1141d853072c0 (not on Sonrisa locator), 6a762fd2de039d6e (Aspen unconfirmed), 173ffa7cc8c3e198 (Al Mufti attribution ambiguous), 5e92660ad5b32980 / e86d6e38d85a9aef (EFD attribution conflict), d99bc2c4d6d3f44a (LinkedIn-only chain).
- **DA_ synthetic NPIs** (validator bars classified status): All Family Dental & Braces ×2 (UDP members in fact), ProCare ×2, UDRC. Aspen c08edf0c9ab2cced keeps tier=branded_dso with status=undetermined (valid combo; tier is written).
- **Out-of-scope entities**: Lyric National (benefits company, not a clinic), UDRC/AmericaSmiles (association management), ClearChoice per ratified R2 (implant-only specialist brand), 8d81d4516f493d1e (R6 fail-closed stands), StomatCare (low confidence), Best-effort singletons with low confidence or open legal-entity questions (Blooming Smiles, Dhaval Shah, Almeleh, Envision A Smile — 3-location brand, no owner identified).

## Slug normalizations applied to already-classified rows in this batch

- `1st_family_dental` → `brand:1st_family_dental` (2 rows)
- `universal_dental_clinics` → `brand:universal_dental_clinics` (1 row)
- `aspen_dental` → `brand:aspen_dental` (1 row)

Known legacy DB slug inconsistencies for a later surgical cleanup (NOT part of
this write): `brand:dental_360` vs `brand:dental360`, `Grand Dental Group` vs
`brand:grand_dental_group`, `Dentologie (Chicago DSO)` vs `brand:dentologie`,
`Aspen Dental (TAG Oral Care Center)`, `ao:SHAFI_REEM` (3 rows) vs
`ao:SHAFI_SOHAIL`.

## QA pass fixes (census-qa-fable, 2026-07-09)

Applied by `apply_qa_fixes_20260709.py` after the rulings above; the file
re-validates clean. Summary of the adversarial QA verdict: institutional
12/12 clean; all sampled DSO tiers rest on documentary evidence; stratified
40 clean; fit to consolidate after these fixes.

- **Ratified-ruling contradiction**: 9279cc777453fb1d (Two Rivers) was
  classified stealth_dso — reverted to T3 dentist_multi per the ratified
  SHAFI ruling; slug ao:SHAFI_SOHAIL.
- **Refuted network linkages stripped from writable fields** (the write leg
  persists network_id/pe_backed even on undetermined rows):
  d4d827860b4132cb + b721ad68889ce64d (heartland_dental refuted),
  ccd94a511fe6d32a + 38d3d0a02dff7b6f (aspen refuted),
  9ff39651d697af30 (GLDP refuted) — network_id nulled, pe_backed=false.
- **Missing pe_backed=true corrected**: 29ded9c384c4e2e3 (Specialized Dental
  Partners — Quad-C), 7542f13e98b7bd0d (DentalOne/Sonrava — New Mountain
  Capital; slug ao:NITTINGER_RACHEL).
- **Pre-classified rows folded into the network rulings**:
  c2ddefdc5cef6aa2 (Grand Dental T5→T3), 3f92a54ef4d70d13 (Smile Obsession
  stealth→branded; the brand is patient-facing).
- **R5 closure adjudication** (fail-closed, ownership-at-closure kept in
  reasoning): 925b33f318557fe7 (Shah Family Streamwood, closed Jul 2025),
  bca301b92b2ede41 (MINT Northlake, closed Oct 2025), 2990d3b52d394795
  (Aspen Lockport, consolidated Apr 2026) → tier/status undetermined.
- **Same-practice split unified**: fe4e8aece6d7fd2e → decisionone_dental_partners
  (DecisionOne membership confirmed; Smile Brands is the upstream investor).
- **Dentologie pe_backed=true uniform** (PM decision: Beringea institutional
  growth capital counts as pe_backed); 3ec3e5c611e518e7 confidence capped
  medium (classic-PE sub-claim refuted).
- **Hygiene**: 9fe62bf8816a28c1 owner_identity (Aspen boilerplate) nulled;
  e45faab59b6a118f wrong artifacts (ADA EIN / Roncevic) scrubbed; network_id
  nulled on 4 T1/T2 rows where it was a same-practice merge key; 19+1 slug
  normalizations applied file-wide (aspen, 1st family, GLDP/CSG,
  smile_obsession, dentologie, two_rivers/SHAFI, sonrisa, partners_in_care,
  dentalworks→ao:NITTINGER_RACHEL, dent_sure, grand_dental_group).
- **Left for verification later**: royal_dental_care vs
  brand:royal_dental_care_il (likely same org, unconfirmed — not merged).
