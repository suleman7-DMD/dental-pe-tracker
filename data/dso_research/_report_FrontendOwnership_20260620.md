# Agent report — FrontendOwnership (Explore, read-only) — 2026-06-20

> Persisted by the lead session (Explore agents cannot write files; this is their returned final message verbatim). Agent at rest / idle. Charter: IA teardown of /warroom, /launchpad, /job-market, /market-intel for the ownership-directory revamp.

OWNERSHIP DIRECTORY REVAMP — COMPLETE IA AUDIT
Routes: /warroom, /launchpad, /job-market, /market-intel

Files read:
- warroom-shell.tsx, sitrep-kpi-strip.tsx, dossier-drawer.tsx (lines 1-1499), hunt-mode-panel.tsx (partial)
- src/lib/warroom/signals.ts, src/lib/warroom/ranking.ts, src/lib/supabase/queries/warroom.ts
- launchpad-shell.tsx, launchpad-kpi-strip.tsx, src/lib/launchpad/signals.ts, src/lib/launchpad/ranking.ts
- job-market-shell.tsx, ownership-landscape.tsx, saturation-table.tsx
- market-intel-shell.tsx, consolidation-map.tsx, dso-penetration-table.tsx, zip-score-table.tsx
- src/lib/constants/entity-classifications.ts, src/lib/constants/consolidation-honesty.ts

## SHARED FOUNDATION (applies to all 4 routes)

BINARY CHOKEPOINTS — the things that define "old model" blast radius:

1. `classifyPractice(ec, os)` in entity-classifications.ts:234
   Returns: "independent" | "corporate" | "specialist" | "non_clinical" | "unknown"
   This is the primary API every route calls. Under T1-T4, this becomes a tier resolver.

2. `INDEPENDENT_CLASSIFICATIONS` (entity-classifications.ts:164) — flat array of 7 values (solo_*, family_practice, small_group, large_group). All are treated identically for ownership purposes even though T1 (solo_established) vs T2 (large_group) are totally different in the new model.

3. `GP_LOCATION_CLASSIFICATIONS` (entity-classifications.ts:180) — INDEPENDENT_CLASSIFICATIONS + CORPORATE_CLASSIFICATIONS. Defines the canonical GP directory denominator. Will not change in shape for the revamp, only how the members are grouped/presented.

4. `OwnershipGroup` type (signals.ts:3–8) — "independent" | "corporate" | "specialist" | "non_clinical" | "unknown". This warroom-specific type is the binary model made explicit. All count functions, filter UIs, and KPI cards downstream of this type output one binary bucket.

5. `consolidation-honesty.ts` hardcoded constants:
   - ADA_HPI_DSO_AFFILIATION.IL.pctDentists = 14.6 (line ~76)
   - CONFIRMED_PER_DENTIST_CORPORATE.IL = { pct: 10.47, corp: 816, total: 7792 } (line ~133)
   - getCorporateBand() / CorporateBandBar — the 3-anchor band visualization. These are G1/G2 transition surfaces; the per-dentist anchor will need updating as new T3 stealth identifications move the floor.

## ROUTE: /warroom

(a) WHAT IT RENDERS

Mode: Hunt (target list + filters) / Investigate (ZIP + practice dossiers)
Lens: retirement | buyability | stealth | peer_pressure
Scope: 11 geographic presets (chicagoland, chicago_proper, north_shore, etc.)

Always-visible strip (SitrepKpiStrip, sitrep-kpi-strip.tsx):
  1. "Practices in Scope" — ownership.total (all GP location classes)
  2. "Confirmed Corporate" — ownership.corporate count + CorporateBand % via getCorporateBand()
  3. "High-Confidence" — countCorporateHighConfidence() result
  4. "Acquisition Ready" — buyability_score >= 50
  5. "Retirement Risk" — year_established < 1995 + INDEPENDENT_CLASSIFICATIONS
  6. "Avg Buyability" — mean buyability_score across GP locations
  7. "Confirmed Independent" — ownership.independent
  8. "Solo High-Volume" — entity_classification = solo_high_volume
  9. "Unknown / Unclassified" — ownership.unknown
  10. "Stealth Clusters" — signalCounts.stealthDsoClusters (practice_signals.stealth_dso_flag aggregated by ZIP)
  11. "Phantom Inventory" — signalCounts.phantomInventoryPractices (practice_signals.phantom_inventory_flag)
  12. "Pending Changes" — practice_changes count in last 90d

Hunt Mode Panel (hunt-mode-panel.tsx):
  - OwnershipGroup filter buttons (binary: independent / corporate / specialist / non_clinical / unknown)
  - Entity classification checkboxes (11 specific values in ENTITY_CLASSIFICATION_ORDER)
  - Practice signal flag checkboxes (8 flags)
  - ZIP signal flag checkbox (zip_ada_benchmark_gap_flag)
  - Target limit selector (25/50/100/200)
  - Tier floor (hot/warm/cool/cold)
  - excludeCorporate toggle (derived from filter.excludeFlags.includes("ownership:corporate"), warroom-shell.tsx:235–240)

Target List — ranked practices, each row shows:
  - practice_name, city, entity_classification label, tier badge, score, signal chips

Dossier Drawer (dossier-drawer.tsx) — 5 tabs per practice:
  Tab 1 Snapshot: ScoreBreakdownInline (component weights), Practice Economics (buyability, year, providers, employees, revenue), Identity & Contact (NPI, DBA, phone, website, taxonomy, entity_classification label concatenated with ownership_status, confidence), Corporate Signals section (parent_company, ein, franchise_name, affiliated_dso, affiliated_pe_sponsor — shown only when any non-null)
  Tab 2 Evidence: 8 practice signal flags + ZIP ada_benchmark_gap + change timeline
  Tab 3 Intel: practice_intel AI dossier
  Tab 4 Market: ZIP context — corporate_share_pct * 100, buyable_practice_ratio * 100, market_type, dld_gp_per_10k, people_per_gp_door (dossier-drawer.tsx:1157–1174)
  Tab 5 Actions: Google Maps / Zocdoc / HealthGrades links + "Find similar" intent

ZIP Dossier Drawer: ZIP-level signals, market type, per-ZIP corporate share, top practices
Living Map: mapbox dots colored by entity_classification / ownership / signal
BriefingRail: structured text output for warroom intent
PinboardTray: saved/pinned practices

(b) EVERY OWNERSHIP-TOUCHING SURFACE (exact provenance)

SITREP KPI "Confirmed Corporate":
  DB source: zip_scores.corporate_location_count via getWarroomSummary() → getOwnershipCountsByQuery() at warroom.ts:643–686
  Query: practice_locations WHERE entity_classification IN ('dso_regional','dso_national') + ownership_status fallback
  Display: corporateFloorPct = corporate / (total - specialist - nonClinical) * 100 in sitrep-kpi-strip.tsx:53–59
  Band: getCorporateBand(corporateFloorPct, "mixed") — passes live floor into 3-anchor band from consolidation-honesty.ts

SITREP KPI "High-Confidence":
  DB source: countCorporateHighConfidence() at warroom.ts:932–948
  Query: practice_locations WHERE entity_classification IN ('dso_national') OR (entity_classification = 'dso_regional' AND (ein IS NOT NULL OR parent_company IS NOT NULL))

SITREP KPI "Retirement Risk":
  DB source: countRetirementRisk() at warroom.ts:708–727
  Query: practice_locations WHERE entity_classification IN INDEPENDENT_CLASSIFICATIONS AND year_established < 1995

Ownership counts overall:
  getOwnershipCountsByQuery() warroom.ts:643–686
  Independent: entity_classification IN INDEPENDENT_CLASSIFICATIONS (7 values) OR ownership_status fallback
  Corporate: entity_classification IN ('dso_regional','dso_national') OR ownership_status fallback
  Returns: WarroomOwnershipCounts with total, independent, corporate, specialist, nonClinical, unknown, known, percentages

Hunt mode filter — entity_classification checkboxes:
  warroom-shell.tsx applies filter.entityClassifications as an .in() filter on practice_locations
  OwnershipGroup filter maps to binary: "independent" → INDEPENDENT_CLASSIFICATIONS, "corporate" → dso_regional/dso_national

Target ranking (ranking.ts):
  entityFitComponent() lines 141–164: GRADUATED within "independent" — solo_established=1.0, solo_high_volume=0.9, solo_new=0.75, solo_inactive=0.6, small_group=0.65, large_group=0.5, family_practice=0.4 — but grouped/presented as one binary independent bucket in KPIs
  corporatePenaltyComponent() lines 208–235: -1.0 weight for high-conf corporate (dso_national OR dso_regional with ein/parent/franchise), -0.45 for "phone-only" — does NOT split T3 stealth from T4 branded
  stealthDsoComponent() lines 368–388: -15 penalty for stealth_dso_flag
  HARDCODED tier thresholds: hot ≥ 80, warm ≥ 60, cool ≥ 40, cold < 40 (ranking.ts:426–431)
  HARDCODED weights: buyability=30, entityFit=15, corporatePenalty=-30, stealthDsoPenalty=-15 (lines 35–48)
  HARDCODED caps: CONFIDENCE_CAP=70, CONFIDENCE_FLOOR=40 (lines 50–51)

Dossier Snapshot tab — Identity field:
  dossier-drawer.tsx:924–927: shows entityLabel + " · " + practice.ownership_status concatenated — legacy field still user-visible
  Corporate Signals section renders when parent_company || ein || franchise_name || affiliated_dso (line 950)

Dossier Market tab:
  corporate_share_pct from zip_scores, correctly multiplied ×100 at dossier-drawer.tsx:1157–1162
  buyable_practice_ratio from zip_scores, correctly ×100 at lines 1168–1174

(c) BINARY MODEL ASSUMPTIONS

- OwnershipGroup type (signals.ts:3–8): the 4-category binary. Every filter UI, count accumulator, KPI label, and URL sync key in warroom uses this type. Changing to 4 tiers cascades to: hunt-mode-panel OWNERSHIP_OPTIONS (line 43–49), warroom.ts getOwnershipCountsByQuery(), WarroomOwnershipCounts type, warroom-shell excludeCorporate logic (line 235–240).
- "Confirmed Corporate" KPI collapses dso_regional and dso_national into one number — no T3/T4 split visible in the strip.
- Hunt mode entity classification checkboxes DO expose all 11 specific values (including dso_regional vs dso_national separately), but the OwnershipGroup parent bucket filter still treats all 7 INDEPENDENT_CLASSIFICATIONS identically.
- The stealthDsoComponent in ranking.ts penalizes stealth_dso_flag but doesn't LABEL it as T3 in any UI surface — it's a -15 modifier, invisible to the user beyond dropping the score.
- The dossier shows ownership_status still displayed alongside entity_classification (line 924–927) — a legacy artifact.

(d) HARDCODED VALUES

ranking.ts:
  - hot ≥ 80, warm ≥ 60, cool ≥ 40, cold < 40 (lines 426–431)
  - DEFAULT_WEIGHTS buyability=30, retirement=25, entityFit=15, enrichment=10, corporatePenalty=-30, stealthDsoPenalty=-15 (lines 35–48)
  - CONFIDENCE_CAP=70, CONFIDENCE_FLOOR=40 (lines 50–51)

sitrep-kpi-strip.tsx:
  - GP denominator: total - specialist - nonClinical (lines 53–57) — collapses the two excluded buckets at display time

consolidation-honesty.ts (shared):
  - ADA_HPI_DSO_AFFILIATION.IL.pctDentists = 14.6
  - CONFIRMED_PER_DENTIST_CORPORATE.IL.pct = 10.47 (corp=816, total=7792)

consolidation-map.tsx (market-intel, used by warroom sitrep as well):
  - Green at 0%, yellow at 15%, red at 30%+ (lines 22–40)

(e) GOAL TAGS

Warroom Sitrep KPI strip: G2 (ownership directory status) + G1 (deal catchment flags) + G3 (acquisition/retirement risk counts)
Hunt Mode filters + target list: G3 (acquisition-potential scoring built on directory)
Dossier Snapshot/Evidence/Market: G2 (per-practice ownership dossier — the core revamp surface)
Dossier Intel tab: G1 (AI research, not ownership taxonomy)
Living Map: G2 (spatial directory view)
BriefingRail: G1 + G3 composite

(f) WHAT MUST CHANGE / ADD / REMOVE FOR REVAMP

CHANGE:
- OwnershipGroup type: expand from binary to T1/T2/T3/T4. Every KPI accumulator, filter UI, and URL param key must adopt the new type. The central chokepoint is warroom.ts:getOwnershipCountsByQuery() — it must return WarroomTierCounts instead of WarroomOwnershipCounts.
- Sitrep "Confirmed Corporate" card: split into two cards or one card with T3/T4 sub-badges. "Stealth DSO (T3)" and "Branded DSO (T4)" are meaningful separately — T3 count is the investigative interest (stealthDsoComponent is already scoring it, just not displaying it).
- Hunt mode OwnershipGroup filter buttons: replace 5 binary group buttons with T1/T2/T3/T4 + specialist + non_clinical buttons.
- corporatePenaltyComponent in ranking.ts: split penalty between T3 and T4. T3 (stealth) warrants investigation, not necessarily pure penalty — a T3 practice is interesting corporate signal, not just "avoid."
- Dossier Snapshot Identity field: remove the ownership_status concatenation (line 924–927) — replace with explicit tier badge (T1 solo, T2 group, T3 stealth DSO, T4 branded DSO) + PE flag indicator.
- Target list row: add tier chip alongside entity_classification label.

ADD:
- `classifyTier(ec, signals)` helper in entity-classifications.ts: maps entity_classification + stealth_dso_flag → T1/T2/T3/T4. T1 = solo_*, T2 = family_practice/small_group/large_group (multi-location by inference) or just T2 = dentist-owned group, T3 = dso_regional, T4 = dso_national.
- WarroomTierCounts type with t1, t2, t3, t4, specialist, nonClinical, unknown fields.
- Sitrep tier breakdown row (below existing strip or as expansion): T1 count / T2 count / T3 stealth count / T4 branded count.
- "PE-backed" cross-cutting flag display: affiliated_pe_sponsor is already fetched in PRACTICE_SELECT (warroom.ts:41), and pe_recap_volatility_warning exists in launchpad ranking. Warroom should surface a PE flag badge on any practice where affiliated_pe_sponsor is not null, regardless of tier.
- Dossier "Tier" field: explicit T-level badge in Snapshot tab replacing the binary "Corporate / Independent" label.
- Hunt mode "T-Level" filter row.

REMOVE:
- ownership_status display from Dossier Snapshot tab (line 924–927) — it is the legacy field; entity_classification + tier are sufficient.
- The binary "Confirmed Corporate" label as the headline concept. It becomes T3 + T4 separately.

## ROUTE: /launchpad

(a) WHAT IT RENDERS

Header: scope selector (4 presets: Chicagoland, Chicago Proper, North Shore, South Suburbs), track switcher (all / succession / high_volume / dso), view toggle (list / map / split)

KPI Strip (launchpad-kpi-strip.tsx) — 6 cards:
  1. "GP clinics in scope" — summary.totalGpLocations (location-deduped) vs totalPracticesInScope (NPI row count)
  2. "Best-fit candidates" — sum of bestFit across all 3 tracks (score ≥ 80)
  3. "Mentor-rich" — solo_*, 25+ years, 2+ staff (mentorRichCount)
  4. "Hiring now" — hiringNowCount (source-backed practice_intel.hiring_active)
  5. "Avoid-tier DSOs" — avoidListCount (Aspen, Sage, Risas, Western)
  6. "Evidence coverage" — withIntelCount / totalCount

Main list (TrackList): ranked LaunchpadRankedTarget rows per track, each showing: practice name, location, tier chip, score, activeSignalIds chip set, dsoTier badge
Map (LaunchpadLivingMap): Mapbox pins colored by tier or entity_classification
Split: side-by-side list + map

PracticeDossier drawer (6 tabs):
  Tab "snapshot": practice basics, score, entity_classification, tier, signals fired, corporate signals
  Tab "score": per-track score breakdown with signal contributions and multipliers
  Tab "intel": practice_intel AI dossier
  Tab "signals": full signal list with reasoning per signal
  Tab "market": zip_scores context
  Tab "briefing": AI compound narrative via /api/launchpad/compound-narrative

PinboardPanel: saved pinned practices
RedFlagPatterns: co-occurrence matrix of warning signals across pinned set
SmartBriefingBuilder: generates briefing text from pinnedNpis

LaunchpadZipDossierDrawer: per-ZIP practice list sorted by track score

(b) EVERY OWNERSHIP-TOUCHING SURFACE

Signal evaluation (ranking.ts evaluateSignals()):
  CORPORATE_CLASSIFICATIONS = Set(["dso_regional","dso_national"]) — local const at ranking.ts:116
  notCorporate check: `cls == null || !CORPORATE_CLASSIFICATIONS.has(cls)` — for high_volume_ethical_signal (line 208)
  community_dso_signal fires when CORPORATE_CLASSIFICATIONS.has(cls) AND dsoTier === "tier1" OR "tier2" (line 253)
  dso_avoid_warning fires when cls === "dso_national" AND dsoTier === "avoid" (line 287)
  non_compete_radius_warning fires when cls === "dso_national" AND (dsoTier === "tier3" OR "avoid") (line 294)
  family_dynasty_warning fires when cls === "family_practice" (line 301)
  ghost_practice_warning fires when cls === "solo_inactive" (line 308)

Track scoring (ranking.ts scoreForTrack()):
  BASE_SCORE = 50 (hardcoded, line 97)
  CONFIDENCE_CAP = 70, CONFIDENCE_FLOOR = 40 (lines 98–99)
  hasThinData = intel == null OR classification_confidence < 40

Track multipliers (TRACK_MULTIPLIERS, lines 25–95):
  "dso" track multiplies community_dso_signal ×2.0, dso_avoid_warning ×1.5, non_compete_radius_warning ×1.5
  "succession" track multiplies succession_track_signal ×2.0, family_dynasty_warning ×1.5
  "high_volume" track multiplies high_volume_ethical_signal ×1.5, hiring_now_signal ×1.5

LaunchpadSummary.corporateSharePct (signals.ts:451): passed into bundle from server, used to display market context. Comes from zip_scores.corporate_share_pct — the same floor fraction used across all routes.

LaunchpadBundle filtered at server level: only GP-class practices are included (launchpad server route fetches with gpOnly=true)

DSO tier resolution (dso-tiers.ts, not directly read but referenced): resolveDsoTier(affiliated_dso, parent_company, franchise_name) → "tier1"/"tier2"/"tier3"/"avoid"/null. This is a RICHER classification than the binary — it already distinguishes 4 DSO subtiers. This is the proto-T4 detail that exists today but isn't promoted to the ownership directory.

LaunchpadPracticeRecord (signals.ts:271–305): includes entity_classification, ownership_status, affiliated_dso, affiliated_pe_sponsor, parent_company, ein, franchise_name — all ownership fields are fetched.

KPI "Avoid-tier DSOs":
  avoidListCount computed during bundle build — count of practices where resolveDsoTier() returns "avoid"
  Hardcoded AVOID list: Aspen, Sage, Western, Smile Brands, Risas (embedded in dso-tiers.ts)

(c) BINARY MODEL ASSUMPTIONS

- The track "dso" is itself a binary: you either route to DSO or you don't. Under T3/T4, this should differentiate — a T3 stealth DSO is NOT a "DSO associate" target, but a T4 branded Tier 1/2 DSO is. The current "dso" track scores both equally as "corporate" targets.
- mentorRichFires() checks SOLO_CLASSIFICATIONS only — correct for T1, but family_practice (T2 group with shared last name) is excluded even though a father-son practice could be a legitimate mentor setup. This is by design (family_dynasty_warning fires instead), but the new T2 label should make this explicit.
- The community_dso_signal check (cls === "dso_national" OR "dso_regional") makes no T3/T4 distinction — a dso_regional stealth DSO does NOT fire community_dso_signal. This is logically correct (stealth DSOs don't have structured associate programs), but it should be documented explicitly in the new model.
- LaunchpadPracticeRecord has ownership_status field (line 293) fetched alongside entity_classification. The score engine itself only uses entity_classification, but the dossier display may still show ownership_status.

(d) HARDCODED VALUES

ranking.ts:
  - BASE_SCORE = 50 (line 97)
  - CONFIDENCE_FLOOR = 40, CONFIDENCE_CAP = 70 (lines 98–99)
  - TRACK_MULTIPLIERS table (lines 25–95) — all weights hardcoded

signals.ts:
  - LAUNCHPAD_TIER_THRESHOLDS: best_fit ≥ 80, strong ≥ 65, maybe ≥ 50, low ≥ 35, avoid < 35 (lines 46–52)
  - Signal baseWeights (e.g., succession_track_signal=30, mentor_rich_signal=25, dso_avoid_warning=-40, non_compete_radius_warning=-25) — lines 88–268

launchpad-kpi-strip.tsx:
  - "score ≥ 80 in any track" — hardcoded threshold for bestFitTotal (line 84 tooltip)
  - "Solo, 25+ yrs, 2+ staff" — hardcoded mentorRich definition (line 94)

(e) GOAL TAGS

KPI strip (clinics, mentor-rich, hiring, evidence coverage): G2 (directory census) + G3 (job scoring)
Track list + scoring engine: G3 (job scoring built on directory)
"Avoid-tier DSOs" KPI: G2 (ownership quality signal for directory)
Practice dossier snapshot/score/signals: G3 (per-practice job opportunity assessment)
Practice dossier intel: G1 (AI research)
Market tab: G2 (ZIP context from directory)
DSO tier list in signals: G2 foundation (proto-T4 detail)

(f) WHAT MUST CHANGE / ADD / REMOVE FOR REVAMP

CHANGE:
- The "dso" track should differentiate T3 from T4. T3 stealth DSOs (dso_regional) should either be excluded from DSO associate scoring or get a heavy penalty, because stealth DSOs by definition don't present as DSO associate opportunities. Today, dso_regional and dso_national both trigger community_dso_signal if their dsoTier resolves to tier1/2 — that logic in evaluateSignals() at line 253 is correct only if dso_regional always stealth, but a real Heartland-under-local-name practice (dso_regional with known affiliated_dso) could be a legitimate tier1 DSO.
- mentorRichFires() check at ranking.ts:156–163: the `SOLO_CLASSIFICATIONS` gate (solo_* only) is correct for T1, but T2 (small_group, large_group) should get a "group practice with multiple providers" positive signal in the high_volume_ethical track, not fall through to a lower implicit score.
- The hardcoded AVOID DSO list in dso-tiers.ts needs ongoing maintenance. Under the new model, the T3/T4 split should inform which dsoTier categories are apply-avoid vs investigate.
- LaunchpadPracticeRecord: remove ownership_status from the type or mark it @deprecated — entity_classification is primary everywhere in the scoring engine already.

ADD:
- T-level field on LaunchpadRankedTarget: t1/t2/t3/t4 derived from entity_classification at bundle-build time. Surface as a chip on each target card.
- PE flag badge: affiliated_pe_sponsor is already fetched (signals.ts:299) — surface it as a cross-cutting badge on any ranked target where it is non-null.
- "T2 groups" KPI in the strip: current strip shows mentor-rich (T1 focus) and avoid-tier DSOs (T4 red flag), but has no summary of T2 (dentist-owned multi-provider groups). A T2 count would be "group practices, not PE" — the honest dental employment segment.
- Filter by tier (T1/T2/T3/T4) in the scope/track header area.

REMOVE:
- Nothing critical to remove; the track/signal structure maps cleanly onto T1–T4 once the tier field exists. ownership_status in LaunchpadPracticeRecord can be deprecated.

## ROUTE: /job-market

(a) WHAT IT RENDERS

Header: Job Market Intelligence with description "where are independent practices, and where is consolidation squeezing out opportunity?"
DataFreshnessBar: totalPractices, daEnriched, lastUpdated
LivingLocationSelector: 4 presets (Chicagoland / Chicago Proper / North Shore / South Suburbs)
Loading spinner when fetching for non-default location

KPI Row 1 (6 cards):
  1. "Tracked Clinics" — gpLocations (zip_scores.total_gp_locations sum) vs total_p (raw GP-class row count)
  2. "Independent %" — indep_pct = indep_cnt / total_p
  3. "Confirmed Corporate" — allSignals_pct = allSignalsCorporate / total_p, with getCorporateBand() band + corporateBandSubtitle/Tooltip
  4. "Avg Buyability" — mean buyability_score
  5. "10+ Staff" — large_count (employee_count >= 10)
  6. "Retirement Risk" — practices independent + year_established < currentYear - 30

KPI Row 2 (3 cards with captions):
  7. "Avg Dental Density" — avgDldVal from zip_scores.dld_gp_per_10k average
  8. "Buyable Practice %" — avgBpr from zip_scores.buyable_practice_ratio average × 100
  9. "High-Volume Solos" — highVolCount (entity_classification = solo_high_volume)

Unknown ownership warning banner (shown when unk_pct > 30%)

4 Tabs:
  Overview: SaturationTable + SaturationMap + ADABenchmarks + OpportunitySignals (lazy)
  Map: PracticeDensityMap (Mapbox hex+dot)
  Directory: PracticeDirectory (table of all practices with score)
  Analytics: MarketOverviewCharts + OwnershipLandscape + MarketAnalytics

(b) EVERY OWNERSHIP-TOUCHING SURFACE

KPI "Confirmed Corporate":
  DB path (server-side, page.tsx serverKpis): pre-computed isCorporateClassification count passed as serverKpis.allSignalsCorporate
  Client-side recompute for non-default locations (computeClientKpis(), job-market-shell.tsx:277–334):
    dso_cnt: classifyPractice(ec, os) === "corporate" — binary
    highConfCorporate: dso_national (non-taxonomy-leak) + dso_regional with ein/generic brand/parent_company/franchise/branch in classification_reasoning
  Display: allSignals_pct = allSignalsCorporate / total_p, then getCorporateBand(allSignals_pct, 'mixed') (lines 591–603)

KPI "Independent %":
  indep_pct = indep_cnt / total_p — isIndependentClassification() applied to all 7 INDEPENDENT_CLASSIFICATIONS treated identically (binary)

KPI "Retirement Risk":
  isIndependentClassification(ec) AND year_established < currentYear - 30 (job-market-shell.tsx:317–319)

computeZipStats() (job-market-shell.tsx:112–168):
  Loops all practices, calls classifyPractice() → binary corporate / independent / unknown
  consolidated_count = dso_affiliated_count (corporate-classified)
  consolidation_pct_of_total uses GP denominator (excludes specialist/non_clinical/org_only_npi/da_unverified/duplicate_location)
  pe_backed_count is HARDCODED to 0 (const pe_backed_count = 0, line 125) — pe-backed is not computed

SaturationTable (saturation-table.tsx):
  "Corporate %" column: zip_scores.corporate_share_pct * 100 (correctly ×100, line 102)
  Color thresholds HARDCODED: green < 5%, amber 5–15%, red > 15% (saturation-table.tsx:33–39)
  "Buyable %" column: zip_scores.buyable_practice_ratio * 100 (correctly ×100, line 100)
  Color thresholds HARDCODED: green > 40%, amber 20–40%, red < 20% (lines 24–30)
  "DLD-GP/10k" national average HARDCODED: ~6.1 comment in saturation-table.tsx:14 and helpText line 180

OwnershipLandscape (ownership-landscape.tsx — Analytics tab):
  Ownership Status Bar chart: loops filteredPractices, groups by entity_classification verbatim (not binary), calls getEntityClassificationLabel() (lines 42–56) — this is the most granular ownership chart on the page
  Practice Size Distribution: solo 1–4 / small group 5–9 / large group 10+ by employee_count — size taxonomy unrelated to T-tier
  Top DSOs Table: loops corporate-classified practices, groups by affiliated_dso name (lines 79–93) — already brand-level detail
  DSO Penetration by ZIP: from zip_scores.corporate_share_pct (lines 104–115) — binary corporate %

(c) BINARY MODEL ASSUMPTIONS

- computeZipStats() produces dso_affiliated_count and pe_backed_count=0 — pe_backed is never computed because there is no separate pe-backed field distinct from entity_classification. Under the new model, PE backing is a cross-cutting flag on top of T1–T4.
- The OwnershipLandscape Ownership Status bar chart already shows individual entity_classification values (not binary), so it is the closest existing surface to a T1–T4 breakdown. But it uses the raw entity_classification labels (Solo Established, Family Practice, etc.) without the tier framing.
- ZipStats type (job-market-shell.tsx:80–90) has dso_affiliated_count, pe_backed_count (always 0), unknown_count — these are pre-binary-model fields that conflate the classification with the count.
- highConfCorporate sub-KPI exists (line 368 in computeClientKpis) but is not displayed as a separate card — it is computed but only used as highConfCorporate field. The display shows only allSignals_pct (the binary corporate %).

(d) HARDCODED VALUES

job-market-shell.tsx:
  - pe_backed_count = 0 (line 125) — hardcoded
  - currentYear - 30 as retirement threshold (line 319) — note: warroom uses year_established < 1995 which is a fixed cutoff, job-market uses currentYear - 30 which is dynamic. These two are inconsistent.
  - Unknown warning threshold: unk_pct > 30 (line 668)

saturation-table.tsx:
  - DLD thresholds: green < 6.1, amber 6.1–10, red > 10 (lines 16–20) — "national avg ~6.1" referenced in helpText
  - Buyable % thresholds: green > 40%, amber 20–40%, red < 20% (lines 24–30)
  - Corporate % thresholds: green < 5%, amber 5–15%, red > 15% (lines 33–39)

consolidation-honesty.ts (shared, see warroom section)

(e) GOAL TAGS

KPI "Tracked Clinics", density, saturation table, saturation map: G2 (directory census, market context)
KPI "Confirmed Corporate" + CorporateBandBar: G2 (ownership directory status surface)
KPI "Avg Buyability", "10+ Staff", "Retirement Risk", "High-Volume Solos": G3 (acquisition-potential and job scoring)
Overview tab SaturationTable: G2 + G3
ADABenchmarks: G1 (PE/DSO macro context)
OpportunitySignals: G3 (job scoring from directory)
Map tab PracticeDensityMap: G2 (spatial directory)
Directory tab PracticeDirectory: G2 (core directory listing)
Analytics OwnershipLandscape: G2 (ownership breakdown by classification)
Analytics MarketAnalytics: G3 (market opportunity analysis)

(f) WHAT MUST CHANGE / ADD / REMOVE FOR REVAMP

CHANGE:
- computeZipStats(): replace binary dso_affiliated_count with tier-split t1_count, t2_count, t3_count, t4_count. pe_backed_count can remain as a cross-cutting flag count (affiliated_pe_sponsor IS NOT NULL). Retire the binary dso_affiliated_count / pe_backed_count fields from ZipStats type.
- KPI "Independent %" should split into T1 % + T2 % sub-rows, matching the "per-location floor vs per-dentist floor" band model. All 7 INDEPENDENT_CLASSIFICATIONS grouped under one "Independent" bucket obscures the T1/T2 distinction that new grads care about.
- Retirement risk threshold inconsistency: job-market uses currentYear - 30 (dynamic), warroom uses year_established < 1995 (fixed). Pick one and make both routes match.
- OwnershipLandscape Ownership Status chart: rename from "Ownership Status" to "Practice Tier Distribution" and map entity_classification values to T1/T2/T3/T4 groups with tier labels. The existing per-classification bar chart already does the right thing — it just needs tier labels and color coding.

ADD:
- T2 group KPI card: "Dentist-owned Groups" count (family_practice + small_group + large_group) as a separate card. This is the segment most interesting for high-volume associate positions.
- PE flag count KPI: practices where affiliated_pe_sponsor IS NOT NULL, as a cross-cutting badge.
- Tier breakdown row in SaturationTable: T1 / T2 / T3 / T4 columns per ZIP, replacing or complementing the single "Corporate %" column.

REMOVE:
- ZipStats fields dso_affiliated_count and pe_backed_count (always 0) from the interface. Replace with tier-split fields.

## ROUTE: /market-intel

(a) WHAT IT RENDERS

3 Tabs: Consolidation | ZIP Analysis | Ownership

Consolidation Tab:
  KPI Row (4 cards):
    1. "Tracked Clinics" — totalGpLocations from SUM(zip_scores.total_gp_locations)
    2. "Confirmed Corporate" — kpis.allSignalsPct = corporate/gpDenom*100, + CorporateBandBar with 3-anchor band
    3. "Independent" — kpis.indepPct
    4. "Unclassified GP" — kpis.unknownCount
  CorporateBandBar component: proportional track visual, 3 markers (location floor, per-dentist floor, ADA anchor)
  ConsolidationMap: Mapbox bubble map, ZIPs colored by corporate_share_pct (green 0% → yellow 15% → red 30%+)
  DSOPenetrationTable: ZIPs ranked by corporate_share_pct, shows GP Locations + Corporate Share % colored by thresholds

ZIP Analysis Tab:
  ZipScoreTable: per-ZIP table with total_practices, gp_locations, corporate_count, independent_count, consolidation_pct, independent_pct, unknown_pct, confidence, opportunity_score, market_type
  Metro filter dropdown: "Chicagoland" vs individual metro subsets (selects by state or metro_area)

Ownership Tab:
  ecBreakdown bar chart: loops ENTITY_CLASSIFICATIONS grouped by category ('solo', 'group', 'corporate', 'other'), shows count per classification from entityCounts prop
  Signal quality note (HARDCODED static string): "Classification is based on..." (lines 418–458)
  Methodology notes (HARDCODED static text)

(b) EVERY OWNERSHIP-TOUCHING SURFACE

KPI "Confirmed Corporate":
  DB path (page.tsx server component): classificationCounts.corporate from getOwnershipCounts() query against practice_locations WHERE entity_classification IN ('dso_regional','dso_national')
  gpDenom: classificationCounts.total - classificationCounts.specialist - classificationCounts.nonClinical (market-intel-shell.tsx lines ~243–265, per sitrep pattern)
  kpis.allSignalsPct = corporate / gpDenom * 100
  getCorporateBand(allSignalsPct, 'mixed') passes live floor into 3-anchor band

KPI "Independent":
  classificationCounts.independent = count WHERE entity_classification IN INDEPENDENT_CLASSIFICATIONS

KPI "Unclassified GP":
  classificationCounts.unknown = count of org_only_npi + null + any unrecognized ec

ConsolidationMap (consolidation-map.tsx):
  consolPct = zip_scores.corporate_share_pct * 100 (line 77)
  corporateFromSaturation = corporate_share_pct * total_gp_locations (line 70–73)
  Falls back to legacy dso_affiliated_count + pe_backed_count from zip_scores (line 72)
  Color thresholds HARDCODED: 0% green, 15% yellow, 30% red (lines 22–40)

DSOPenetrationTable (dso-penetration-table.tsx):
  Source: zip_scores.corporate_share_pct * 100 (line 34)
  Color: red ≥ 30%, amber ≥ 15%, green < 15% (lines 63–65)

ZipScoreTable (zip-score-table.tsx):
  corporateCount: corporate_share_pct * total_gp_locations (primary) OR dso_affiliated_count + pe_backed_count (legacy fallback, lines 38–43)
  indepCount: zip_scores.independent_count if > 0, else gpLoc - corporateCount (lines 44–48)
  consolPct = corporate_share_pct * 100 (line 51)
  Columns include corporate_count and independent_count — binary split

Ownership Tab ecBreakdown:
  Groups ENTITY_CLASSIFICATIONS by category ("solo", "group", "corporate", "other") from entity-classifications.ts
  Shows count from entityCounts prop (Record<string, number> from server)
  This IS the per-classification breakdown — closest existing surface to a tier directory

Metro filter (market-intel-shell.tsx lines 143–168):
  For non-Chicagoland selections: computes corporateCount from corporate_share_pct * total_gp_locations per ZIP (line 148)
  Binary: corporate vs total_gp_locations — no tier split

(c) BINARY MODEL ASSUMPTIONS

- All 4 KPIs (Tracked, Corporate, Independent, Unknown) use binary buckets. There is no T2 "dentist-owned group" vs T1 "true solo" visible anywhere in the KPIs or the Consolidation tab.
- ConsolidationMap colors by corporate_share_pct (binary corporate %) — no T3/T4 split spatial visualization.
- ZipScoreTable has consolidation_pct and independent_pct but no tier columns.
- The legacy fallback in ZipScoreTable (dso_affiliated_count + pe_backed_count) — pe_backed_count is a pre-entity_classification field that is mostly null in the current DB. The fallback path exists for historical rows but is dead weight for current data.
- Ownership Tab ecBreakdown groups by ENTITY_CLASSIFICATIONS category ("solo", "group", "corporate", "other") which is already close to T1/T2/T3/T4 — "solo" = T1, "group" = T2, "corporate" = T3+T4. The new model maps almost perfectly onto the existing category taxonomy.

(d) HARDCODED VALUES

consolidation-map.tsx:
  - 0% = green, 15% = yellow, 30%+ = red (lines 22–40)

dso-penetration-table.tsx:
  - red ≥ 30%, amber ≥ 15%, green < 15% (lines 63–65)

market-intel-shell.tsx:
  - gpDenom computed as total - specialist - nonClinical (same sitrep pattern)
  - ALL_CHICAGO_SCOPE = 'Chicagoland' string const (line 64)

consolidation-honesty.ts (shared, all hardcoded anchor constants)

Ownership Tab methodology text: entirely static strings, no dynamic figures

(e) GOAL TAGS

Consolidation tab KPIs + CorporateBandBar: G2 (ownership directory macro snapshot) + G1 (macro PE consolidation tracking)
ConsolidationMap: G2 (spatial directory)
DSOPenetrationTable: G2 (per-ZIP corporate concentration)
ZIP Analysis ZipScoreTable: G2 + G3 (market opportunity scoring)
Ownership Tab ecBreakdown: G2 (directory taxonomy breakdown — the core G2 analytics surface)
Methodology static text: G1 (transparency/honesty layer)

(f) WHAT MUST CHANGE / ADD / REMOVE FOR REVAMP

CHANGE:
- Consolidation tab KPI "Confirmed Corporate": split into "T3 Stealth DSO %" and "T4 Branded DSO %" KPI cards. The combined binary corporate % can remain as a header, but the sub-cards clarify the investigative vs map surfaces.
- ConsolidationMap: add a second coloring mode toggle — "By Corporate %" (existing) vs "By Tier Distribution" (choropleth by dominant tier or T3 density). This would immediately show the stealth-DSO concentration pattern.
- ZipScoreTable: add tier columns (T1/T2/T3/T4 counts) or replace consolidation_pct with tier-split percentages.
- Ownership Tab ecBreakdown groupings: relabel "solo" → "T1 True Independent", "group" → "T2 Dentist-Owned Group", "corporate" → "T3/T4 DSO" (split by dso_regional vs dso_national). The category taxonomy in ENTITY_CLASSIFICATIONS already encodes this — it just needs renamed labels.

ADD:
- "PE-Backed Practices" count on Consolidation tab: affiliated_pe_sponsor IS NOT NULL count as a cross-cutting row below the 4 KPIs.
- Tier treemap or stacked bar in Ownership Tab: T1 / T2 / T3 / T4 absolute counts with % share, replacing the flat ecBreakdown bar chart. The data already exists in entityCounts.
- Dynamic methodology text: replace the hardcoded static strings with data-driven text showing "of N GP clinics, X are T1, Y are T2, Z are T3 (stealth), W are T4 (branded)" rather than static prose.

REMOVE:
- Legacy ZipScoreTable fallback: dso_affiliated_count + pe_backed_count fallback in zip-score-table.tsx:42–43 — dead weight for current data. Remove or wrap in a comment that says "pre-entity_classification rows only."
- Hardcoded static methodology strings in Ownership tab. Compute from live data.

## CROSS-ROUTE BLAST RADIUS SUMMARY

SINGLE-POINT CHANGES (changes here cascade everywhere):

1. entity-classifications.ts — ADD `classifyTier(ec, signals?)` returning T1 | T2 | T3 | T4 | specialist | non_clinical | unknown. Every route's ownership KPI and filter can consume this instead of calling classifyPractice() → binary.
   - T1: solo_established, solo_new, solo_inactive, solo_high_volume
   - T2: family_practice, small_group, large_group
   - T3: dso_regional (stealth/PE under local name)
   - T4: dso_national (branded DSO)
   PE flag: affiliated_pe_sponsor IS NOT NULL, orthogonal to tier.

2. consolidation-honesty.ts — ADD `getCorporateTierBand()` that returns T3 + T4 sub-percentages alongside the current 3-anchor structure. The existing getCorporateBand() can remain for backward compat; the new function enables tier-aware tooltip text.

3. warroom.ts getOwnershipCountsByQuery() — Change return type to include t1/t2/t3/t4 counts. This is the primary DB query factory — every route's KPI strip derives from a variant of this pattern.

4. classifyPractice() — Can be deprecated in favor of classifyTier(). Or extended: classifyPractice() continues to return binary for backward compat; classifyTier() added alongside for new tier-aware surfaces.

PER-ROUTE SURFACES WITH NO BINARY ASSUMPTION (already tier-ready or goal G1, no change needed):
- Dossier drawer Corporate Signals section (parent_company / ein / franchise_name / affiliated_dso / affiliated_pe_sponsor) — already granular
- Practice signal flags (stealth_dso_flag etc.) — already sub-classification signals
- DSO tier list in launchpad (tier1/tier2/tier3/avoid) — already richer than binary
- Launchpad evaluateSignals() — already uses entity_classification value directly, not classifyPractice()
- OwnershipLandscape Ownership Status bar chart — already per-classification
- Ownership Tab ecBreakdown — already per-classification grouped by category

SURFACES REQUIRING ONLY LABEL CHANGES (data already correct, presentation binary):
- SaturationTable "Corporate %" column → split into T3 % + T4 % columns
- Consolidation KPI "Confirmed Corporate" → "T3 + T4 DSO" with sub-labels
- Job Market "Independent %" → T1 % + T2 % sub-breakdown

SURFACES REQUIRING LOGIC CHANGES (not just labels):
- OwnershipGroup type in signals.ts → replace with TierGroup type
- Hunt mode filter buttons → T1/T2/T3/T4 checkboxes replacing binary OwnershipGroup
- ranking.ts corporatePenaltyComponent() → differentiate T3 vs T4 penalty
- Launchpad "dso" track → gate on T4 (branded DSO) only, not T3 stealth
- ZipStats type and computeZipStats() → tier-split counts replacing binary dso_affiliated_count
