# VISION: The Optimal Dental PE Intelligence Platform

*Written May 2026. Grounded in the real codebase — every surface, table, and data asset cited here exists today.*
*This is description, not a plan. What the finished, world-class version looks like.*

---

## 0. What This Thing Actually Is (and Could Become)

Right now, this platform is a single-user intelligence tool — a founder-grade research environment for tracking PE consolidation in dentistry, finding first jobs, and spotting acquisition targets. The data engine is real, the classification system is real, the AI research layer is real. What isn't real yet is the full potential of the dataset.

The optimal version of this app is the Bloomberg Terminal of dental private equity: a continuously-refreshed, nationally-scoped, ML-classified, entity-graph-resolved intelligence system with a command surface sophisticated enough that a PE associate, a dental group CFO, a DSO recruiter, and a graduating dental student each find their own irreplaceable workflow inside it. It is not a dashboard. It is an operating environment.

Below is what that looks like.

---

## 1. Data Foundation: From 290 ZIPs to the Whole Country

### National Coverage

The current database covers 381,598 NPI rows across the US, but the *watched* scope is 290 ZIPs — 269 Chicagoland and 21 Boston Metro. That geographic constraint is an artifact of compute budget, not ambition. The NPPES federal data that populates `practices` already contains every licensed dentist and dental organization in all 50 states. The classifier (`dso_classifier.py`), the scoring engine (`merge_and_score.py`), and the Supabase sync already operate on the full national table; they're just not running entity classification or ZIP scoring on all ~14,000 US dental ZIPs.

In the optimal version, there are no "watched" vs. "unwatched" ZIPs. Every US ZIP with at least one GP dental practice gets a `zip_scores` row. Every practice gets `entity_classification`. The pipeline running on Sunday mornings classifies nationally, not just for two metros. The Warroom can point at Phoenix, Miami, Nashville, or the entire Sun Belt. The `/market-intel` consolidation map shows every state as a real choropleth, not as an inert gray layer for the 48 non-watched states.

The 290 ZIP constraint today is a practical limitation. The data model already supports removing it.

### Identity Resolution: The NPI-Location-Owner-Fund Graph

The current database holds a genuine data asymmetry: every dental NPI in the country, every PE deal announcement since 2020, and partial corporate ownership signals via `dso_national`/`dso_regional` classification. What it does not have is a resolved corporate ownership graph that connects the dots between them.

The optimal version resolves this. The `practice_to_location_xref` table (introduced in the `dc18d24` dedup rewrite) is the right foundation. On top of it, the graph extends:

- **NPI → Location → Entity**: each physical clinic maps to a parent legal entity (using EIN from Data Axle, franchise from the same importer, IUSA numbers already in the `practices` schema)
- **Entity → Platform → PE Fund**: each DSO platform maps to its PE sponsor — already partially resolved in the `deals` table's `pe_sponsor` and `platform_company` columns, but not joined back into practice-level data
- **Fund → Portfolio**: each PE fund's dental portfolio — all practices they control, across all platforms, across all geographies — resolved as a single graph query

Today, if you want to know "how many practices does Heartland Dental's PE backer currently control in Illinois," you need to hand-join the `deals` table, the `practices` table's `affiliated_dso` field, and the `platforms` table. In the optimal version, that's a single node traversal in a maintained ownership graph. The Warroom's "Deal Catchment" zone around a target practice becomes "PE fund exposure radius" — how many practices within 10 miles are already in the same fund's portfolio.

The raw materials exist: `ein`, `franchise_name`, `iusa_number`, `parent_company`, `affiliated_dso`, `affiliated_pe_sponsor` are all columns in `practices`. Data Axle's Pass 6 (Corporate Linkage Detection) already clusters practices by parent company and EIN. The missing piece is assembling these signals into a maintained graph structure rather than flat columns.

### Historical Time-Series

The platform has no historical time-series of practice-level data. The `practice_changes` table (8,848 rows) logs name/address/ownership transitions but is not designed for longitudinal queries like "show me the corporate share in ZIP 60629 each month for the last three years." The `deals` table covers October 2020 through March 2026, but the practices table itself is a current snapshot.

The optimal version adds a `practice_snapshots` table: a weekly or monthly materialized snapshot of key fields for every watched practice — `entity_classification`, `buyability_score`, `employee_count`, `estimated_revenue`, `num_providers`. This is not large. At 290 ZIPs × ~4,889 GP locations × weekly snapshot × 3 years, it's ~23 million rows — well within Supabase Postgres range, trivially achievable with a `pg_cron` job.

With that table, every chart that currently shows a static "current state" metric becomes an animated time-series. The Market Intel consolidation map shows corporate share trending up or down in each ZIP over 36 months. The Warroom's retirement-risk flag shows practices that have *worsened* their retirement profile (aging out with no heir) rather than just practices that are already at risk today. The Deal Flow timeline shows not just when announcements were made, but when the underlying practices changed classification status.

### Data Quality and Provenance

The `/data-breakdown` page (added April 26, 2026) is the right instinct taken to its logical extreme. In the optimal version, every visible number has a metadata tooltip showing: source table, last-updated timestamp, upstream source (NPPES monthly, Data Axle import date, AI-research date), classification confidence band, and any known caveats (like the NPI-row vs. location distinction that currently trips up every new reader of the codebase).

The "data thin" confidence cap at 70 for practices without `practice_intel` rows — currently enforced in both `src/lib/warroom/ranking.ts` and `src/lib/launchpad/ranking.ts` — extends to every KPI surface. If a ZIP's `metrics_confidence` is `low`, its consolidation percentage is shown with a visual uncertainty band, not a crisp number. If a practice's `classification_confidence` is below 40, its tier badge shows a hollow rather than filled indicator. The app teaches users how much to trust each data point rather than presenting all numbers with equal authority.

---

## 2. Classification and Intelligence: Beyond Heuristic Rules

### From Rule-Based to ML Classification

The current 4-pass heuristic classifier (`dso_classifier.py`) is genuinely good — it handles the `dc18d24` location-dedup fix, the Phase B phone-only signal demotion, and the 11-class taxonomy correctly. But it is brittle: changes in NPPES taxonomy codes, new DSO naming conventions, or a wave of rebranding can silently shift classifications. The `phantom_inventory_flag`, `stealth_dso_flag`, and `revenue_default_flag` signals are pattern-matched heuristics that were built one observation at a time.

The optimal classification layer trains a gradient-boosting classifier (XGBoost or LightGBM — not a neural net, interpretability matters here) on the existing labeled data. The labeled set is large: 13,818 NPI rows in watched ZIPs, all with `entity_classification` assigned, plus `classification_reasoning` text that records *why* each label was chosen. That reasoning text, parsed and featurized, becomes the training signal. Features include provider count at address (from `practice_locations`), last-name Jaccard similarity across co-located providers, taxonomy code prefix, employee count quintile, revenue tertile, EIN co-occurrence count, franchise field presence, Data Axle `parent_company` fuzzy match, and whether any NPI at the address appears in the `deals` table as a target.

The classifier outputs a probability vector across all 11 classes. The classification system stops at the first rule that fires and instead uses the argmax of the probability vector, with the second-highest probability surfaced as an "alternative classification" badge in the Warroom dossier. "Solo established (87%) — could be family practice (11%)" is more honest and more useful than a deterministic label that was wrong 13% of the time but never said so.

Critically: the model is retrained weekly when the pipeline runs. New NPPES data means new labeled examples. The Warroom's "flag a misclassification" button (described below) sends corrections directly into the training feedback loop.

### The Corporate Ownership Knowledge Graph

The `dso_national` and `dso_regional` classes identify corporate-controlled practices but do not resolve which PE fund ultimately controls them. Today, Aspen Dental appears in `affiliated_dso` as "Aspen Dental" — but the actual ownership structure is Aspen Dental Management Inc., backed by Leonard Green & Partners (historically) and more recently recapitalized. That graph node — PE fund → DSO platform → individual practice — is currently only resolved at the deal level (the `deals` table has `pe_sponsor` and `platform_company`), not at the practice level.

The optimal version maintains a `corporate_ownership_graph` table with nodes (fund, platform, entity, location) and edges (controls, backs, owns_stake_in) with timestamps. When a new deal is scraped from GDN or PESP, the parser not only inserts the deal row but also upserts edges in the graph. When a practice's `affiliated_dso` changes from `NULL` to `"Heartland Dental"`, the graph automatically inherits the current PE sponsor of Heartland from the most recent relevant deal. The Warroom's "PE Deals in Scope: 0" problem — currently broken because `deals.target_zip` is NULL for all 2,910 deals — disappears: the graph resolves practice → DSO → deal without relying on the `target_zip` field.

### Predicting Acquisitions Before Announcement

This is the platform's most defensible unique capability, and it barely exists today. The `buyability_score` and `retirement_combo_flag` are primitive version-1 proxies for acquisition risk. The optimal version trains a predictive acquisition model on the historical record of what practices were acquired, and what their pre-acquisition signals looked like.

The training set: the 2,861 deals in the `deals` table, cross-referenced back to the practices table. For every deal whose `target_name` fuzzy-matches a practice in `practice_locations`, the pre-acquisition snapshot (using the `practice_changes` log and the hypothetical `practice_snapshots` table above) becomes a positive training example. Features: year established, employee count, num_providers, ZIP-level `corporate_share_pct`, ZIP-level `dld_gp_per_10k`, ADA HPI benchmark gap for the practice's state, recent change activity, owner career stage (derived from year_established + num_providers), and the existing 8 practice signal flags.

Output: a probability score "likelihood of acquisition within 18 months" — surfaced as a new lens in the Warroom, a new tier in the Launchpad red-flag system ("PE Exposure Risk"), and a new KPI on the Deal Flow page. A practice showing elevated acquisition probability before any public announcement is the platform's highest-value signal. A PE associate or a dental grad considering joining a practice both need to know if that practice is about to be sold out from under them.

---

## 3. The Qualitative AI Layer: From Batch Research to Living Intelligence

### The Current State and Its Ceiling

The research engine (`scrapers/research_engine.py`) is well-architected — raw HTTP calls to the Anthropic API, forced web search via `tool_choice`, per-field source URLs, a 4-layer anti-hallucination gate. The batch pipeline (`dossier_batch/`) can run at $0.008/practice. The 2,996 practice_intel rows represent genuine AI-verified intelligence.

But the coverage ceiling is real: as of May 2026, 287 of 290 ZIP intelligence records are synthetic placeholders with no actual web search. The weekly $5 research budget fills maybe 50 practices per week organically. And there's no freshness mechanism — a `practice_intel` row written 90 days ago has a TTL, but nothing triggers re-research when the underlying data changes.

### Continuous, Event-Triggered Research

The optimal qualitative layer is not a batch job running on Sunday mornings. It is an event-driven research system.

When NPPES monthly update lands and a practice changes its `num_providers` (more dentists → practice growth), it triggers a high-priority research queue entry. When `practice_changes` logs an ownership transition, it triggers immediate re-research on both the acquired and the acquiring entity. When a new deal appears in `deals` targeting a DSO brand that has 3+ locations in a ZIP, every independent practice in that ZIP gets queued for research at elevated priority. The research engine processes the queue continuously, with model routing by urgency: Haiku for steady-state refresh, Sonnet for high-priority events, Claude Opus for the 50 highest-buyability practices in each metro at quarterly cadence.

The result: not 3 freshly-researched ZIPs out of 290, but 290 ZIPs with research updated within the last 30 days, proportional to how much each ZIP is actively consolidating. Not 3,370 practice intel rows frozen at April 2026, but a living file that updates when facts change.

### The Warroom Copilot

Today, the Warroom's intent bar (`intent-bar.tsx`) parses natural language into filter state via a lookup table of synonyms (`intent.ts`). "Show me stealth DSOs in Oak Park" correctly resolves. But "show me practices that are likely to be acquired this year and are not yet on anyone's radar" requires the user to manually configure multiple filters.

The optimal Warroom copilot is a genuine AI planning layer. The user speaks to the Warroom through a persistent chat interface (not just the ⌘K single-shot intent bar). "I want to find solo practitioners over 60 who have no associate and are seeing declining Google review velocity — give me the top 10 in Naperville" executes a multi-step reasoning chain: parse the criteria, construct the Supabase query, execute it, score and rank results, then narrate the findings in a briefing rail that sounds like a sharp analyst. The copilot has access to the full data context: `practice_signals`, `practice_intel`, `zip_scores`, `deals`, `ada_hpi_benchmarks`. It cites sources.

The "compound-narrative" route already exists at `/api/launchpad/compound-narrative` and calls Sonnet 4.6 with `practice_intel` context. That's the seed. The copilot is that logic generalized: instead of one practice, it operates over the ranked target list. Instead of a 200-300 word thesis, it can answer follow-up questions. Instead of generating on demand for one practice, it pre-generates briefings overnight for the top 20 targets in each scope.

### The Launchpad Copilot

The Launchpad's AI narrative (`narrative-card.tsx`) already generates "why this practice for me" on demand via Claude Haiku. The 6 AI routes added in Phase 3 (ask-intel, compound-narrative, interview-prep, zip-mood, contract-parse, smart-briefing) are the right structure. What they lack is continuity — each invocation is stateless, with no memory of the user's previous research.

The optimal Launchpad copilot has a session context: it knows the user's selected track, their pinned practices, their saved searches, and any questions they've asked in the current session. When the user asks "what's the catch with Dr. Kowalski's practice?" it checks the pinboard, retrieves the relevant `practice_intel` row and the `practice_signals` overlay, cross-references recent `practice_changes`, and narrates a synthesized answer that draws on all those sources — with citations. When the user says "compare my top 3 picks for succession track," it computes differential signal breakdowns and surfaces the clearest distinguishing factors, not just side-by-side metric tables.

---

## 4. Product Surfaces: What God-Mode Really Looks Like

### The Warroom: Acquisition Command Center

The current Warroom has the right architecture — two modes (Hunt, Investigate), four lenses, 11 scopes, living map, ranked target list, dossier drawer, pinboard, keyboard shortcuts, URL-synced state. It is genuinely the most sophisticated surface in the app. The optimal version extends it in three directions.

**Direction 1: The Living Intelligence Feed.** The "what's new since last visit" proposal (referenced but unbuilt in the Warroom Ship Log) becomes a persistent intelligence briefing at the top of the Warroom. Not just "N new practice_changes in scope since your last visit" but a narrative: "Since Thursday, two practices in Naperville have changed ownership status, one new DSO location opened in ZIP 60540, and a GDN article announced Heartland's acquisition of a group practice 4 miles from your pinned target Dr. Ahmad. Do you want to review the updated dossier?" This briefing is generated nightly by the AI layer for each scope and cached — it is not computed on the fly when the user opens the Warroom.

**Direction 2: The Corporate Radar.** A new fifth lens — "PE Exposure" — colors ZIPs not by current corporate share but by predicted corporate interest over the next 18 months (from the acquisition prediction model above). ZIPs where the prediction model shows elevated risk light up in amber before any deal is announced. Drilling into such a ZIP shows the individual practices with high acquisition probability, their signal flags, their proximity to existing DSO locations, and the PE funds most active in adjacent ZIPs. This is the only surface in the market that could give a buyer or a graduating dentist early warning of consolidation in their target neighborhood.

**Direction 3: The Action Layer.** The current Warroom's lifecycle stages (Untouched / Researching / Contacting / In dialogue / Passed / Won) live in localStorage per device. In the optimal version, they live in Supabase behind lightweight auth. When a practice moves from "Researching" to "Contacting," that triggers an automatic research refresh (re-run `practice_deep_dive.py` against the NPI). When a practice moves to "In dialogue," a templated outreach brief generates — owner name, estimated practice age, buyability score, ZIP market context, suggested opening offer range derived from ADA HPI comps. The Warroom becomes not just a research tool but a deal-management surface. The pinboard becomes a CRM.

**The Map Gets Real.** Currently, 20.5% of practices in watched ZIPs have lat/lon coordinates (from Data Axle). The living map (`living-map.tsx`) therefore shows ~80% empty space. The optimal pipeline geocodes all 13,818 watched-ZIP NPI rows using the USPS standardized address already in the practices table. With 100% geocoding, the Mapbox choropleth layers resolve to individual dots for every GP practice, every DSO cluster becomes visible as a geographic pattern, and the "micro-cluster" signal flag actually shows spatial clusters rather than inferring them from ZIP co-location.

### The Launchpad: First-Job Finder at Its Limit

The Launchpad's 20-signal scoring engine, 3-track model, 5-tab practice dossier, and curated DSO tier list are substantively correct. The gaps are coverage (only 0% of practices have source-backed intel), freshness (DSO tier list is static), and feedback (no mechanism for grads to report whether a job was what the score predicted).

The optimal Launchpad adds four things the current version does not have.

**First: Live Hiring Pipeline Integration.** The FTC enforcement question around dental job boards aside, the optimal version detects active hiring signals not from AI scraping Google reviews but from direct practice website monitoring. A nightly crawler checks the careers/jobs page of every practice in watched ZIPs with a buyability score above 50. Job postings are extracted, timestamped, and stored in `practice_intel.associate_openings`. When a practice posts an "associate dentist" listing, the `hiring_now_signal` fires immediately and the practice's tier badge updates to "Active Opening" in the Launchpad list. The user does not need to run a manual research batch to see this.

**Second: The Compensation Reality Check.** ADA HPI benchmarks (918 rows in the `ada_hpi_benchmarks` table) currently show state-level DSO affiliation rates by career stage. The optimal version extends this table with compensation percentile bands by ZIP cluster: GP associate median, P25, P75, split by practice type (solo, small group, DSO). This data comes from ADA HPI's annual survey, cross-referenced with SalaryDr aggregate data and the Data Axle `estimated_revenue` field. The Compensation tab in the practice dossier shows not just "ADA HPI Illinois average $160k" but "practices of this type in this ZIP cluster typically pay $145k-$185k for an associate; this practice's revenue and employee count suggest it can support $155k." That's a claim the current system cannot make honestly. The optimal version can.

**Third: The Exit Map.** A dental grad's first job decision is not just about year-one income. It is about what happens in year 3-5. The Launchpad's Succession Track scoring does some of this — `succession_track_signal` fires when a practice has a retiring owner and open buyability. The optimal version adds an explicit "exit scenario" section to the practice dossier's Snapshot tab: if this practice matches the succession profile, a simple DCF model estimates what a buyout would cost in year 4 (using ADA HPI data on practice valuations as 60-80% of annual collections) and what the monthly debt service would look like against the grad's existing student loan burden. Not financial advice — a planning tool with honest assumptions displayed.

**Fourth: Alumni Network Signal.** The most useful signal for a new grad evaluating a practice is whether anyone who worked there is findable and willing to share their experience. The optimal Launchpad integrates a lightweight crowdsourced layer: users who went through the tool can optionally submit a 5-field "outcome report" (joined/didn't join, practice matched the score, track recommendation, would you revisit this ZIP). These reports aggregate into a practice-level "community signal" badge — not a Glassdoor review, but a thin overlay that shows "2 of 3 grads who contacted this practice recommended it for Succession Track." This turns the Launchpad from a solo research tool into a network.

### Deal Flow: From Chart Gallery to Prediction Surface

The current Deal Flow page (/deal-flow) presents 2,861 deals across four tabs: Overview, Sponsors, Geography, Deals. It correctly visualizes the deal volume timeline, top sponsors, state choropleth, and searchable table. These are retrospective.

The optimal Deal Flow adds a forward-looking layer: a "Deal Radar" tab driven by the acquisition prediction model. Rather than showing only announced deals, it shows the practices flagged as high acquisition probability that do not yet appear in the deals table — the "dark pipeline" of likely-but-unannounced acquisitions. It shows PE funds that are actively buying (deals in the last 90 days) ranked by ZIP-level presence in watched metros, so a user can anticipate which geographies are next in each fund's rollup strategy. And it shows DSO platforms whose last deal was 12+ months ago, flagging them as potentially paused (financial distress, PE recap in progress, management transition) — signal for grads considering joining them.

### Market Intel: From Map to Scenario Tool

The Market Intel page's three tabs (Consolidation, ZIP Analysis, Ownership) are honest and accurate post the April 2026 audit fixes. The optimal version adds a fourth tab: **Scenario Planner**.

The user inputs a proposed acquisition: "I'm considering buying Dr. Chen's practice at 1234 Oak Park Blvd — 3 providers, $900k annual collections, established 1998." The planner queries the ZIP score and surrounding practice landscape, computes how the acquisition would change the buyer's market position (from zero to first-mover in a 70% independent ZIP, or entering a 30% corporate ZIP as competitor #4), models the dentist-location-density post-acquisition, and surfaces the ADA HPI benchmark for associate employment costs at that practice size. It answers the strategic question "does this deal make sense relative to the market" with the actual market data behind it.

### System: Full Observability

The System page today shows data freshness, source coverage, completeness bars, pipeline log viewer, and manual entry forms. It is the backend-facing admin surface. The optimal version extends it in two directions.

**Observability dashboard**: every pipeline step emits structured events to `logs/pipeline_events.jsonl` via `pipeline_logger.py`. In the optimal version, those events surface as a real-time dashboard — not a log viewer but an operational monitor. Each step has a health indicator (green/amber/red) based on elapsed time since last success and expected row count range. The `MIN_ROWS_THRESHOLD` floors already in `sync_to_supabase.py` (platforms=20, pe_sponsors=10, etc.) become automated alerting thresholds: if a sync step produces fewer rows than the floor, a Discord webhook fires immediately rather than waiting for the Monday data-invariants CI job to catch it.

**Data-quality feedback loop**: a "Flag a problem" button on every KPI card, every practice row in the Warroom, every deal in the Deal Flow table. When flagged, the problem goes into a `data_quality_reports` table with the entity key, the suspect value, and an optional note. The weekly pipeline processes flags and re-researches flagged entities. Incorrect classifications feed the ML model's error correction path. Wrong deal attributions go into the `COMMENTARY_PATTERNS` prefilter in `pesp_scraper.py`. The users become co-maintainers of the data quality.

---

## 5. Reliability, Observability, and the Auditable-Number Promise

### Pipeline Reliability

The current pipeline has survived the April 2026 three-week outage and the subsequent 33-fix audit. The fixes were real and are holding. But the system still has structural fragility: the PESP scraper is dead (212 days), the GDN scraper's monthly roundup timing is not guaranteed, `target_zip` is NULL on all 2,910 deals, and 287/290 ZIP intelligence rows are synthetic placeholders. These are not bugs to fix; they are design constraints that the optimal system eliminates.

The optimal pipeline has no single points of failure for deal ingestion. Instead of relying on any one source, it has a source hierarchy: PESP → GDN → Becker's → PitchBook → manual entry. When PESP goes dark (as it did), the system does not silently stall — it automatically elevates Becker's scraper (`beckers_scraper.py`) to primary status and alerts that PESP needs manual CSV intervention. Each source has a freshness SLA (PESP: 14 days, GDN: 35 days, Becker's: 7 days) and the System page shows which sources are inside or outside their SLA with explicit color coding.

The `refresh.sh` weekly cron gains a dry-run mode that runs every Thursday, simulates the Sunday pipeline, and reports what would be scraped, what would be classified, and what the row count deltas would be — without touching any data. This catches "GDN hasn't published this month's roundup" before Sunday arrives, giving a window to manually check and adjust.

### The Auditable-Number Promise

The `data-breakdown` page (`/data-breakdown`, added April 26) is the right instinct. The optimal version takes it further: every number visible anywhere in the app is auditable from within the app.

The audit trail is not a separate page — it is a universal tooltip layer. Hovering over "4,889 GP clinics" anywhere shows a mini-popover: "Source: `SUM(zip_scores.total_gp_locations)` across 290 watched ZIPs. Last updated: 2026-04-26 16:20 UTC. Definition: address-deduped GP clinic locations, excluding specialist and non-clinical practices." Clicking "drill in" opens the data breakdown view for that specific number with the full SQL provenance.

The Warroom's signal flags show their derivation: "stealth_dso_flag: fires when entity_classification = dso_regional AND `affiliated_dso` IS NULL — this practice has corporate EIN pattern but no known DSO brand. Confidence: 72%. Last computed: 2026-04-26." The Launchpad's track score shows its component breakdown in the Snapshot tab already (per the Phase 3 score panel). The optimal version shows this for every score in every context.

---

## 6. Platform: Multi-User, Collaboration, Monetization, and Moat

### Multi-User and Auth

The current platform is a single-user system. The Warroom's lifecycle stages, reviewed tracking, pin notes, and saved searches all live in localStorage — non-portable, non-shared, per-device. This is acceptable for a solo researcher but breaks down immediately when a two-person team tries to coordinate.

The optimal platform has Supabase Auth (already a dependency) with three roles:

- **Analyst**: full read, can pin, can annotate, can flag data quality issues, can run AI research, can save searches and share them as URLs
- **Collaborator**: can see pins and annotations from other Analysts on the same account, can add to the pinboard, can comment on dossiers
- **Admin**: pipeline controls, data entry, system monitoring

The pinboard becomes a shared workspace. "I pinned Dr. Chen's practice and left a note from Monday's call" is visible to a colleague who opens the same Warroom scope. The pipeline lifecycle stages (Researching → Contacting → In dialogue → Won) map naturally to a deal pipeline that two people can work together on.

### Alerts and Notifications

The most underbuilt feature of the current system is alerting. A user who identifies 20 target practices in the Warroom and then comes back 2 weeks later to find 3 of them have changed ownership status has no way of knowing this happened without manual checking.

The optimal alert system uses Supabase Realtime (already a library dependency via the `@supabase/supabase-js` client) to push notifications when watched entities change. User subscribes to: a specific practice (notify me of any change), a ZIP (notify me of any new deal, any ownership transition, any new practice_intel), a PE fund (notify me of any new deal involving this sponsor), or a signal combination ("notify me when any practice in Naperville crosses buyability_score = 60"). Notifications arrive via email digest, Discord webhook (consistent with the existing notification infrastructure in `.github/workflows/data-invariants.yml`), or in-app notification bell.

### API and Exports

The platform has a SELECT-only SQL explorer on the Research page and CSV export on Buyability and Deals. The optimal version adds a versioned REST API:

- `GET /api/v1/practices?zip=60491&entity_classification=solo_established` — paginated practice query
- `GET /api/v1/deals?sponsor=heartland&year=2025` — deal query
- `GET /api/v1/zip-scores?state=IL` — ZIP score query
- `POST /api/v1/research/practice` — trigger AI research on a specific NPI

Rate-limited by API key. This enables downstream workflows: a dental group's EHR system could query whether a competitor practice just changed ownership, a dental school could build their own job board powered by this API's data, a PE fund could watch for emerging consolidation patterns in markets they're evaluating.

### Monetization and Moat

The platform's moat is not the technology — it is the classified, entity-resolved, AI-annotated dataset of 381,598 dental practices with 5 years of deal flow history. No commercial database has the combination of NPPES federal coverage, proprietary classification, qualitative AI research, and deal-cross-referenced practice-level intelligence. Dentagraphics charges $3,000+ for a static state-level market report that contains less information than a single `/market-intel` ZIP analysis here.

The optimal monetization recognizes this:

- **Individual Researcher** ($49/month): full Launchpad access, 10 AI research requests per month, read-only access to Warroom (no pins/lifecycle)
- **Associate/Buyer** ($149/month): full Warroom with pins and lifecycle tracking, 50 AI research requests, deal flow and market intel export
- **Team/Deal Room** ($499/month): multi-user, shared pinboard and notes, full API access, alert subscriptions, weekly intelligence briefing email
- **Enterprise/DSO** (custom): national scope, white-label option, custom data integrations, dedicated data refresh SLA

The DSO tier list in `src/lib/launchpad/dso-tiers.ts` is currently free and publicly visible. In the optimal platform, DSOs pay to maintain their listing accuracy and add recruitment links — not as advertising, but as verified factual entries. A DSO that moves from Tier 2 to Tier 1 (after improving average associate tenure) can submit evidence and the research engine re-verifies. This creates a business model aligned with quality rather than clicks.

---

## 7. The 10x Leaps: Genuinely Transformative Capabilities

### Leap 1: Acquisition Probability Before Announcement

No commercial product today predicts dental practice acquisitions before they are announced. The inputs exist in this platform: 2,861 historical deals, 381,598 practices with classification and enrichment data, ZIP-level market saturation, and a `practice_changes` log capturing pre-acquisition signals. A trained acquisition probability model would surface, for each of the 4,889 GP clinics in watched metros, a score reflecting likelihood of acquisition within 18 months. A PE associate who uses this to get ahead of a deal that hasn't been announced yet is seeing something that does not exist anywhere else. This capability is probably 3-4 months of work. The dataset to build it already exists.

### Leap 2: The New-Grad Career Outcome Network

The Launchpad scores practices for new grad fit, but it has no feedback loop. The optimal version adds a thin, voluntary career outcome layer: users who used Launchpad to evaluate a practice can report what happened (joined, accepted offer, rejected offer, practice was not what the score predicted). Over two years of dental school graduation cycles, this creates a novel dataset — the first validated connection between publicly-observable practice signals and first-job outcomes for dental graduates. ADA HPI's annual survey asks graduates about their employment status but not which specific practice they evaluated or why they chose it. This platform could collect that data. The resulting dataset has genuine academic value (publishable in JADA) and practical value (improves the scoring model's precision from heuristic to empirically-validated).

### Leap 3: DSO Competitive Intelligence for Practices Under Pressure

Right now, when a solo dentist in Oak Park sees a new DSO location open two blocks away, they have no tool to quickly understand: how aggressive is this DSO in this market? What practices in their portfolio have seen revenue changes after acquisition? What does the new associate comp structure look like? This platform already has the data to answer all three questions — `dso_locations` (92 scraped locations), `deals` (historical acquisition pace by DSO brand), `practice_intel` (AI-researched compensation signals), ADA HPI state-level data. A new page — call it `/competitive-radar` — takes a ZIP and a named DSO and returns: "Heartland Dental has opened 3 locations within 5 miles of your practice in the last 24 months. Their average associate comp in Illinois DSOs is $138k base. Practices they've acquired in Chicagoland typically maintain patient volume for 6-12 months post-acquisition before declining Google review velocity." That is a product that independent practice owners would pay for.

### Leap 4: The Dental School Partnership Pipeline

UIC College of Dentistry, Northwestern Dental (closed 2001 but the alumni network is relevant), Loyola, Midwestern, and the University of Illinois Chicago all produce graduates entering the Chicagoland market. Boston has BU, Tufts, and Harvard. These schools have residency coordinators and placement directors who guide students through their first job search with very little market data. The optimal Launchpad has a faculty-facing view: a residency director at BU Dental can query the Boston Metro Launchpad scope, see the aggregate landscape of succession-track opportunities within the school's traditional placement geography, and export a curated shortlist for their senior seminar. This is not a marketing play — it is a genuine tool for dental education. The data quality and ethical framing (ADA HPI citations, transparent sourcing, honest "data thin" caveats) make it defensible in an academic context. The school benefits, the grads benefit, the platform gains a distribution channel that reaches exactly the users it was built for.

### Leap 5: National M&A Intelligence for PE Funds and DSO CFOs

The current platform is Chicagoland-focused. Scaled nationally (all 50 states, every watched ZIP), it becomes the first independently-built, public-data-grounded national dental M&A intelligence database. Today, PE funds evaluating dental M&A opportunities pay $15,000-$50,000 for a market study from a healthcare consulting firm that is based on the same NPPES data this platform already has, interpreted by analysts who do not have access to a maintained, classified, AI-annotated version of it.

The platform's `/research` page already has PE sponsor profiles and DSO platform profiles. Scaled nationally and kept current weekly, with the ownership graph resolved, the acquisition probability model running, and the qualitative AI research layer active — this is a $25k/year enterprise subscription to a PE fund's deal team. Not because the technology is novel, but because the maintained, classified, continuously-updated national dataset assembled here does not exist commercially. The defensibility comes from the combination: federal data + classification expertise + AI research + maintained historical record. Each piece is replicable. The combination, maintained consistently over 3+ years, is not.

---

## 8. The Unified Vision

The optimal version of this platform is defined by three properties that none of its current commercial alternatives possess simultaneously:

**Complete provenance.** Every number traces to its SQL query, its upstream source, its confidence band, and its last-update timestamp. The data-breakdown page and the auditable-number tooltip layer make the platform the only dental market intelligence tool where a user can say "show me where this number comes from" and get a complete answer.

**Prediction, not just description.** The acquisition probability model, the event-triggered research refresh, and the alert layer convert the platform from a historical record into a forward-looking instrument. The user who uses it correctly is not reading last week's news — they are acting on patterns that will become next quarter's announcements.

**Depth at scale.** The combination of 381,598 NPPES rows, 2,861+ deals, AI-verified practice dossiers, and ZIP-level saturation scoring at national scope is not replicated anywhere. The moat is not a technology patent. It is three years of continuous maintenance, classification tuning, deal cross-referencing, and AI-annotated practice research that creates a dataset whose accuracy and granularity improve the longer it runs.

This is not a feature list. It is the result of taking what is already real in this codebase — the entity classification system, the Warroom command surface, the Launchpad scoring engine, the qualitative AI research layer, the deal flow history — and asking what each of them becomes when the constraints of single-user, two-metro, $5-weekly-budget are removed.

The platform already has the bones. The optimal version is those bones, fully realized.

---

*Report written for /warroom multi-agent vision session, May 2026.*
*Data sourced from: `/Users/suleman/dental-pe-tracker/CLAUDE.md`, `CLAUDE_ARCHIVE.md`, `FIRST_JOB_FINDER_PLAN.md`, `AUDIT_REPORT_2026-05-01.md`, `dental-pe-nextjs/CLAUDE.md`, and direct source inspection of `scrapers/research_engine.py`, `src/lib/warroom/ranking.ts`, `src/lib/warroom/intent.ts`, `src/app/warroom/_components/dossier-drawer.tsx`, and related files.*
