# SPEC — Truth-Safe App, Route by Route
**Author:** Fable (PM) · 2026-07-04 · Deliverable 1 of SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md
**Interfaces:** every ownership fact renders through `src/lib/census/ownership-truth.ts`
(see DATA_CONTRACT_TRUTH_APP_20260704.md). Legacy verdicts per PURGE_LIST_LEGACY_TRUTH_CLAIMS_20260704.md.
**Governing user decision (2026-07-04):** legacy detector output is REMOVED from user-facing
ownership surfaces (not relabeled). It survives only in Methodology (as history) and raw-audit views.

One spine: **the practice directory**. Each practice = one truth-backed record (ownership +
evidence + job context + acquisition relevance + review status). Every page is a lens on that spine.

Denominators (unit law): location universe = SUM(zip_scores.total_gp_locations) live;
NPI rows ≠ locations; reviewed% states its scope (universe vs reviewed). No hardcoded tallies.

---

## 1. Directory — `/job-market` (priority 1, Phase 1)
**Purpose:** the front door. Find any Chicagoland GP practice; see who owns it, with evidence status.
**Shows:** search + filters (city/ZIP/living-location, ownership bucket, tier, confidence,
evidence status, network, PE-backed, source class); table rows = practice cards with CensusBadge +
source-class chip; header KPIs = structural (clinic count, density) + census coverage FOR THE
SELECTED SCOPE (reviewed/unresolved of that location's ZIPs — computed live, never IL-wide numbers
presented as location-scoped).
**Actions:** search → open `/practice/[locationId]`; filter by bucket; export/pin.
**Legacy:** detector KPIs/banner removed (✅ 61dabe2); Phase 1 replaces detector zip-stats,
overview charts, ownership-landscape, map colors, opportunity signals (see purge list).
**Reuse:** `practice-directory.tsx` table + CensusBadge already census-first; keep saturation
table for density (non-ownership) with detector columns swapped for census buckets.
**Verdict:** KEEP route, label "Directory". This page is the product.

## 2. Job Hunt — `/launchpad` (priority 2, Phase 1)
**Purpose:** D4 → Chicagoland associate job. Where to apply, what to know, what to avoid.
**Shows:** three honest lanes (rule §2.9 — no fake precision):
  1. **Verified job targets** — census-reviewed, hiring-relevant (T2–T5 employ associates; T4/T5
     flagged as DSO employment with PE context; T1 solo = rare associate demand, shown honestly).
  2. **Promising leads** — census-reviewed but thin intel, or strong non-ownership signals.
  3. **Needs research** — unreviewed/undetermined. Capped score, explicit "why capped" line.
Scores: explainable, census-tier-driven, capped when intel thin. AI features (briefing, interview
prep) receive the ownership record with source class so generated copy states evidence status.
**Legacy:** ranking/signals off entity_classification → replaced (purge list). 
**Verdict:** KEEP route, label "Job Hunt". Second lens on the spine.

## 3. Ownership — `/market-intel` (priority 3, Phase 3)
**Purpose:** THE consolidation-truth page: how much of Chicagoland dentistry is what.
**Shows:** five-bucket stacked truth bar (`summarizeBuckets` of full IL scope) as the headline;
"Not Solo Owner-Operated %" as the broad top-line (labeling law); T4+T5 share beside ADA 14.6%
with unit caveat; per-ZIP map colored by census bucket share with unresolved rendered explicitly;
network/sponsor drill-down (network_id groups, pe_backed).
**Legacy:** corporate-share KPIs, detector map colors, CorporateBandBar headline → removed/demoted.
**Verdict:** KEEP route, label "Ownership". The five buckets are the page.

## 4. Acquisition Scout — `/buyability` (priority 4, Phase 3)
**Purpose:** which practices could be bought (succession targets) — census-grounded.
**Shows:** candidate set = census T1/T2 (+T3 where owner-dentist retiring), owner age/tenure,
succession signals, capped buyability score with reasons; unresolved rows shown as "not assessable
yet — needs census review" (never silently scored).
**Legacy:** detector-independence scoring → reframed (purge list).
**Verdict:** KEEP route, label "Acquisition Scout".

## 5. Review Desk — `/warroom` (priority 5, Phase 3)
**Purpose:** ops/QA workbench for the census itself.
**Shows:** queues — holds (91: 52 dso_verify + 30 unresolved + 9 duplicate_suspect), triage (649),
undetermined-researched (~477), never-researched (~950 wave-5) [counts live from artifacts until a
`census_review_status` column syncs — labeled file-sourced; recheck: charter §1a]; duplicate/closure
queues; audit failures; PM decision log.
**Legacy:** detector target-ranking → replaced by census ops queues.
**Verdict:** KEEP route, relabel content from "war room targets" to "Review Desk".

## 6. Practice page — `/practice/[locationId]` (Phase 2)
**Purpose:** THE core object. Tabs: Ownership & evidence (OwnershipRecord: tier, bucket, confidence,
evidence URLs, network siblings) / Job-hunt intel / Acquisition-succession / Network siblings
(network_id) / Raw source audit (NPI rows, detector fields labeled legacy — the ONLY non-Methodology
place detector values appear, as raw audit data).
**Verdict:** KEEP; becomes the canonical destination of every row link.

## 7. The rest
- **PE Deals `/deal-flow`** — KEEP as context, every number chip `pe_deal_context`; link deals to
  network_id where known. DEMOTE from headline navigation prominence.
- **Evidence `/research`** — KEEP: evidence browser (ownership_evidence_urls/basis by network).
- **Research Notes `/intelligence`** — KEEP: narrative notes; census citations where relevant.
- **Methodology `/data-breakdown`** — KEEP + becomes the detector's ONLY exhibit hall: floor story
  (268 locations / 1,152 NPIs, CI-guarded), CorporateBandBar, ADA anchors, unit discipline, census
  method (tiers, evidence rules, holds).
- **System `/system`** — KEEP: census sync-state card (✅ 61dabe2) first, then pipeline health.
- **Home `/`** — Phase 3 recompose from truth components: census KPI strip (already close),
  five-bucket bar, entry cards to Directory/Job Hunt/Ownership. Remove "Legacy Floor" KPI; demote
  "Scout Queue"; TIER_ROWS → contract TIER_META.

## Phase order & gates
Phase 1 (post-sync): Directory + Job Hunt. Phase 2: practice page + global search. Phase 3:
Ownership bar, Scout reframe, Review Desk, Home recompose. Every phase: `npm run build` +
`npx vitest run` green (ownership-truth tests = the truth-law gate), then a banking commit.
**Phase 1+ census UI is blocked until the two Supabase sync legs run (user-authorized).**
