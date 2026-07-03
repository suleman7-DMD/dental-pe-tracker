# Agent report — FrontendCrossCut (Explore, read-only) — 2026-06-20

> Persisted by the lead session (Explore agents cannot write files; this is their returned final message verbatim). Agent at rest / idle. Charter: IA teardown of /, /deal-flow, /buyability, /research, /intelligence, /system, /data-breakdown + cross-cutting ownership machinery. Read-only; no files edited, no builds run, no git operations.

INFORMATION ARCHITECTURE AUDIT — FULL REPORT

## PART 1 — ROUTE TEARDOWNS

### ROUTE: / (Home)
Files: src/app/page.tsx, src/app/_components/home-shell.tsx

Tabs/sections: Single page, no tabs. 6 KPI cards + recent deals feed + activity feed.

KPIs that touch ownership/corporate/consolidation:
  1. "Confirmed Corporate" KPI card (home-shell.tsx:371-385)
     - Value: summary.consolidatedPct (string like "5.58%")
     - Source chain: page.tsx calls getPracticeStats() → practices.ts:245
       returns (corporate / totalGpLocations * 100).toFixed(1)+"%"
       where corporate = dso_regional + dso_national counts from practice_locations
     - Subtitle: corporateBandSubtitle(getCorporateBand(parseFloat(consolidatedPct), 'mixed'))
     - Tooltip: corporateBandTooltip(getCorporateBand(...))
     - home-shell.tsx:374-383 (band calls at :377-383)
  2. "Acquisition Targets" KPI: getAcquisitionTargetCount() → buyability_score >= 50, no ownership filter
  3. "Retirement Risk" KPI: getRetirementRiskCount() → INDEPENDENT_CLASSIFICATIONS + year_established < 1995
  4. "Practices Tracked" KPI: GLOBAL_PRACTICE_NPI_COUNT (hardcoded constant from data-snapshot.ts)

Activity feed (home-shell.tsx:196):
  - Recognizes ownership_change, ownership_status, affiliated_dso as field-change types
  - These are detected from practice_changes rows, not entity_classification

Hardcoded values:
  - page.tsx:65: fallback consolidatedPct: '--' while loading
  - GLOBAL_PRACTICE_NPI_COUNT in data-snapshot.ts (381,598)

Goals: G1 (deals feed), G2 (corporate KPI, retirement/acquisition counts)

Under revamp:
  - "Confirmed Corporate" KPI card must decompose or at minimum show T2+T3+T4 vs just T3+T4.
    The value currently = (dso_regional+dso_national)/total_gp_locations. Under multi-tier that
    would need a new "consolidated %" = (T2+T3+T4)/total and a separate "DSO/PE penetration %" = (T3+T4)/total.
  - The corporate band (floor→per-dentist→ADA anchor) is valid for T3+T4 only; T2 needs its own band or exclusion.
  - Activity feed field detection unchanged; no structural break.

### ROUTE: /deal-flow
Files: src/app/deal-flow/page.tsx, deal-flow-shell.tsx, deals-table.tsx

Tabs/sections: 4 tabs: Overview | Sponsors | Geography | Deals. All client-side filter on initialDeals (fetched server-side)

Ownership/corporate touches:
  - deals-table.tsx imports ownershipColor from design-tokens.ts but deals themselves
    do not have entity_classification — the color is applied to the deal's target_type
    or ownership_status field on deal rows, not practice classification.
  - No corporate %, no consolidated count, no band displayed anywhere.
  - pe_sponsor is the PE-flag signal here.

Hardcoded: none relevant to ownership taxonomy.
Goals: G1 exclusively.

Under revamp: Largely unchanged. The pe_sponsor / platform fields ARE the revamp's
"PE-backing as cross-cutting flag" — no new taxonomy work needed here. If revamp adds
a T3/T4 breakdown, deal-flow can optionally surface "deals by DSO tier" from sponsor data,
but the route itself needs no structural change.

### ROUTE: /buyability
Files: src/app/buyability/page.tsx, buyability-shell.tsx

Tabs/sections: Single page, no tabs. 4 KPI cards + ZIP filter + sortable table + CSV export.

KPIs and categorization:
  - buyability-shell.tsx:37-57, function categorize(p):
      specialist  → "specialist" bucket
      isCorporateClassification(ec) → "dead_end" bucket  [dso_regional OR dso_national]
      non_clinical → "dead_end" bucket
      isIndependentClassification(ec) + buyability_score >= 50 → "acquisition_target"
      isIndependentClassification(ec) + buyability_score < 50 → "job_target"
  - 4 KPI cards: Acquisition Targets / Dead Ends (corporate+non_clinical) / Job Targets / Specialists

Hardcoded: none; categorize() uses canonical helpers from entity-classifications.ts.
Goals: G2, G3.

Under revamp:
  - "Dead Ends" = isCorporateClassification() → currently T3+T4 only. Under multi-tier T2
    (dentist-owned groups) are NOT dead-ends for acquisition. Revamp must split "Dead End"
    label: T3/T4 = "DSO/PE-backed" (truly off-market), T2 = potentially acquirable group practices.
  - T3 stealth DSOs currently appear as independent because classifier hasn't confirmed them;
    revamp may surface them as a distinct bucket.
  - The binary isCorporateClassification() call at line :44 is the single choke-point — replace
    with tiered check once T1-T4 groupings exist.

### ROUTE: /research
Files: page.tsx, research-shell.tsx, sponsor-profile, platform-profile, state-deep-dive, sql-explorer

Tabs/sections: 4 tabs: PE Sponsor Profile | Platform Profile | State Deep Dive | SQL Explorer

Ownership/corporate touches:
  - No direct corporate %, no consolidation KPIs.
  - State Deep Dive tab may show ownership-level data from ada_hpi_benchmarks and state-level deal counts, but the shell itself doesn't compute any corporate %.
  - SQL Explorer allows ad-hoc entity_classification queries including ownership-filtered ones.
  - sql-presets.ts:17 has inline "dso_regional","dso_national" in a preset SQL string.

Goals: G1 primarily, G3 tangentially.
Under revamp: No structural change needed. sql-presets.ts:17 inline literal is non-canonical but only affects a UI-surfaced preset query — update the string once T3/T4 labels are settled.

### ROUTE: /intelligence
Files: page.tsx, intelligence-shell.tsx

Tabs/sections: Single page: 6 KPI cards + ZIP intel table + Practice dossier table (expandable panels)

KPIs: ZIPs Researched, ZIP Coverage, Practices Researched, High Readiness, Total Research Cost, Avg Confidence
  - "acquisition_readiness" is an AI-generated string field (high/medium/unlikely/unknown) from practice_intel, NOT derived from entity_classification.
  - No corporate % KPI displayed.

Goals: G3.
Under revamp: Minimal impact. The "High Readiness" KPI is purely AI-generated readiness scoring, independent of ownership taxonomy. If revamp adds T-tier labels to practice_intel or to the dossier surface, this page would benefit from filtering by tier — but no structural ownership logic changes here.

### ROUTE: /system
Files: page.tsx, system-shell.tsx, manual-entry-forms.tsx

Tabs/sections: Single page: data freshness/coverage/completeness bars, scraper health, pipeline log, manual entry form.

Ownership/corporate touches:
  - manual-entry-forms.tsx:355: inline string literals for entity_classification dropdown:
      ['dso_regional', 'dso_national', 'specialist', 'non_clinical', ...]
    This is a hardcoded UI option list — NOT imported from ENTITY_CLASSIFICATIONS array.
  - No corporate % displayed.

Goals: Admin/ops.
Under revamp: If new T-tier classification values are added to entity_classification, the manual-entry dropdown (manual-entry-forms.tsx:355) must be updated — it is a literal array, not driven by ENTITY_CLASSIFICATIONS. This is a known maintenance risk.

### ROUTE: /data-breakdown
Files: page.tsx, data-breakdown-shell.tsx

Tabs/sections: Single page: searchable provenance blocks, filtered by category (practices/locations/deals/zips/intel). Each block in the DataBreakdownBundle explains where a KPI number comes from.

Ownership/corporate touches:
  - Surfaces narrative provenance for the same corporate % KPIs shown on Home/Market Intel.
  - No additional computation — purely display of pre-computed provenance strings.

Goals: G2 transparency.
Under revamp: The provenance blocks themselves will need rewriting to describe T1/T2/T3/T4 logic once the revamp ships — but no code logic changes in this file itself, just updated prose constants.

## PART 2 — CROSS-CUTTING OWNERSHIP MACHINERY

### A. CANONICAL CLASSIFICATION FILE — src/lib/constants/entity-classifications.ts

1. ENTITY_CLASSIFICATIONS array (14 entries with category "solo"|"group"|"corporate"|"other")
   - Current groupings: solo_* → "solo"; family_practice/small_group/large_group → "group"; dso_regional/dso_national → "corporate"; rest → "other"
   - Under revamp: "solo" = T1; "group" = T2 (dentist-owned multi-location); "corporate" = T3+T4. The category strings on each entry ARE the natural hook for tier assignment.
   - duplicate_location is defined here (:56-63) — maps to "other", excluded from all denominators.

2. isIndependentClassification(ec) — :130-142
   Returns true for: solo_established, solo_new, solo_inactive, solo_high_volume, family_practice, small_group, large_group (7 values).
   Under revamp: conflates T1 (solos) and T2 (groups). Needs split into isT1Classification() and isT2Classification(), or an optional tier param.

3. isCorporateClassification(ec) — :145-149
   Returns true for: dso_regional, dso_national only.
   Under revamp: maps to T3+T4. Unchanged for the "DSO/PE penetration" metric. But "Consolidated %" = T2+T3+T4 needs a new isConsolidatedClassification() that includes groups.

4. classifyPractice(ec, os) — :215-234
   Returns: "independent"|"corporate"|"specialist"|"non_clinical"|"unknown"
   Under revamp: 5-way output becomes 6-way: T1/T2/T3/T4/specialist/non_clinical/unknown. This is the most impactful single change — propagates to all ~20 call sites.

5. INDEPENDENT_CLASSIFICATIONS readonly array — :164-167
   7 values. Used directly in Supabase .in() filters at 8+ locations.
   Under revamp: needs companion T1_CLASSIFICATIONS and T2_CLASSIFICATIONS arrays, or split into two exported arrays with GP_LOCATION_CLASSIFICATIONS assembled from T1+T2+T3+T4.

6. CORPORATE_CLASSIFICATIONS readonly array — :170-173
   ['dso_regional','dso_national'] — the canonical source.
   Under revamp: rename or supplement with T3_CLASSIFICATIONS / T4_CLASSIFICATIONS.

7. GP_LOCATION_CLASSIFICATIONS = INDEPENDENT + CORPORATE — :180-183
   9 values total. Used in .in() filters for "all GP practice" queries.
   Under revamp: Unchanged structurally — T1+T2+T3+T4 still = all GP locations. Just the grouping within that set changes.

### B. COPIES / SHADOWS OF CORPORATE_CLASSIFICATIONS

Five distinct locations define or shadow the corporate set, outside the canonical file:

1. src/lib/launchpad/ranking.ts:116
   const CORPORATE_CLASSIFICATIONS = new Set(["dso_regional", "dso_national"])
   LOCAL shadow — not imported. Also references "dso_national" at :287, :294 for dsoTier logic.
   RISK: Will silently diverge when T3/T4 labels change.

2. src/lib/supabase/queries/practices.ts:88
   .in("entity_classification", ["dso_regional", "dso_national"]) — inline literal in getPracticeCountsByStatus(). Should import CORPORATE_CLASSIFICATIONS.

3. src/app/market-intel/page.tsx:30
   .filter((p) => p.entity_classification === 'dso_regional' || p.entity_classification === 'dso_national') — inline filter. Also at :34-35.

4. src/lib/supabase/queries/warroom.ts:657, :941, :945 — three inline .in()/.eq() filters using literals.

5. src/lib/constants/sql-presets.ts:17 — SQL string: IN ('dso_regional','dso_national')

Additional inline literal sites (individual string comparisons, not full shadows):
   src/app/job-market/page.tsx:69-72 — four filter comparisons
   src/app/job-market/_components/job-market-shell.tsx:301, 305, 366, 370 — EC-switch blocks
   src/app/job-market/_components/practice-directory.tsx:315 — "is hiring" filter logic
   src/app/warroom/_components/hunt-mode-panel.tsx:59-60 — filter chip array
   src/lib/warroom/intent.ts:40-41 — intent keyword→EC mapping
   src/lib/warroom/ranking.ts:222-223 — corporate detection for ranking penalty
   Total non-canonical literal sites: ~15+

### C. CONSOLIDATION-HONESTY.TS INVENTORY — src/lib/constants/consolidation-honesty.ts

Hardcoded constants:
  - ADA_HPI_DSO_AFFILIATION: { IL: 14.6, MA: 14.9 }  (per-dentist %, ADA 2024)
  - CONFIRMED_PER_DENTIST_CORPORATE: { IL: 10.47 (=816/7792), MA: 4.17 (=73/1752) }
  - US_DENTAL_PRACTICE_ESTIMATE: 137_000
  - US_NPPES_DENTAL_NPI_ROWS: 381_598

Functions:
  - getCorporateBand(confirmedPct, state, perDentistOverride?) → CorporateBand. Three-anchor output: floor (per-location %) / perDentist (%) / adaAnchor (%). "floor" = confirmedPct (runtime from zip_scores); perDentist = CONFIRMED_PER_DENTIST_CORPORATE[state].
  - getCorporateBandPoints(band) → { floor, perDentist, adaAnchor } numbers
  - corporateBandTooltip(band) → tooltip string explaining the three-anchor honest band
  - corporateBandSubtitle(band) → "X.X% per-dentist · ADA ~14.6%" subtitle string

Call sites (all pass 'mixed' or a state string and the runtime consolidatedPct):
  - home-shell.tsx:377-383 (Home "Confirmed Corporate" KPI)
  - warroom sitrep-kpi-strip.tsx:59, :87-90 (Warroom Sitrep "Confirmed Corporate" KPI)
  - job-market-shell.tsx:591-598 (Job Market "Corporate Penetration" KPI)
  - market-intel-shell.tsx:262-265, :281-283 (Market Intel Consolidation tab KPI + CorporateBandBar)
  - warroom briefing.ts:1, :52 (Warroom briefing text generation)
  Total: 5 call-site files, 7 call instances.

CorporateBandBar component: src/components/data-display/corporate-band-bar.tsx:28-42. Only used at market-intel-shell.tsx:281-283.

Under revamp:
  - The three-anchor model (floor→per-dentist→ADA) is T3+T4 only today.
  - T2 (dentist-owned groups) needs its own segment or the band must be relabeled to "DSO/PE penetration" rather than "consolidated".
  - CONFIRMED_PER_DENTIST_CORPORATE would need a T2-per-dentist companion.
  - ADA_HPI_DSO_AFFILIATION stays as the T3+T4 external anchor.
  - corporateBandTooltip/corporateBandSubtitle prose strings will need rewording to distinguish T2 from T3+T4.

### D. DESIGN-TOKENS.TS OWNERSHIP COLOR SYSTEM — src/lib/constants/design-tokens.ts

Current binary color map (colors.status):
  independent: '#2563EB'
  dso_affiliated: '#D4920B'  (amber, SEMANTIC.amber)
  pe_backed: '#C23B3B'       (red, SEMANTIC.red)
  unknown: TEXT.muted (#9C9C90)

Functions:
  - ownershipLabel(status) → "Independent"|"DSO-Affiliated"|"PE-Backed"|"Unknown" — operates on ownership_status strings, NOT entity_classification.
  - ownershipColor(status) → hex color from above map — same: ownership_status-based.

Under revamp:
  - A T1/T2/T3/T4 color system does not yet exist.
  - Recommended: T1 '#2563EB' (blue, existing independent), T2 '#6366F1' (indigo, group), T3 '#D4920B' (amber, stealth), T4 '#C23B3B' (red, known DSO/PE). PE-flag overlay = a badge/indicator, not a primary color.
  - getEntityClassificationLabel() already provides granular labels — ownershipLabel/ownershipColor can be retired once entity_classification is primary everywhere. These two functions currently serve deal-flow/practice tables that still use ownership_status.

### E. SCORING.TS OWNERSHIP FACTOR — src/lib/utils/scoring.ts

computeJobOpportunityScore(practice):
  - Independent: +30 pts (via isIndependentClassification, which includes both T1 solos and T2 groups)
  - corporate: +0 (implicit)
  - unknown: +10
  Point gap: independent vs corporate = 30 pts.

isRetirementRisk(practice):
  - isIndependentClassification(ec) must be true (T1+T2 both qualify today)
  - year_established < 1995 (30+ years old)

Under revamp:
  - T2 multi-location groups may warrant a different score than T1 solos.
  - T3 stealth DSOs are currently mislabeled independent — when correctly labeled they'd score 0 pts, removing them from job-target/acquisition-target lists automatically.
  - isRetirementRisk: T2 family_practice groups ARE legitimate retirement risk candidates; small_group/large_group dentist chains less so. May need tier-specific filter.

### F. EVERY CORPORATE-% SURFACE (CONSOLIDATED LIST)

1. Home "Confirmed Corporate" KPI — home-shell.tsx:374-383. Source: getPracticeStats().consolidatedPct → practice_locations ec + zip_scores.total_gp_locations. Band: getCorporateBand(parseFloat(consolidatedPct), 'mixed')
2. Warroom Sitrep "Confirmed Corporate" KPI — sitrep-kpi-strip.tsx:58, :80-92. Source: ownership.corporate / gpLocations. Band: getCorporateBand(corporateFloorPct, "mixed")
3. Job Market "Corporate Penetration" KPI — job-market-shell.tsx:591-598. Source: kpiDisplay.allSignals_pct (locDsoRegionalCount + locDsoNationalCount / total; page.tsx:69-72). Band: getCorporateBand(...)
4. Market Intel Consolidation tab "Corporate Share" KPI + CorporateBandBar — market-intel-shell.tsx:144-145, :262-265, :281-283. Source: kpis.allSignalsPct (corporateCount / totalGpLocations; corporateCount = sum zip_scores.corporate_share_pct * total_gp_locations). Only usage of CorporateBandBar.
5. Market Intel "DSO Penetration" table — dso-penetration-table.tsx:28-34, :59-72. Source: zip_scores.corporate_share_pct (*100).
6. Market Intel "ZIP Analysis" — zip-score-table.tsx:38-52, :171. Source: zip_scores.corporate_share_pct * 100 ("Consolidation %").
7. Market Intel Consolidation map — consolidation-map.tsx:69-77. Source: corporate_share_pct * total_gp_locations → choropleth.
8. Market Intel "City Practice Tree" — city-practice-tree.tsx:112-114. Source: corporate_share_pct * total_gp_locations (per-city rollup).
9. Warroom Living Map lens "Corporate Share" — living-map.tsx:52-53. Source: zipScore.corporate_share_pct (*100).
10. Warroom ZIP Dossier — zip-dossier-drawer.tsx:506, :1157-1158. Source: corporate_share_pct * 100.
11. Launchpad ZIP Dossier — zip-dossier-drawer.tsx:175, :222. Source: corporate_share_pct.
12. Launchpad Practice Dossier — practice-dossier.tsx:1475. Source: target.zipScore.corporate_share_pct.
13. Launchpad AI ask/zip-mood API routes — api/launchpad/ask/route.ts:68-69, api/launchpad/zip-mood/route.ts:41-42. Source: z.corporate_share_pct * 100 (AI prompt context).
14. Warroom Briefing — warroom/briefing.ts:52. Source: pct → getCorporateBand().
15. Job Market Saturation Map — saturation-map.tsx:81, :381. Source: zs.corporate_share_pct * 100.
16. Job Market Saturation Table — saturation-table.tsx:102-103. Source: zs.corporate_share_pct * 100.
17. Job Market Ownership Landscape chart — ownership-landscape.tsx:107-113, :193. Source: corporate_share_pct * 100.
18. Job Market Market Analytics chart — market-analytics.tsx:64, :71. Source: consolidatedCount / total (classifyPractice(ec) === 'corporate').
19. Launchpad Ranking — zipCorpShare — launchpad/ranking.ts:279. Source: zipScore.corporate_share_pct (score factor).
20. getPracticeCountsByStatus() inline filter — queries/practices.ts:88. Inline ["dso_regional","dso_national"] — feeds Market Intel Ownership tab count.

### G. SUMMARY: WHAT THE REVAMP MUST TOUCH

HIGH IMPACT (structural change required):
  1. entity-classifications.ts — add T1/T2/T3/T4 grouping constants; split classifyPractice() into 6-way (or add getTier()); split INDEPENDENT_CLASSIFICATIONS into T1+T2 arrays.
  2. consolidation-honesty.ts — decompose getCorporateBand() or add getConsolidationBand() that includes T2 in its lower anchor. CONFIRMED_PER_DENTIST_CORPORATE needs a T2 companion once T2 data exists.
  3. practices.ts:getPracticeStats() — consolidatedPct today = (dso_regional+dso_national)/total. Under revamp needs "consolidatedPct" = (T2+T3+T4)/total AND "dsoPenetrationPct" = (T3+T4)/total.
  4. buyability-shell.tsx:categorize() — isCorporateClassification() maps only to T3+T4 dead-ends. T2 groups need their own category or explicit pass-through to job_target.
  5. design-tokens.ts — add 4-tier color map; deprecate binary ownership_status colors.

MEDIUM IMPACT (update to use canonical constants):
  6. launchpad/ranking.ts:116 — local CORPORATE_CLASSIFICATIONS Set → import from entity-classifications.ts.
  7. queries/practices.ts:88 — inline literal → import CORPORATE_CLASSIFICATIONS.
  8. market-intel/page.tsx:30-35 — inline literals → import helpers.
  9. queries/warroom.ts:657, :941, :945 — inline literals → import helpers.
  10. sql-presets.ts:17 — inline SQL string → update when T3/T4 labels settle.
  11. manual-entry-forms.tsx:355 — hardcoded dropdown → drive from ENTITY_CLASSIFICATIONS array.

LOW IMPACT (display copy only):
  12. corporateBandTooltip / corporateBandSubtitle strings — rewording after T2/T3/T4 split.
  13. data-breakdown bundle prose — update provenance descriptions.
  14. warroom briefing.ts prose strings — update once tier labels are settled.

UNCHANGED:
  - /deal-flow (G1 only; pe_sponsor is already the PE-flag signal)
  - /research (no ownership computation)
  - /intelligence (AI readiness score, not entity_classification)
  - /system freshness/scraper health panels
  - Activity feed field detection (ownership_status strings from practice_changes)
  - All ~19 surfaces that read zip_scores.corporate_share_pct (that scalar comes from the pipeline's merge_and_score.py — the frontend reads it as-is; updating the pipeline to emit t2_share_pct/t3t4_share_pct would unlock multi-tier maps with NO frontend logic changes)
