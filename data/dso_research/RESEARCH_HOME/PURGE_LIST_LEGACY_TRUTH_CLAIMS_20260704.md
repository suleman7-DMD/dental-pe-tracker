# PURGE LIST — Legacy Detector Claims in the UI
**Author:** Fable (PM) · 2026-07-04 · Deliverable 3 of SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md
**Governing decision (user, 2026-07-04):** *remove* legacy ownership claims from the UI, don't
relabel them. Detector output stops being an ownership answer anywhere users read one.
**Boundary — what is NOT purged:**
- **Database columns and pipeline stay.** `entity_classification`, `zip_scores.corporate_location_count`,
  floor CI guards (`FLOOR expect_min=268`, `FLOOR_NPI expect_min=1152`) are untouched (charter §2.10).
  The detector still prioritizes future census waves and cross-checks census QA. This purge is UI-only.
- **Methodology (`/data-breakdown`) keeps ONE detector exhibit**: the floor-vs-census story
  (how the automated floor was built, why hand review superseded it, ADA anchors + unit caveat).
  `CorporateBandBar` + `consolidation-honesty.ts` live there and only there.
- **Raw-audit surfaces** (practice drawer "raw source" fields, SQL explorer presets) may show
  `entity_classification` as a raw column, labeled "Legacy detector estimate (context)".

Status legend: ✅ done · Phase N = scheduled in that phase of the charter.

## `/job-market` — Directory (priority 1)
| Claim / component | Verdict | Status |
|---|---|---|
| "Confirmed Corporate" KPI (classifyPractice, corporate band) | REMOVE | ✅ 61dabe2 |
| "Not Confirmed Corp." KPI | REMOVE | ✅ 61dabe2 |
| Unknown-ownership warning banner (detector unknowns) | REMOVE | ✅ 61dabe2 |
| Header copy "legacy detector fields remain visible" | REMOVE (rewritten census-first) | ✅ 61dabe2 |
| `computeZipStats()` per-ZIP dso_affiliated/consolidation_pct (classifyPractice) feeding saturation map/table | REPLACE with per-ZIP census bucket counts (unresolved visible) | ✅ aa25ae4 |
| `market-overview-charts.tsx` detector ownership pie | REMOVE → five-bucket census chart | ✅ 2632a56 |
| `ownership-landscape.tsx` (detector corporate/independent breakdown) | REMOVE → census bucket landscape | ✅ 2632a56 |
| `practice-density-map.tsx` marker colors via classifyPractice | REPLACE colors with census tier colors; unreviewed = neutral gray | ✅ aa25ae4 |
| `opportunity-signals.tsx` / `market-analytics.tsx` detector-derived signals | REPLACE with census-tier signals; missing census → "needs research" | ✅ 2632a56 + aa25ae4 |
| `practice-detail-drawer.tsx` entity_classification field | DEMOTE to raw-audit section with legacy label; census record primary | ✅ 824c48d (census block first w/ evidence + link to full record; detector fields → "Raw Source Audit" section; multi-ZIP claim softened to name-match signal) |

## `/launchpad` — Job Hunt (priority 2)
| Claim / component | Verdict | Status |
|---|---|---|
| `lib/launchpad/ranking.ts` + `signals.ts` ownership points from entity_classification | REPLACE with census-tier scoring; unknown → capped score + honest "Needs research" lane (rule §2.9) | ✅ de4e6bd |
| AI routes' PracticeSnapshot passing detector fields as ownership | RELABEL in payload (detector = context field; census record = ownership) so AI copy can't launder detector claims | ✅ 724f7bd (went further: detector ownership fields removed from PracticeSnapshot; only peer_class survives as a non-ownership percentile key) |
| Track lists / dossiers showing detector chips | REPLACE with CensusBadge | ✅ de4e6bd |

## `/market-intel` — Ownership (priority 3)
| Claim / component | Verdict | Status |
|---|---|---|
| Headline corporate-share KPIs off `zip_scores.corporate_location_count` | REMOVE → five-bucket stacked truth bar from `summarizeBuckets` | Phase 3 |
| `consolidation-map.tsx` ZIP colors by detector corporate share | REPLACE with census bucket share per ZIP; unresolved rendered explicitly | Phase 3 |
| `CorporateBandBar` as page headline | DEMOTE to `/data-breakdown` only | Phase 3 |
| `city-practice-tree.tsx` / `zip-score-table.tsx` corporate columns/chips | REPLACE with census bucket columns | Phase 3 |
| ADA 14.6% anywhere near a non-T4+T5 number | RELABEL: only `dsoPePct*` may anchor to ADA, with `ADA_ANCHOR_UNIT_CAVEAT` | Phase 3 |

## `/buyability` — Acquisition Scout (priority 4)
| Claim / component | Verdict | Status |
|---|---|---|
| `buyability_score` independence points from detector classification | REFRAME: candidate set = census T1/T2 (+ owner age + intel); score capped and explained when census missing | Phase 3 |
| "Independent" chips via isIndependentClassification | REPLACE with CensusBadge | Phase 3 |

## `/warroom` — Review Desk (priority 5)
| Claim / component | Verdict | Status |
|---|---|---|
| `lib/warroom/ranking.ts` / `signals.ts` detector-driven target logic | REPLACE: warroom becomes census ops/QA workbench (holds, triage, undetermined, duplicate queues) | Phase 3 |
| Target-list detector chips | REPLACE with CensusBadge + source-class chip | Phase 3 |

## Home `/`
| Claim / component | Verdict | Status |
|---|---|---|
| "Legacy Floor" KPI (detector corp rows) | REMOVE (story moves to Methodology) | Phase 3 (home recompose) |
| "Scout Queue" KPI ("legacy heuristic") | DEMOTE now, REPLACE when buyability reframes | Phase 3 |
| Local `TIER_ROWS` const in home-shell duplicating tier labels/colors | REPLACE with contract `TIER_META` (consumer rule) | Phase 3 |

## Cross-cutting
| Item | Verdict | Status |
|---|---|---|
| `census-badge.tsx` duplicate tier labels ("Verified Independent" overclaim) | REPLACED — labels now from ownership-truth contract | ✅ 61dabe2 |
| `queries/census.ts` `independentReviewed` counting T2 as independent | REMOVED — buckets via `summarizeBuckets` | ✅ 68796d6 |
| `sql-presets.ts` entity_classification presets | KEEP (raw audit surface), preset descriptions say "legacy detector" | ✅ 824c48d (3 presets renamed "(legacy detector)" + SQL comment headers stating not census truth) |
| F27 test + `classifyPractice` helpers | KEEP while any consumer remains; delete helpers only when the last non-Methodology consumer is gone, and replace F27 with a census-era guard (ownership-truth tests already lock the bucket law) | end of Phase 3 |
