# Comprehensive Audit Sweep — {{TARGET_DATE}}

You are running in **GitHub Actions headless mode**. No interactive user. Be terse, decisive, finish in a single pass. No clarifying questions; pick the most reasonable interpretation and proceed.

## Read This First — Why This Session Exists

The dental PE tracker app — the one live on Vercel — has been through extensive feature additions, bug fixes, feature fixes, and updates since day one. From the start, the owner has been skeptical of every component, every module, every data point, every scraper, every page, every feature, every tool and sub-tool, every claim of data accuracy, and every claim of real-time updates. What was originally designed with intent has become a Frankenstein.

Right now nobody can confidently say:
- What works vs. what doesn't
- What features even exist
- What data needs fixing
- What scrapers need fixing
- Why the live URL keeps showing stale data even after extensive debugging

**Persistent symptoms to investigate:**
- The app keeps falling back on the excuse "GDN hasn't posted the latest deal roundup yet." That excuse cannot account for the staleness, because there are many other deal sources that should be filling the gap and clearly aren't.
- All Chicagoland practice NPI data shows stale state, even after extensive debugging.
- The newer features — War Room and First Job Search (Launchpad) — are deeply questionable. No confidence they actually work end-to-end.
- The maps, which are supposed to be the god-mode visualization layer, look suspect.
- The dossiers and ZIP-level analyses are almost certainly stuffed with half-assed Haiku hallucinations rather than verifiable, source-attributed data.

The chief concern is the data flow itself: what should be feeding in real-time, what should be auto-updating via scrapers, what should be auto-running across all tracked practices (classifiers/declassifiers), and how all of that should compose into a backend intelligent enough to give a god-mode view of Chicagoland practices and deal flow without manual input.

## What This Session Is — and What It Is NOT

This is an **audit**. Not a debug session. Not a fix session. **No code changes. No edits. No commits. No "while I'm here, let me clean this up." No silent fallbacks. No "this looks fine."**

The audit is the precondition for targeted debugging — without it, every fix is a guess.

## Hard Rules (Non-Negotiable)

1. **No code changes.** No edits. No commits. No "tiny tweak." No mutating commands. Audit only. The single output file is `{{REPORT_PATH}}`.
2. **No assumptions.** If you cannot verify something works, mark it `unknown — verification needed` and describe exactly how to verify. Do not guess. Do not infer.
3. **Read every line in scope.** Skim is forbidden. Spot-check is forbidden. If a module is in scope, every line is read.
4. **Cite file:line for every claim.** No vague "seems broken" or "looks correct." Evidence is `file:line`, query output + timestamp, log line + run ID, or HTTP response + URL.
5. **Flag every LLM-generated artifact baked into stored data.** Call out Haiku output by exact location and field. Treat any LLM-written content as suspect until proven otherwise by source attribution.
6. **Report unknowns explicitly.** A feature you cannot trace is itself a finding, not a thing to skip.
7. **No pre-compromise.** Do not soften findings, do not "start small," do not propose a phased subset of the audit. The whole thing gets audited. Match the ambition.
8. **No time estimates.** Describe the work, not how long it takes.
9. **Stay within CI constraints.** `launchctl` unavailable on Linux runner — document as a known gap, don't try to invoke it. Use Supabase REST + WebFetch + git log as substitutes.
10. **One pass.** Do not loop. Do not schedule follow-ups. Stop when the report is written.

## Scope — Audit Targets (None Optional)

### 1. Codebase Inventory
- Every file in the repo, organized by directory and domain.
- Every component, page, route, API handler, edge function, background job, cron, queue worker, webhook.
- Every script: scrapers, enrichment jobs, classifiers/declassifiers, batch processors, ETL, one-off CLI tools.
- Every config file, env var, secret reference, build/deploy hook, Vercel project setting referenced in code.
- Read `CLAUDE.md` end-to-end and every doc in `docs/` end-to-end. Cross-reference docs vs. code.

### 2. Feature Inventory
For every user-visible feature, produce a row:
- Name and where it lives in code
- Claimed behavior (per docs/commits/code intent)
- Actual behavior (per close code reading)
- Data dependencies (reads from / writes to)
- Wiring (live data vs. stub/mock/fixture vs. hardcoded)
- Reachability (linked from where, or orphaned)
- State (works / partial / broken / unknown / orphaned / dead code)

Must explicitly cover by name: **War Room, First Job Search (Launchpad), every map view, every dossier surface, every ZIP-level analysis, every Chicagoland practice view, every deal-flow view, every dashboard card, every filter, every search.**

### 3. Inbound Data Flow Audit
For every inbound data source (GDN, NPPES/NPI, PESP, PitchBook, Data Axle, ADSO, ADA HPI, others):
- What is it
- Where it enters the app (file:line)
- What ingestion process runs (script/job/function)
- On what schedule (cron expression, trigger, manual)
- Last known successful run (if observable)
- Where the output lands
- What's downstream

### 4. Interpretation, Analysis, Merge & Scoring Audit
For every transformation step between raw input and stored/displayed data:
- Interpretation — parsing, normalization, field mapping
- Analysis — every computed metric, signal, classification
- Merge / dedup — conflict resolution, idempotency, can it corrupt state on re-run
- Scoring — every score (lead, deal-fit, buyability, opportunity), algorithm, inputs, output
- Classifiers / declassifiers — what triggers them, what they write
- Dossier building — for every section: sourced+attributed vs. LLM-generated free text. Flag every Haiku-written section that lacks verifiable source attribution.

### 5. Enriched Data Propagation Audit
End-to-end trace of every enriched record: raw ingestion → enrichment → storage → read path → UI render. For each pipeline:
- Where it's supposed to land in the UI
- Where it actually lands (or where the chain breaks)
- Every silent failure, swallowed error, fallback
- Every cache layer (ISR/SSR/CSR boundary, revalidation rule) that could be serving stale data

### 6. Real-Time / Background Update Audit
- Every scraper: source, cadence, last run, success/failure history, output destination
- Every cron / scheduled function / edge function / webhook / queue worker
- Every "should auto-update" pathway (NPI updates, deal roundups, classification, dossier refresh, map data refresh)
- Verify scheduled work is *actually* scheduled, *actually* fires, and reaches surfaces

### 7. Frontend — Next.js (`https://dental-pe-nextjs.vercel.app`)
For each page (`/`, `/launchpad`, `/warroom`, `/deal-flow`, `/market-intel`, `/buyability`, `/job-market`, `/research`, `/intelligence`, `/system`):
1. **Render check** — WebFetch the live URL. HTTP 200? Renders content? KPIs populated?
2. **Data freshness** — most-recent timestamp visible in UI vs. Supabase `MAX(updated_at)`. Stale in DB or in cache?
3. **Feature completeness** — every tab, KPI card, chart, map, table, drawer, filter, signal flag, tooltip described in `CLAUDE.md` for that page. exists / missing / broken / empty.
4. **Cross-page consistency** — Home "consolidated" KPI vs. Market Intel; Job Market vs. Market Intel Chicagoland totals; Warroom Sitrep vs. Market Intel.
5. **URL filter sync** — load a filtered URL. Filters applied?

**Special scrutiny:**
- **Warroom** — every mode (Hunt/Investigate), every lens, every scope (chicagoland + 7 subzones + 3 saved). Are the 8 practice + 1 ZIP signal flags computed from real signals or hardcoded? Does `getSitrepBundle` return live data? Does Living Map color polygons by lens correctly? Does dossier drawer surface real intel?
- **Launchpad** — 20-signal catalog evaluation, 3 tracks, 5 tiers, 16-DSO curated tier list, 5-tab dossier. Spot-check 3 ranked practices: signal evaluations accurate against underlying NPI? Is `dso-tiers.ts` hardcoded fiction or sourced research?
- **Maps** (Warroom Living, Job Market Density hex+dots, Market Intel Consolidation, Deal Flow State Choropleth) — for each: real Supabase data or sample/cached/fake/empty? Verify point counts vs. `SELECT COUNT(*)`.
- **Intelligence** — surfaces actual `practice_intel` rows? Confidence/quality badges match `verification_quality`?
- **System** — Pipeline Log Viewer shows recent events? Data Coverage panel shows all sources (incl. ADSO + ADA HPI per April 2026 fix)?
- **Home** — 6 KPI cards live? Activity feed (from `practice_changes`) actually updates? Freshness bar reflects real freshness?

### 8. Frontend — Streamlit (Legacy, `https://suleman7-pe.streamlit.app`)
- App still up?
- Each of the 6 pages renders?
- Gzipped DB decompresses correctly?
- Anything diverged dangerously from Next.js (e.g., different consolidation %)?

### 9. Deployment & Live URL Behavior
- Vercel: last 10 deployments — successful vs. failed. Current production build hash + timestamp.
- Streamlit Cloud: last deploy timestamp, current state.
- Supabase: connection limits, free-tier pause status, current DB size, GitHub Actions keep-alive workflow active and succeeding?
- Caching layers — list every cache between source-of-truth and rendered DOM:
  - SQLite → Supabase sync interval
  - Supabase Postgres
  - Next.js Server Component fetch
  - React Query (5min stale, 30min gc)
  - Vercel ISR / SSG / Edge cache
  - Browser HTTP cache
- Identify which cache is responsible for any stale-data complaint.

### 10. Documentation vs. Reality (Documentation Drift)
- For every claim in `CLAUDE.md` and any other doc: does the code actually support that claim? Mark `accurate / partially accurate / stale / wrong`.
- Every "do not regress" claim, every "fixed in March/April 2026" claim, every architectural claim, every row-count claim — verify and list discrepancies.
- `SCRAPER_AUDIT_STATUS.md` — current state vs. claims.
- `scrapers/dossier_batch/` — files described actually exist? Current with what's running?
- Any resume-checkpoint or phase-progress docs — accurate?
- List every feature/capability mentioned in docs with no corresponding live code path.
- List every live code path with no documentation.
- Flag any "supposed to" language in docs that the code doesn't implement.

### 11. Specific Symptom Investigation (Diagnosis Only — No Fixes)
- **GDN excuse:** enumerate every other deal source, what each contributes, why none filling the gap (with file:line). Manually identify 8–12 PE dental deals announced in the last 60 days from public web sources; check whether each appears in the `deals` table.
- **Stale Chicagoland NPI data:** trace NPI source → ingestion job → store → read path → UI. Find the freeze point.
- **Maps look suspect:** verify data source, freshness fields, transformation pipeline, rendering logic.
- **Dossiers / ZIP analyses likely hallucinated:** for each surface, classify every section as `sourced+attributed / sourced+unattributed / LLM-generated (Haiku) / LLM-generated (other) / unknown`. List every hallucination-risk surface.
- **War Room and Launchpad:** end-to-end trace. Do they actually read live data? Where? Failure modes? Wired to anything real?

### 12. The Owner's Six Specific Pain Points (Yes/No/Partial + Evidence)
1. **"Why is data stale on the live URL?"** — Trace one specific stale data point end-to-end: source → scraper → SQLite → sync → Supabase → Next.js fetch → React Query → rendered DOM. Identify the exact layer.
2. **"GDN has no recent deals — why aren't other sources filling the gap?"** — Falsify or confirm with the manual deal-discovery from §11.
3. **"NPI / Chicagoland practice changes look stale even after extensive debugging."** — When was NPPES last imported? When was `practice_changes` last appended? Most recent change row? Real-time updates actually happening?
4. **"Are the maps real or fake?"** — For each Mapbox map, render and verify points/polygons match DB row counts and coordinates.
5. **"Are the dossiers full of Haiku hallucinations?"** — 5-dossier deep spot-check against cited URLs.
6. **"Is the intelligent backend actually running automatically?"** — Show cron run history. Last 10 runs of: `weekly_research.py`, `sync_to_supabase.py`, NPPES monthly, cron-triggered `refresh.sh`.

## Methodology

- **Read code.** Open every file you reference. No speculation from filenames.
- **Run queries.** Supabase REST API for Postgres; if `data/dental_pe_tracker.db.gz` was decompressed, you can `sqlite3` it. Capture outputs verbatim.
- **Check logs.** `logs/pipeline_events.jsonl`, GitHub Actions workflow runs, any other observable log streams.
- **Render the live URL.** WebFetch each Vercel route; verify rendered data vs. Supabase.
- **Cross-reference claims.** When `CLAUDE.md` says "X is fixed," locate the commit, verify the code is present, verify the test or evidence.
- **Time-box per item.** If verification would take more than ~20 minutes for any single item, mark it `unknown — needs hands-on investigation` and explain precisely what additional access or action would resolve it.

## Deliverable — Single Consolidated Audit Report

Save to `{{REPORT_PATH}}` (which the workflow expects to also be committed at the path `AUDIT_REPORT_{{TARGET_DATE}}.md` at the repo root — write it there too).

**Required sections (do not skip):**
1. **Executive Summary** (≤1 page) — top 10 verified-broken, top 10 verified-stale, top 10 unknowns. One-line each.
2. **Codebase Map** — every file/module by domain.
3. **Feature Inventory Table** — schema from §2, one row per feature.
4. **Pipeline Health Matrix** — scraper-by-scraper: last-run / rows-last-30d / coverage-gap / status / suspected-cause.
5. **Scheduled Job Table** — name / schedule / last successful run / output / status / evidence.
6. **Database Integrity** — SQLite-vs-Supabase row-count parity, freshness-by-table, orphan/duplicate counts.
7. **Data Flow Diagrams** — one per major pipeline (ingestion → enrichment → store → UI), with break points marked.
8. **Frontend Audit** — page-by-page, feature-by-feature health matrix.
9. **Map Reality Check** — one section per map, with render proof and row-count verification.
10. **Hallucination Audit** — every dossier and ZIP section classified; 5-dossier deep spot-check against cited URLs.
11. **Documentation Drift Log** — every CLAUDE.md claim vs. reality.
12. **Symptom Diagnosis** — for each symptom in §11 of scope, root-cause hypothesis with file:line evidence.
13. **Pain Point Resolutions** — explicit yes/no/partial answers to all six owner questions in §12.
14. **Suspected Root Causes** — hypotheses ranked confidence (high/medium/low) with reasoning.
15. **Prioritized Debug Backlog** — bugs ordered by blast radius. Each item specific enough to feed directly into the next debug session. **This is the audit's most valuable artifact.** Tag each item with severity: `P0` (critical, data integrity / user trust on fire) / `P1` (high, clear regression) / `P2` (medium, hygiene with user impact) / `P3` (low, nice-to-have).

For every finding: file paths with line numbers, query outputs, timestamps, URLs. No bare claims.

## Success Criteria

When this audit is complete, the report should let the owner:
1. Name every feature that exists and know its true state.
2. Understand every data flow end-to-end with no black boxes.
3. Know exactly which scrapers/jobs are running and which aren't, with evidence.
4. Know exactly which dossier/ZIP content is real vs. hallucinated.
5. Hold a ranked, evidence-backed debug backlog that drives the next session.
6. Trust the audit — meaning never need to re-audit any of this scope after this is done.

## What This Audit Is NOT

- Not a fix session. Don't touch code. Don't run mutating commands.
- Not a refactor opportunity. Don't suggest cleanups beyond what's needed for clarity.
- Not an architecture critique unless architecture is the verified root cause.
- Not a feature wishlist. Audit what exists, not what's missing.
- Not a polish job on `CLAUDE.md`. Doc drift goes in §11 of the report — don't edit the doc.

When the report is written to `{{REPORT_PATH}}` AND copied/written to `AUDIT_REPORT_{{TARGET_DATE}}.md` at repo root, your job is done. Exit cleanly.
