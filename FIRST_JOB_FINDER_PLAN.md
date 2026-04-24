# FIRST JOB FINDER — Build Plan

**Document type:** Internal architecture plan — review before opening execution session  
**Author:** Architect Synthesizer (multi-agent research synthesis)  
**Date:** April 24, 2026  
**Status:** Ready for owner review

---

## 1. Executive Summary

**Build name selected: Launchpad** (over "First Job Finder" and "AssociateScout" — shorter, directionally positive, no implication of desperation).

This plan defines the Launchpad page (`/launchpad`) for the Dental PE Intelligence Platform: a career-track matcher for new dental school graduates facing their first associate job search. The persona is a May 2026 graduate with $300k+ in student debt, zero established patients, and full choice paralysis about whether to chase mentorship/succession, high-volume clinical reps, or a structured DSO path. Launchpad converts the existing 401k+ practice database, qualitative intel layer, and ZIP scoring engine into a track-weighted 0–100 fit score for every practice in Chicagoland's 269 watched ZIPs. Success looks like this: a BU or Midwestern dental grad opens `/launchpad`, selects their living location, picks "Succession Track," and sees a ranked list of 15–30 solo practitioners who fit the mentor-rich + buyability profile — filtered to commutable ZIPs — with a one-click dossier drawer showing compensation benchmarks, red flags, and 10 tailored interview questions. The build reuses the Warroom architecture throughout (server-component page, client shell, React Query, URL-synced state) and extends the existing AI research engine rather than rebuilding it.

---

## 2. Research Findings

### The New-Grad Pain Is Structural, Not Cyclical

The ADA Health Policy Institute data paints a consistent picture: non-owner GP dentist inflation-adjusted income has declined from a 2010 peak to approximately $210k in 2024 — a real-terms drop of roughly $57k over 14 years ([ADA HPI 2024 Dentist Income Report](https://www.ada.org/resources/research/health-policy-institute/dentist-income)). At the same time, average dental school debt has crossed $320k for private school graduates. The debt-to-first-year-income ratio has inverted badly.

The corporate capture layer compounds this. DSO affiliation among dentists rose from 8.8% in 2017 to 16.1% by 2024 ([ADA HPI DSO Affiliation Report](https://www.ada.org/resources/research/health-policy-institute/dentist-participation-in-dso)). Industry analysts (ADA's own conservative methodology) estimate the real share is closer to 25–35% when location-level corporate signals are counted rather than just dentist self-report. In Chicagoland specifically, this database has classified 9.9% of practices as showing detected corporate signals, with 1.9% as high-confidence DSO/national corporate. The classified portion is already above the ADA self-report national average.

### Salary Reality: Three Very Different Outcomes

Headline ADA HPI benchmark for 2024: non-owner GP average $160,891, new-grad average $166,676 ([ADA HPI Dentist Income Report](https://www.ada.org/resources/research/health-policy-institute/dentist-income)). The first number surprises most grads — why is new-grad pay above the non-owner average? Because corporate DSOs recruit heavily at graduation with structured packages.

DSO-specific compensation tells a different story: SalaryDr (real-offer database) shows new-grad DSO offers averaging $275,360 total compensation ([SalaryDr dental salary data](https://www.salarydr.com/dentist-salary)), but this includes production bonuses that most new grads do not hit in year one given the learning curve on case acceptance and speed. Base salary at Heartland-tier DSOs is typically $120–140k + production percentage; net take-home year one is commonly $140–170k.

The succession track has the highest 5-year ceiling if the deal closes: an associate-to-partner trajectory in a high-income independent practice (FFS or FFS/PPO mix, north-shore suburbs, $1.2M+ collections) can produce $350–500k within 4–7 years. The median buyout price for a solo GP practice in Chicagoland is 60–80% of annual collections (Range: $500k–$1.2M). With seller financing, annual debt service is often lower than a fresh DSO associate's student loan payment.

### Three-Track Framing: Validated

Domain research confirms that dental career coaches and dental school residency directors consistently describe these three paths as distinct, with very different lifestyle and financial outcomes:

1. **Succession/Mentorship Track** ("apprentice to owner"): Solo practitioner 55+, established 20–30 years, needs clinical help now, plans to exit in 3–7 years. Ideal for the grad who wants ownership but can't afford startup costs. Key risk: owner not actually ready to sell, or family member in dental school.

2. **High-Volume Ethical Practice Track**: Busy private or group practice, consistent FFS/PPO mix (not Medicaid-dominant), income-stable patient base, 3–5 providers. Maximizes clinical reps in years 1–3. Best option for grads who want high income + fast skill acquisition without ownership pressure.

3. **DSO Associate Track**: Structured onboarding, benefits (health/401k/malpractice), CE support, administrative lift. Appropriate for grads who explicitly prefer not to manage business risk early. The key distinction: reputable DSOs (Mortenson employee-owned, MB2 Dental Partners, Benevis, Community Dental Partners, Dental Associates of Wisconsin) vs notorious churn shops where average associate tenure is under 18 months and production pressure is relentless.

### Job Board Landscape

Signal-to-noise ranking from domain research:

- **Highest signal**: [DentalPost](https://www.dentalpost.net) (dentistry-specific, verified practices, succession-track listings), [ADA Career Center](https://careercenter.ada.org) (peer-reviewed listings), [iHireDental](https://www.ihiredental.com)
- **Medium signal**: [Dental Economics job board](https://www.dentaleconomics.com/careers), state dental association boards (ISDS, MDS)
- **Low signal / DSO-skewed**: Indeed, LinkedIn (heavily dominated by DSO recruiter posts that are functionally evergreen; do not represent actual openings at specific practices)

ToS note: DentalPost prohibits automated scraping. This matters for Section 8.

### DSO Tier List (Synthesized from Domain Research)

**Tier 1 — Strong for new grads (mentorship culture, low churn, fair comp):**
- Mortenson Dental Partners — employee-owned ([Mortenson About page](https://www.mortensondental.com/about)); genuine ownership culture, lower-volume environments
- MB2 Dental Partners — DPO structure (dentist-owned partnership); grads retain equity upside ([MB2 Dental Partnership model](https://mb2dental.com/partnership))
- Dental Associates of Wisconsin — regional, family-operated, strong training program

**Tier 2 — Decent with caveats (structured but watch comp terms):**
- Pacific Dental Services (PDS) — CE-heavy, large infrastructure; watch non-compete radius
- Dental Care Alliance (DCA) — Florida-heavy but expanding Midwest; decent base packages
- Benevis — safety-net model (Medicaid-heavy), but genuine mentorship; strong for clinical reps if you can handle the volume
- Community Dental Partners — FQHC/community model; mission-driven, lower comp ceiling

**Tier 3 — Mixed / proceed with caution:**
- Heartland Dental — largest DSO; production pressure is real; tenure data shows 12–24mo average for first-time associates; comp packages have improved post-2023 ([Heartland careers](https://jobs.heartland.com/earn/)); non-compete aggressively enforced
- National Dental Group (NADG) — similar to Heartland trajectory
- Aspen Dental Management (ADMI) — separate AVOID category below; distinguish the management company from clinical entities
- Great Expressions Dental Centers — mixed regional variation; Michigan/SE markets better than Florida
- American Dental Partners (ADI) — rebranding multiple times; instability signal

**AVOID tier — documented consumer harm, regulatory action, or churn data:**
- Aspen Dental / Aspen Dental Management (ADMI) — NY AG settlement 2015 ([NY AG Aspen Dental settlement](https://ag.ny.gov/press-release/2015/attorney-general-schneiderman-announces-settlement-aspen-dental)); PBS Frontline documented consumer harm ([PBS Frontline "Dollars and Dentists" 2012](https://www.pbs.org/wgbh/frontline/film/dollars-and-dentists/)); aggressive upsell incentives remain post-settlement
- Sage Dental — Florida-based; multiple patient complaint clusters; aggressive production metrics
- Western Dental — California; repeated regulatory actions; Medicaid-heavy with high-volume pressure
- Smile Brands / Bright Now Dental — private equity recapitalization 2022–2024; comp/contract instability
- Risas Dental — Arizona-heavy; price-aggressive Medicaid model; not suitable for mentorship

### Succession Track Red Flags (Domain Research)

1. No written buy-sell agreement drafted within 6 months of hire
2. Owner's family member is currently in dental school or a recent graduate
3. Multiple associates have cycled through the practice in the past 5 years (look for practice_changes churn)
4. Practice is listed on more than one dental brokerage platform simultaneously (signal: testing the market without commitment)
5. Owner refuses to disclose 3 years of P&L statements before year 2 of the associate relationship

### Contract Red Flags

Note: The FTC non-compete ban (effective September 2025, [FTC Final Rule](https://www.ftc.gov/news-events/news/press-releases/2024/04/ftc-issues-final-rule-banning-noncompetes)) has narrow exclusions — senior executives only. Non-competes for associate dentists remain enforceable in most states, including Illinois. Review by a dental contract attorney is non-negotiable before signing. Common traps:

- **Lab fee deduction**: contract language stating "lab fees deducted before production split" — this can reduce effective collection rate by 8–15%
- **Recoverable-draw deficit**: if base salary is structured as a "draw against production" rather than a guaranteed base, a slow first year creates a growing debt to the practice owner
- **Excessive non-compete radius**: Illinois courts have upheld 10–25 mile radii for up to 2 years; DSOs routinely request 25 miles/3 years — negotiate down before signing

---

## 3. Reusing the ZIP Research API

### Existing Research Infrastructure (Verified Line Counts)

The qualitative intelligence layer is already scaffolded and production-tested. No new infrastructure is needed for v1 — only new prompts and two new method wrappers.

| File | Lines | Role |
|------|-------|------|
| `scrapers/research_engine.py` | 409 | Core Anthropic API client — raw HTTP requests, prompt caching, circuit breaker (3 failures → abort), Haiku-4-5 default / Sonnet-4-20250514 escalation |
| `scrapers/qualitative_scout.py` | 391 | ZIP-level CLI; `--zip 60491` or `--metro chicagoland`; ~$0.04–0.06/ZIP |
| `scrapers/practice_deep_dive.py` | 587 | Practice-level CLI; two-pass Haiku→Sonnet escalation; ~$0.08–0.12 standard, ~$0.28 deep |
| `scrapers/intel_database.py` | 289 | SQLAlchemy CRUD for both intel tables; 90-day cache TTL |
| `scrapers/weekly_research.py` | 309 | Automated runner; $5/week budget cap; batch API (50% discount) |

Current coverage: `zip_qualitative_intel` has 290 rows (one per watched ZIP); `practice_intel` is sparse at approximately 23 rows. The `practice_intel` schema already contains the fields most relevant to job hunting: `hiring_active`, `owner_career_stage`, `accepts_medicaid`, `ppo_heavy`, `technology_level`, `google_rating`, `google_velocity`, `red_flags`, `green_flags`, `acquisition_readiness`, `confidence` — all present as typed columns in `src/lib/types/intel.ts:70–130`.

### Extension Strategy: Don't Rebuild, Extend

The correct approach is to add a parallel prompt mode to the existing `research_engine.py` rather than creating a new script. Two new constants and one new method:

```python
# research_engine.py — add after existing JOB_HUNT_SYSTEM placeholder (line ~30)
JOB_HUNT_SYSTEM = """
You are a dental career intelligence analyst helping a new dental school graduate evaluate
associate job opportunities in the Chicagoland market. Your task: analyze publicly available
signals about a dental practice to assess its fit for a first-year associate. Extract only
what you can verify from public sources (website, Google reviews, LinkedIn, HealthGrades,
job boards). Return null for fields you cannot verify — NEVER fabricate data.
"""

JOB_HUNT_PRACTICE_USER = """
Analyze this dental practice for new-grad associate fit. Practice: {practice_name},
{address}, {city}, {state}. Website: {website}. NPI: {npi}.

Return a JSON object with these fields:
- associate_openings: true/false/null — is the practice actively recruiting an associate?
- mentorship_signals: list of observed signals suggesting owner mentorship culture
- succession_intent: "active_seeking" | "possible" | "unlikely" | null
- compensation_signals: any visible comp data (production%, hourly, salary range, benefits)
- culture_signals: list of signals about practice culture (reviews, social, website tone)
- interview_red_flags: list of contract or cultural red flags to probe in interview
- new_grad_friendly_score: integer 1-10 based on overall signals
"""
```

The new `research_practice_jobhunt(npi, practice_name, address, city, state, website)` method in `research_engine.py` should follow the same pattern as the existing `research_practice()` method (lines ~200–280): call Haiku first, check escalation criteria (new_grad_friendly_score >= 7 OR succession_intent == "active_seeking"), escalate to Sonnet if triggered.

For v1, store results in the existing `practice_intel.raw_json` column (no ALTER TABLE required). The new fields can be extracted at query time in TypeScript from the `raw_json` blob. For v2 (Phase 2), add the queryable columns as an ALTER TABLE migration: `hiring_active`, `succession_intent_detected`, `new_grad_friendly_score` (already partially present in the schema — verify against the SQLite schema before running migrations).

---

## 4. Proposed Architecture

### Route Decision

Three candidates evaluated: `/launchpad`, `/first-job`, `/associate-finder`. **Recommendation: `/launchpad`**. Rationale: shortest, non-stigmatizing (no implication of desperation), evocative of the career launch metaphor, consistent with the existing route naming style (`/warroom`, `/research`, `/intelligence`).

### Component Map

Mirror Warroom's proven pattern throughout. The Warroom page at `dental-pe-nextjs/src/app/warroom/page.tsx` (35 lines) is the template for the server component — it fetches the bundle, wraps it in a try/catch, passes `initialBundle` and `initialBundleError` as props to the client shell. Zero client-side loading flash on initial navigation.

**New files to create:**

```
src/app/launchpad/
  page.tsx                           — server component, ~35 lines, fetches LaunchpadBundle
  _components/
    launchpad-shell.tsx              — root 'use client' shell, mirrors warroom-shell.tsx (741 lines)
    scope-selector.tsx               — reuses LIVING_LOCATIONS from living-locations.ts
    track-switcher.tsx               — 3-button: Succession | High-Volume | DSO
    launchpad-kpi-strip.tsx          — 4 KPI cards: Mentor-Rich | Now Hiring | Avoid Count | Median Comp
    launchpad-map.tsx                — Mapbox; 5 lenses (see Section 7)
    track-list.tsx                   — ranked practice list; 3-color tier badges per track
    practice-dossier.tsx             — Sheet drawer, 5 tabs (see Section 7)
    dso-tier-card.tsx                — DSO track: shows tier badge + key facts

src/lib/launchpad/
  signals.ts                         — TypeScript types for all 20 signals
  scope.ts                           — scope definitions, reuses LIVING_LOCATIONS
  ranking.ts                         — track-weighted scoreForTrack(); analog to warroom/ranking.ts
  dso-tiers.ts                       — hand-curated static constant: Tier1/Tier2/Tier3/Avoid

src/lib/hooks/
  use-launchpad-state.ts             — dual-write URL+localStorage state machine
  use-launchpad-data.ts              — React Query wrapper, 5min staleTime

src/lib/supabase/queries/
  launchpad.ts                       — Supabase queries; reuses practices, practice_intel, zip_scores
```

### Data Flow

`page.tsx` (server) fetches `LaunchpadBundle` from Supabase: the top 300–500 practices in watched ZIPs ranked by initial score, plus ZIP-level signals from `zip_scores`, plus any available `practice_intel` rows. Bundle is passed to `LaunchpadShell` as `initialBundle`. Client shell mounts with data immediately visible. React Query hydrates from `initialBundle` and refetches on filter change (track switch, scope change, map lens change) with 5min staleTime. URL params sync track + scope + selected NPI for shareability — same `useUrlFilters` hook pattern used across all existing pages.

The `LaunchpadBundle` type mirrors `WarroomSitrepBundle` in `src/lib/warroom/signals.ts` but substitutes warroom-specific fields with job-hunt fields: `mentorRichCount`, `hiringNowCount`, `avoidCountInScope`, `medianCompEstimate`.

---

## 5. Signal Catalog

Twenty signals ranked by implementation priority. Data sources are all fields already present in the Supabase schema (practices table + practice_intel + zip_scores + practice_changes).

| # | Signal Name | Definition | Data Source | Base Weight |
|---|-------------|------------|-------------|-------------|
| 1 | `mentor_rich_signal` | solo entity_classification (any solo_* variant) AND year_established <= 2001 (25+ years) AND num_providers >= 1 AND employee_count >= 2 | practices | +25 |
| 2 | `succession_track_signal` | mentor_rich_signal fires AND buyability_score >= 50 AND num_providers = 1 (no current associate) | practices | +30 |
| 3 | `hiring_now_signal` | practice_intel.hiring_active = 1 OR practice_intel.associate_openings = true (from raw_json job-hunt mode) | practice_intel | +20 |
| 4 | `high_volume_ethical_signal` | employee_count >= 5 AND (estimated_revenue >= 800000 OR num_providers >= 3) AND entity_classification NOT IN (dso_national, dso_regional) AND ZIP median HH income >= $75k | practices + zip_scores | +20 |
| 5 | `boutique_solo_signal` | entity_classification = solo_high_volume AND estimated_revenue >= 1000000 AND practice_intel.technology_level = 'high' | practices + practice_intel | +25 |
| 6 | `ffs_concierge_signal` | practice_intel.ppo_heavy = 0 AND practice_intel.accepts_medicaid = 0 AND website language indicates concierge/fee-for-service (AI-extracted) | practice_intel | +15 |
| 7 | `tech_modern_signal` | practice_intel.technology_level = 'high' (CBCT, iTero, intraoral scanner detected on website or Google listing) | practice_intel | +10 |
| 8 | `community_dso_signal` | entity_classification = dso_national AND affiliated_dso IN Tier1/Tier2 DSO list (dso-tiers.ts constant) | practices | +18 |
| 9 | `mentor_density_zip_signal` | ZIP has >= 5 mentor_rich practices in the zip_scores.total_gp_locations pool AND corporate_share_pct < 0.25 | zip_scores | +12 |
| 10 | `commutable_signal` | ZIP code is in user's selected LIVING_LOCATION.commutable_zips list | living-locations.ts | +20 (filter) |
| 11 | `growing_undersupplied_signal` | zip_scores.market_type = 'growing_undersupplied' AND zip_scores.metrics_confidence IN ('high','medium') | zip_scores | +10 |
| 12 | `succession_published_signal` | practice_intel raw_json succession_intent = 'active_seeking' OR practice name found on dental brokerage site (AI-research-able) | practice_intel | +35 |
| 13 | `dso_avoid_warning` | entity_classification = dso_national AND affiliated_dso IN AVOID tier list (Aspen, Sage, Western, Smile Brands, Risas) | practices | -40 |
| 14 | `family_dynasty_warning` | entity_classification = family_practice (shared last name at address → internal succession; new grad = placeholder) | practices | -15 |
| 15 | `ghost_practice_warning` | entity_classification = solo_inactive (no phone AND no website) | practices | -30 |
| 16 | `recent_acquisition_warning` | practice_changes shows ownership_status flip to dso_affiliated within past 18 months (instability, comp/contract churn likely) | practice_changes | -20 |
| 17 | `associate_saturated_signal` | entity_classification = large_group AND num_providers >= 5 (less mentorship time per associate at this scale) | practices | -10 |
| 18 | `medicaid_mill_warning` | practice_intel.accepts_medicaid = 1 AND ZIP median HH income < $45k AND google_velocity = 'high' (high-throughput Medicaid volume) | practice_intel + zip_scores | -15 |
| 19 | `non_compete_radius_warning` | entity_classification = dso_national AND affiliated_dso IN Tier3/Avoid (documented enforcement history) | practices | -25 |
| 20 | `pe_recap_volatility_warning` | affiliated_pe_sponsor IS NOT NULL AND deal was within past 12 months in deals table | practices + deals | -15 |

**Example application:** "Dr. Kowalski DDS, established 1994 (32 years), entity_classification = solo_established, employee_count = 3, buyability_score = 67, num_providers = 1" → fires `mentor_rich_signal` (+25) + `succession_track_signal` (+30). Base score: 50 + 55 = 105, capped at 100. On Succession Track with 1.5x/2.0x multipliers applied before cap: final score 100, tier = BEST FIT.

**Example application:** "Aspen Dental, Oak Brook IL, entity_classification = dso_national, affiliated_dso = Aspen Dental" → fires `dso_avoid_warning` (-40). Base score: 50 - 40 = 10. On any track: final score 10, tier = AVOID.

---

## 6. Scoring Model

This section defines the canonical scoring function. The user flagged this as critical — it is specified completely enough to implement directly.

### Base Score and Signal Accumulation

Every practice starts at **base score = 50**.

Each active signal contributes its base weight (positive or negative). After all signals are summed, a **track-specific multiplier** is applied to each signal contribution before summing. The cap is applied last.

```
function scoreForTrack(practice, signals, track):
  base = 50
  total_contribution = 0

  for signal in ACTIVE_SIGNALS(practice):
    raw_weight = signal.base_weight
    multiplier = TRACK_MULTIPLIERS[track][signal.name] ?? 1.0
    contribution = raw_weight * multiplier
    total_contribution += contribution

  raw_score = base + total_contribution
  final_score = clamp(raw_score, 0, 100)

  # Confidence cap: thin data means don't over-trust the score
  if practice.classification_confidence < 40 OR practice_intel IS NULL:
    final_score = min(final_score, 70)

  return final_score
```

### Track-Specific Multipliers

These multipliers modulate signal strength by track, analogous to `LENS_WEIGHT_MULTIPLIERS` in `src/lib/warroom/ranking.ts:54–96`.

| Signal | Succession Track | High-Volume Track | DSO Track |
|--------|-----------------|-------------------|-----------|
| `mentor_rich_signal` | 1.5x | 1.0x | 0.5x |
| `succession_track_signal` | 2.0x | 0.5x | 0.0x |
| `succession_published_signal` | 2.5x | 0.3x | 0.0x |
| `high_volume_ethical_signal` | 0.5x | 1.5x | 0.5x |
| `boutique_solo_signal` | 1.0x | 1.5x | 0.3x |
| `hiring_now_signal` | 1.0x | 1.5x | 1.0x |
| `ffs_concierge_signal` | 0.8x | 1.2x | 0.0x |
| `community_dso_signal` | 0.0x | 0.5x | 2.0x |
| `tech_modern_signal` | 0.7x | 1.0x | 0.8x |
| `mentor_density_zip_signal` | 1.3x | 0.8x | 0.5x |
| `dso_avoid_warning` | 1.0x | 1.0x | 1.5x |
| `family_dynasty_warning` | 1.5x | 1.0x | 0.0x |
| `ghost_practice_warning` | 1.0x | 1.0x | 1.0x |
| `recent_acquisition_warning` | 1.2x | 1.0x | 0.8x |
| `associate_saturated_signal` | 1.5x | 0.5x | 0.3x |
| `medicaid_mill_warning` | 1.0x | 1.2x | 0.5x |
| `non_compete_radius_warning` | 0.8x | 0.8x | 1.5x |
| `pe_recap_volatility_warning` | 0.8x | 0.8x | 1.3x |

### Tier Thresholds

| Score | Tier | Label | Action |
|-------|------|-------|--------|
| 80–100 | BEST FIT | Green badge | Pursue immediately; dossier → Interview Prep tab |
| 65–79 | STRONG FIT | Yellow-green badge | Apply; ask hard questions at screening call |
| 50–64 | MAYBE | Amber badge | Only if better options exhausted |
| 35–49 | LOW FIT | Orange-red badge | Likely disappoints; missing key signals |
| 0–34 | AVOID | Dark red/grey badge | Known red flags; skip unless researching the space |

### Confidence Modifier

If `practice.classification_confidence < 40` (DSO classifier was uncertain) OR `practice_intel` row is NULL (no AI research yet), cap the final score at 70 regardless of signal total. Show a visual indicator in the dossier: "Data thin — verify in interview." This prevents the model from confidently mislabeling a practice whose ownership is ambiguous in the database.

### Track-Blend Override

If the user selects "All Tracks" (explore mode before committing to a strategy): compute all three track scores independently, then surface `max(succession_score, high_volume_score, dso_score)` as the headline score, with the winning track name shown as a small badge ("Best as: Succession"). This handles the majority of new grads who don't yet know which track they want — they see the best possible fit for each practice regardless of track, and can narrow later.

### Score Interpretation Example

Dr. Ahmed DDS practice: 28-year-old solo (established 1998), employee_count=4, buyability_score=72, num_providers=1, classification_confidence=85, practice_intel present (hiring_active=1, accepts_medicaid=0, technology_level='high').

- mentor_rich_signal: +25 × 1.5x (Succession) = +37.5
- succession_track_signal: +30 × 2.0x = +60.0
- hiring_now_signal: +20 × 1.0x = +20.0
- tech_modern_signal: +10 × 0.7x = +7.0
- Raw: 50 + 37.5 + 60 + 20 + 7 = 174.5 → capped at 100 → BEST FIT

On High-Volume Track: 50 + 25 + 15 + 30 + 10 = 130 → capped at 100 (still BEST FIT, but fewer multiplied signals). On DSO Track: 50 + 12.5 + 0 + 20 + 8 = 90.5 → BEST FIT only because hiring_now fires. Track-blend shows "Best as: Succession."

---

## 7. UI Mockup — Text Wireframe

### Top Bar (persistent, above all content)

```
[ ScopeSelector ▾ "West Loop / South Loop" ]  [ Succession | High-Volume | DSO ]  [ Map | List ]  [ ? Help ]
```

ScopeSelector uses `LIVING_LOCATIONS` keys from `src/lib/constants/living-locations.ts` plus a future "Custom Address" option (Haversine radius for v1; Mapbox Isochrone API for v2).

### KPI Strip (4 cards, matches warm-light design system)

```
┌─────────────────┐ ┌────────────────┐ ┌────────────────────┐ ┌──────────────────┐
│  Mentor-Rich    │ │  Now Hiring    │ │  Avoid-List in     │ │  Median Comp     │
│  Practices      │ │  (Detected)    │ │  Your Area         │ │  Estimate        │
│  [JB Mono 28px] │ │ [JB Mono 28px] │ │  [JB Mono 28px]    │ │  [JB Mono 28px]  │
│  34             │ │  12            │ │  7 shops           │ │  $155k – $175k   │
│  in scope       │ │  practices     │ │  ⚠ tap to see      │ │  ADA HPI range   │
└─────────────────┘ └────────────────┘ └────────────────────┘ └──────────────────┘
```

### Main Split: 60% Map (left) | 40% Ranked List (right)

**Map: 5 Lenses** (toggle with icon pill bar above map, mirrors Warroom's lens switcher)

1. **Mentor Density** — heatmap weighted by count of mentor_rich_signal practices per ZIP; green gradient
2. **Hire Heat** — heatmap weighted by `practice_intel.hiring_active` density per ZIP; warm orange gradient
3. **Livable Score** — heatmap by ZIP median income vs estimated rent (30% rule); data from zip_scores + census estimates
4. **Commute Radius** — Haversine overlay showing 20-mile ring from selected home location; gray isochrone ring
5. **DSO Avoid** — red dots over AVOID-tier DSO locations; green dots over Tier1 community DSOs; practice-level (not ZIP-level)

**Ranked List (right panel):** Sorted by track score descending. Each row:

```
[Score badge] Practice Name           [Track badge]
              Dr. Owner Name · 1994 · Oak Park, IL
              ● mentor_rich  ● hiring_now  ○ 3 employees
```

Color-coded tier badges: BEST FIT (green), STRONG FIT (yellow), MAYBE (amber), AVOID (dark red).

### Practice Dossier Drawer (5 tabs, Sheet component — mirrors `dossier-drawer.tsx` 1440-line pattern)

Tab 1 — **Snapshot**: Practice name, address, phone, website link, entity_classification badge, year established, employee count, ownership stage estimate, fit score with track-by-track breakdown (bar for each track showing raw score and top contributing signals).

Tab 2 — **Compensation Benchmarks**: ADA HPI median for Illinois ($160,891 non-owner average, 2024), state/ZIP percentile estimate, comparable DSO comp ranges (production % + base for Heartland/PDS/MB2 where applicable), interactive production% calculator (input: expected collection rate; output: effective annual take-home; toggle for lab fee deduction, recoverable-draw structure).

Tab 3 — **Mentorship Signals**: Owner career stage (derived from year_established + practice_intel.owner_career_stage), num_providers trend from practice_changes, AI-extracted mentorship signals from practice_intel.green_flags and succession_intent, google_rating + google_sentiment summary.

Tab 4 — **Red Flags**: All triggered warning signals listed with explanation, contract red flag checklist (non-compete enforceability for Illinois, lab fee clause check, draw-deficit structure, scope-of-practice creep), DSO tier rating if dso_national (Tier1/2/3/AVOID badge with one-sentence rationale and primary source citation).

Tab 5 — **Interview Prep**: Auto-generated 10 questions tailored to this practice's track + active signals. Examples: if succession_track fires → "What does your ideal transition timeline look like?" / "Have you had a buy-sell agreement drafted, or would that be a first step?" / "What happens if I want to buy out in 3 years vs 7 years — does the deal structure change?". If dso_avoid fires → "Can you walk me through the associate departure process?" / "Is the non-compete radius negotiable?". Questions are deterministic from signal combination, not AI-generated at runtime (precomputed lookup table in `dso-tiers.ts` for v1).

**Key differences from Warroom dossier-drawer.tsx:** No PE deal catchment tab, no EIN cluster analysis, no "find similar" PE-sponsor links. Replaced with compensation benchmarking (Tab 2) and interview prep (Tab 5) — direct value to the new grad with zero PE-acquisition relevance.

---

## 8. Data Gaps and Acquisition Plan

What we don't have now, and the exact path to get it:

| Gap | Current Status | Cost / Path |
|-----|---------------|-------------|
| Active hiring status per practice | `practice_intel.hiring_active` column exists (typed in intel.ts:89); ~23 rows populated | AI research via `practice_deep_dive.py` job-hunt mode at ~$0.10/practice; priority: top 300 by mentor_rich + succession_track signal |
| Insurance mix (PPO/FFS/Medicaid) | `accepts_medicaid` and `ppo_heavy` columns exist (intel.ts:109–110); sparse data | AI research at ~$0.10/practice; 300 priority practices ≈ $30 |
| Owner career stage | `owner_career_stage` column exists (intel.ts:80); sparse | AI research at $0.10/practice; inferred from year_established as fallback |
| Succession intent | Not a typed column; extractable from `raw_json` via new job-hunt prompt | $0 for existing intel rows; $0.10/practice for new runs |
| Compensation benchmarks per ZIP | ZIP-level comp data not in current schema | One-time AI research via `qualitative_scout.py` extension, ~$0.04/ZIP × 269 ZIPs ≈ $11 |
| DSO tier list (curated) | Not stored in database | Hand-curated by Suleman from this document → `src/lib/launchpad/dso-tiers.ts` static constant; refresh quarterly |
| Glassdoor / Indeed practice culture | No data; ToS prohibits scraping | AI-research from Google reviews + HealthGrades sentiment only; set expectation accordingly |
| Owner explicit succession intent | Unobservable except via AI research of broker listings | AI-research can detect DentalBrokers.com / ADS listings; $0.10/practice |
| Days/hours operated | Not in practices table | Website scrape via AI research; low priority for v1 |
| DSO-specific comp ranges (live) | SalaryDr and ADA HPI are static references | Hard-coded from SalaryDr aggregates in dso-tiers.ts; update quarterly |
| New grad Glassdoor reviews | No access | Out of scope; cite ADA HPI and SalaryDr only |

**Total v1 seeding cost estimate:** ~$15 for ZIP-level comp benchmarks (269 ZIPs via qualitative_scout) + ~$30 for top 300 practices at $0.10/practice = **~$45 total one-time cost**. With $5/week weekly_research.py cap, the database self-populates at ~50 practices/week from then on.

**Full Chicagoland practice-level coverage** (top 3,000 practices): ~$300–500 at standard rate. Recommend authorizing this as a single deliberate seeding run rather than waiting 60 weeks for the organic cap to fill it.

---

## 9. Phased Build Plan

### Phase 1 — MVP (1 week, 4 commit-sized chunks)

**Goal:** Ranked practice list by track, scoped by living location, with basic dossier drawer. No map, no AI-research extension, no compensation calculator.

**Chunk 1 — Route scaffolding** (1 session):
- Create `src/app/launchpad/page.tsx` (35 lines, server component pattern from warroom/page.tsx)
- Create `src/app/launchpad/_components/launchpad-shell.tsx` (client shell skeleton — scope selector, track switcher, empty list panel)
- Create `src/lib/launchpad/scope.ts` (imports LIVING_LOCATIONS, exports default scope)
- Create `src/lib/supabase/queries/launchpad.ts` (getLaunchpadPractices query, top 500 by ZIP scope)

**Chunk 2 — Signals and ranking** (1 session):
- Create `src/lib/launchpad/signals.ts` (TypeScript types for all 20 signals)
- Create `src/lib/launchpad/ranking.ts` (scoreForTrack(), TRACK_MULTIPLIERS, tier classification)
- Implement Phase 1 signals (8 highest-value, no practice_intel dependency): mentor_rich, succession_track, high_volume_ethical, community_dso, dso_avoid, family_dynasty, ghost_practice, commutable
- Create `src/lib/launchpad/dso-tiers.ts` (hand-curated Tier1/2/3/Avoid static constant)

**Chunk 3 — Track list and KPI strip** (1 session):
- Implement `track-list.tsx` (ranked list with tier badges, signal chips, sort by track score)
- Implement `launchpad-kpi-strip.tsx` (4 KPI cards computed from filtered practice set)
- Wire URL-param sync via `useUrlFilters` (track + scope + selected NPI)

**Chunk 4 — Practice dossier drawer (Snapshot + Red Flags only)** (1 session):
- Implement `practice-dossier.tsx` with Sheet component (2 tabs: Snapshot, Red Flags)
- Red Flags tab: render all triggered warning signals + static contract red flag checklist
- Run `npm run build` in `dental-pe-nextjs/` to verify TypeScript clean

### Phase 2 — Deeper Signals + AI Research (1–2 weeks, 6 commit-sized chunks)

**Goal:** Full signal catalog, AI research extension, all 5 dossier tabs, map system.

- Extend `scrapers/research_engine.py` with `JOB_HUNT_SYSTEM` + `JOB_HUNT_PRACTICE_USER` prompt constants and `research_practice_jobhunt()` method
- Run deliberate seeding: top 300 practices at $30 total
- Add ALTER TABLE migration for new queryable columns: `succession_intent_detected VARCHAR(20)`, `new_grad_friendly_score INTEGER` (verify against SQLite schema before running)
- Update `sync_to_supabase.py` to include new columns in the incremental sync
- Implement 5-lens map system in `launchpad-map.tsx` (reuses Mapbox GL pattern from `practice-density-map.tsx`)
- Build remaining 3 dossier tabs: Compensation Benchmarks, Mentorship Signals, Interview Prep
- Build `dso-tier-card.tsx` for DSO track (shows tier badge, rationale, primary source citation)
- Implement scoring confidence modifier (cap at 70 for thin data)

### Phase 3 — Polish (1–2 weeks, 5 commit-sized chunks)

**Goal:** Production-quality tool, distribution-ready.

- Mapbox Isochrone API integration for true commute-radius overlay (replaces Haversine v1)
- Contract red flag interactive parser (paste contract text → AI extracts specific traps; use research_engine.py raw HTTP pattern, one-off endpoint)
- Compensation calculator (production% × collection rate, lab fee deduction toggle, draw-deficit toggle)
- Saved practices / pinboard (mirror Warroom's PinboardTray component pattern from `pinboard-tray.tsx`)
- DSO tier list quarterly refresh job (add to weekly_research.py or standalone cron)
- Boston Metro living location presets (4 presets: Back Bay, Cambridge, Newton, All Boston Metro)

---

## 10. Risks and Open Questions

These are decisions Suleman needs to make before opening the execution session.

**1. DSO Tier List: Curated vs LLM-Generated**

Current plan: hand-curate v1 from the domain research in Section 2 of this document, stored as a TypeScript constant. The risk is staleness — DSOs change ownership (Smile Brands was recapped in 2022, Benevis was acquired from Forba/Church Street Health Management). A quarterly LLM review could keep it fresh but introduces hallucination risk on factual claims (dates, settlements, acquisition history). Recommendation: hand-curate v1, add LLM-augmented quarterly review in Phase 3. Never surface a tier rating without a citable primary source — avoid editorializing beyond what the sources support.

**2. Data Acquisition Budget**

Full Chicagoland seeding (~3,000 practices × $0.10) = ~$300–500. This is a one-time cost that unlocks the full signal catalog for Phase 1 Day 1. The alternative is the $5/week organic build-up, which takes ~60 weeks to reach equivalent coverage. Decision: authorize the one-time seeding run before Phase 2 begins, or wait.

**3. DentalPost Job Board Integration**

DentalPost [Terms of Service](https://www.dentalpost.net/terms/) prohibit automated scraping. Three options: (a) skip entirely, let AI-research infer hiring status from website/Google/LinkedIn only — this is the conservative path and already adequate for v1; (b) pursue a data partnership API agreement with DentalPost (cost unknown, timeline 1–3 months); (c) accept ToS risk for MVP only. Recommendation: option (a) for all phases. The existing AI research pipeline already detects hiring signals from public website job pages and Google reviews — this is sufficient signal quality without ToS exposure.

**4. Boston Metro Support**

`LIVING_LOCATIONS` currently has Chicagoland presets only. Boston represents a natural second market (BU, Tufts, Harvard dental schools all within the metro). Adding 4 Boston presets (Back Bay/South End, Cambridge, Newton, All Boston Metro) requires expanding `watched_zips` to include the 21 already-tracked Boston ZIPs, and updating `LIVING_LOCATIONS` in `src/lib/constants/living-locations.ts`. This is low-effort (1 session) and should be included in Phase 1 Chunk 1 if Suleman confirms the target audience includes Boston grads. Otherwise defer to Phase 3.

**5. Track Ambiguity Display**

Some practices score strongly across multiple tracks (a high-volume ethical practice with a retiring owner). Show all 3 scores per practice row, or only the winning track? Recommendation: show the winning track score prominently with the track name as a badge; show the other two scores as small secondary indicators in the dossier Snapshot tab. This keeps the list clean while preserving the full picture in the dossier.

**6. Compensation Data Legal Sensitivity**

Showing a practice-specific estimated income ("Dr. Smith's practice: $175k estimated") could create legal exposure if the estimate is wrong and a grad relies on it. Recommendation: never surface practice-specific dollar estimates. Show only ZIP/state-level ADA HPI ranges and DSO-class comp ranges (sourced from SalaryDr and Heartland/PDS public comp pages). The compensation calculator uses ADA ranges as input assumptions, not practice-specific projections.

**7. Dental School Partnership (v3 Opportunity)**

UIC College of Dentistry, Northwestern, U-Michigan, and Loyola are all within the Chicagoland market. A faculty-facing or residency-director-facing version of Launchpad (with practice ownership data, buyability score, and succession signals) could be a genuine distribution channel. This is entirely out of scope for v1 and v2 but worth noting as a v3 distribution path if the tool proves useful internally.

**8. AVOID Tier Defamation Risk**

Calling Aspen Dental "AVOID" with citation to the [NY AG 2015 settlement](https://ag.ny.gov/press-release/2015/attorney-general-schneiderman-announces-settlement-aspen-dental) and [PBS Frontline 2012](https://www.pbs.org/wgbh/frontline/film/dollars-and-dentists/) is defensible as opinion grounded in documented fact. The risk escalates if user-generated reviews or AI-synthesized claims are mixed in without sourcing. Recommendation: AVOID badges cite only primary sources (regulatory settlements, government actions, court records). Green flag signals (mentorship culture, employee ownership) cite company About pages directly. No user-generated review text should be reproduced verbatim.

---

### QA Discrepancies (For the Record)

Three minor discrepancies were noted between scout reports and verified file state:

- "All Chicagoland" ZIP count is **269** in the actual `LIVING_LOCATIONS` constant (not 268 as stated in `CLAUDE.md`). The constant is the source of truth; the documentation is stale by one ZIP.
- `warroom-shell.tsx` is **741 lines** (verified by `wc -l`), not 760 as the scout-warroom report claimed. The architectural pattern is correct; only the line count was off.
- Mortenson Dental Partners is described as "employee-owned" on their About page — not "ESOP" specifically. The distinction matters: ESOP is a specific legal structure; "employee-owned" is the term they use publicly. Use their language.

---

*End of plan. Estimated read time: 20 minutes. Open execution session after Suleman confirms decisions on items 10.1–10.4.*
