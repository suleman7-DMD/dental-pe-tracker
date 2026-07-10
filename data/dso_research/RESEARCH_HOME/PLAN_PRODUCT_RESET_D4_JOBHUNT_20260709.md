# PRODUCT RESET PLAN — D4 Chicagoland Associate Job Hunt CRM + Broad Directory
**Author:** Fable (pivot session) · 2026-07-09 · Status: EXECUTION CONTRACT (supersedes the old full-coverage mission as *product goal*; all data-safety law unchanged)
**Inputs:** 3 audit fleets (17 agents, ~1.3M tokens: foundation/pagination+counts+state, route-rot+D4-fields+scaffolding+fake-precision, bloat+funnel-quantification+design-panel), `HANDOFF_P0_SESSION_TO_PIVOT_20260709.md`, Codex salvage estimate (keep 60-70% / simplify 20-30% / hide 10-20%), truth charter `SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md` §2 (still binding).
**Products:** **A. Broad Chicagoland Directory** (all 4,439 shown honestly) + **B. Verified D4 Job Hunt CRM** (THE product: top 300 → top 100 → top 50 outreach-ready + outreach tracker).
**Standing law (unchanged):** ownership-truth.ts is the only ownership interpreter; census writes only via consolidate_census.py two-step; human gates on all DB writes / syncs / spend; detector floor CI guards untouched; MA parked; never DELETE from practices; the original full-coverage named-owner vision is **NOT solved — it is retired as a goal** (bloat verdict: kill; est. $250k+/yr to actually do).

---

## ⚠️ URGENT PRE-SUNDAY GATE (before 2026-07-12 08:00 weekly refresh)

`refresh.sh` step [11/11] full sync runs `practice_locations` full_replace → **`TRUNCATE ... CASCADE` wipes `job_hunt_verification` (48 rows) via its FK** (sync_to_supabase.py:158; the "no FK deps" comment there is stale). The table is not ORM-mapped, not in any sync, has no CI guard, no auto-reimport. Recovery exists (seed + `import_job_hunt_verification.py --allow-db-write`) but nothing triggers it.

**Fix (P0.0, needs user go — pick one before Sunday):**
1. **Recommended:** patch the sync so any `practice_locations` full_replace immediately re-runs the JHV seed import + `--verify`, and add CI guard `JOB_HUNT expect_min=48` to `check_data_invariants.py`. Fix the stale comment.
2. Alternative: `launchctl unload` the weekly agent this week (user action), patch at leisure.
3. Fallback: accept the wipe, re-import Monday (safe ONLY while live == seed; any un-exported new row would be lost).

Second stranded queue: `practice_manual_corrections` (**7 rows live, reconciled 2026-07-09: 6 queued edge-QA + 1 rejected health_check** — evidence `data/dso_research/correction_queue_reconciliation_20260709.json`; the SQLite mirror holds only the 6 QA rows and is NOT the system of record) is Supabase-written by the app, has no pull/export/apply path and already drifted once. **Never add it to full_replace sync** (that would overwrite the live queue) — it needs a Supabase→seed export + the promised-but-missing `apply_manual_corrections.py`.

---

## 1. CURRENT TRUTH MATRIX (14 fields, IL GP scope = 4,439; all counts machine-queried 2026-07-09)

| # | Field | Coverage | Source | Trust level | Directory-grade? | Job-hunt-grade? |
|---|---|---|---|---|---|---|
| 1 | Practice name | 4,439 registry names; **38** website-confirmed public names | NPPES / Data-Axle; JHV `public_practice_name` | Registry only → Website-verified (38) | ✅ with "registry name" label | Only website-verified names for outreach (verified-name precedence already shipped) |
| 2 | Address | 4,439 (100%) | NPPES registry | Registry only; 47 cross-checked vs live site | ✅ | ✅ with label; cross-check on outreach |
| 3 | Phone | 4,214 (94.9%) | NPPES/DA registry | Registry only; **0 structurally website-verified** (JHV has NO phone column; ~14-17 prose mentions) | ✅ labeled | ⚠️ Call-verify before relying; add `verified_phone` column (Wave 1) |
| 4 | Website | 1,868 on `practice_locations`; ~3,027 locations have some URL via intel; **47 liveness-verified** | Mixed: DA / intel / Lane A / JHV | Registry only → Website-verified (47) | ✅ labeled "on file, liveness unchecked" | Verified rows only; false-website-match kill rule mandatory (proven failure class: ofsmiles.com, czfamilydental.com) |
| 5 | Ownership category | **3,180 (71.64%)** hand-reviewed tiers + 477 undetermined + 178 held visible; banked +488 awaiting write | Census `ownership_tier` + evidence URLs | **Ownership-reviewed — the strongest field in the platform** | ✅ | ✅ (T2/T3 = best associate pre-filter) |
| 6 | True named owner/operator | **26 (0.56%)** website-stated; 686 owner_identity strings in banked file (ledger-only, not in DB) | JHV `owner_operator_stated` | Website-verified (26) else Missing | ❌ never implied per-office | Cohort-only via waves; NEVER promised for all 4,439 (goal killed) |
| 7 | Current doctors (from website) | **35 (0.79%)** rosters | JHV `doctors` jsonb | Website-verified | ❌ (show "not checked") | THE #1 gap → Waves 1-3 primary target |
| 8 | Provider count | buckets known for all: 1→2,485 · 2+→1,364 · null/0→590 | NPPES roster on `practice_locations.provider_count` | Registry only (may include departed associates) | ✅ labeled | ✅ as pre-filter only (2+ = associate signal) |
| 9 | Employee count | ~54.8% | Data-Axle | **Commercial estimate** — never fact | ✅ labeled "estimate" | Triage only; never in an uncapped lane |
| 10 | Revenue | ~54.6% | Data-Axle | Commercial estimate | ✅ labeled | Triage only |
| 11 | Hiring/careers page | **5 verified**; ~103 locations AI-flagged `hiring_active` (lead list, 43 in profile — every one needs re-verify) | JHV / practice_intel | Website-verified (5) vs AI-cited | ❌ | Verified only; AI flags = queue fuel |
| 12 | Dentist openings | **3 locations** structured (0.07%) | JHV `openings` | Website-verified | ❌ | Wave target; decays fastest (60d TTL) |
| 13 | Reviews/reputation | 275 locations with 50+ reviews @4.0+ (118 in profile) | practice_intel google metrics (source-URL-gated) | AI-cited (label; never "verified") | ✅ labeled | ✅ as ranking signal only |
| 14 | DSO/PE/network status | T4+T5 **179 locations**; pe_backed 118; 527 deals; network rulings ratified (DECISIONS_PM_20260709) | Census + PM rulings + deals (pe_deal_context) | Ownership-reviewed / PE-deal-context | ✅ | ✅ (brand-level careers checks = Wave 4) |

**The inversion that defines the pivot:** verification quality is inverted vs. D4 need — the fields a job hunter acts on (doctors, owner, hiring, openings: all <1%) are the emptiest; the fields we perfected (ownership category: 71.6%) are done. The census demotes from *product* to *the funnel's first filter*. Fleet-verified: **95.7% of the universe has been touched by research (4,250/4,439) — but at ownership grade, not job-hunt grade.**

## 2. ROUTE TRIAGE

Codex estimate vs. fleet-3 independent 55-asset inventory: keep-core 13 + repurpose 19 = 58% keep · demote-context 11 = 20% · freeze 9 + kill 4 = 24% hide/kill. **The two agree; the split below is ratified.**

| Route (sidebar label) | Verdict | What changes |
|---|---|---|
| `/` Home | **KEEP+SIMPLIFY** → Mission Control | Funnel bar (live-computed stages) + next-action queue + wave status. Fix: `census.ts:113` undeterminedReviewed structurally 0 (never selects `census_review_status` — 655 researched rows silently shown as "Not Started", charter violation); relabel "Verified"→"Reviewed" (hero badge + census card); delete dead detector plumbing (unused consolidatedPct/independentPct in HomeSummary) |
| `/job-market` Directory | **KEEP** (Product A) | Add trust-lane column + funnel-stage filter + "Add to pool". Fix: label Data-Axle KPIs "commercial estimate"; label Acquisition-Lead filter caption as detector-derived; per-fact TrustSourceTags in the drawer (mirror /practice pattern) |
| `/launchpad` Job Hunt | **KEEP — THE product** | Six trust lanes replace 0-100 track scores (§5). Fix HIGH-severity AI poisoning: `ask` + `zip-mood` routes inject detector corporate_share_pct as "CONFIRMED/verified floor" into Claude prompts → rewire to five census buckets; kill hardcoded $135k-175k "MGMA" comp band (no MGMA data exists in repo); `verification_quality ?? "verified"` default → "unchecked"; kill `dso-tiers.ts` curated list (superseded by census + PM rulings) |
| `/practice/[locationId]` | **KEEP — model surface** (zero audit violations) | Add Outreach tab. Fix: `use-practice-card.tsx:18-58` hand-rolled tier switch → import ownership-truth.ts (contract law: never reimplement) |
| `/market-intel` Ownership | **SIMPLIFY→context** (page passes audit clean) | Five-bucket truth bar stays as the control-type legend; move to Context nav section |
| `/buyability` Acquisition Scout | **SIMPLIFY→reframe: "Equity Path"** | Retiring dentist-owned offices = associate-now-buy-in-later — the acquisition data is NOT bloat, its investor framing is. Fix: Confidence star column (detector match-confidence, falls back to buyability_score/25 — two category errors) → replace with census confidence; "Dead Ends" census/detector blend → split visually; label Classification column "older automated" |
| `/warroom` Review Desk | **HIDE→ADMIN** | Highest detector-as-truth density in app. Keep: queues (held 178 / undetermined 477 / corrections 6 / stale rechecks / wave board). Kill as user-surface: Hunt-mode 0-100 ranking (awards entity_classification ownership points while fetched census columns sit ignored — the single largest rule-4+9 violation), sitrep "Confirmed Corporate" detector KPIs, briefing corporate-floor lines, dossier detector-identity chips + MarketTab corporate share |
| `/system` | **ADMIN-ONLY keep** | Fix hardcoded GLOBAL_PRACTICE_NPI_COUNT freshness constants (silent-drift risk); add JHV/outreach/wave import status |
| `/data-breakdown` Methodology | **KEEP** | Add funnel-stage provenance (rules verbatim from code); legacy detector exhibit stays confined here — the only legal home |
| `/deal-flow` PE Deals | **HIDE→context** | Shrink to brand-level PE lookup ("your interviewer's parent was acquired by X in 2025") on practice/employer panels; freeze deal scrapers (P7) |
| `/research` Evidence | **SIMPLIFY** | Rebuild as **Employer Profiles** (DSO/group "who would I work for": IL footprint, PE-backing, reviews); SQL explorer → /system |
| `/intelligence` Research Notes | **MERGE into practice page** | Dossiers render where used; fix VerificationBadge "Verified" (AI self-assessment may never grant the reserved word); intel-audit drops non-canon "high" |
| Streamlit app + gzip-DB git push | **KILL** (freeze, remove from pipeline) | Largest pure maintenance win |
| Scrapers PESP/GDN/Beckers/ADSO/ADA-HPI + PitchBook importer + hidden-DSO detector fleet | **FREEZE-ARCHIVE / KILL(PitchBook)** | Deals frozen at 527 "as of 2026-07"; monthly NPPES refresh KEPT (real-office ground truth); Sunday refresh skeleton kept for sync/invariants only |

## 3. NEW APP SHAPE (8 surfaces)

1. **Dashboard** (`/`) — funnel bar S0→S5 (every count live from one module), next-action queue (outreach `next_action_date`), stale-recheck alerts, wave status.
2. **Opportunity List** (`/launchpad`) — the six trust lanes × ranked pool; every card: lane label + why + `missing[]` verbatim; DSO-employment toggle adds the 179 T4/T5 lane.
3. **Verified Shortlist** — S3 view (fresh JHV rows, rank ≥4): rosters, owner statements, hiring links, evidence trail; the "trust these 50" surface.
4. **Practice Detail** (`/practice/[locationId]`) — the CRM record: ownership+evidence / job-hunt intel / network+PE context / outreach tab / correction button.
5. **Outreach Tracker** — NEW `job_hunt_outreach` table (clone JHV durability pattern: DDL + seed + importer `--verify/--export`): status enum not_contacted→emailed→called→replied→interview→rejected→offer, notes, next_action(+date), contact log. Replaces per-device localStorage pins (one-time migration). Board on Job Hunt + panel on practice page.
6. **Directory** (`/job-market`) — Product A: all 4,439, honest columns only (allowed claims: location exists; ownership category if reviewed; researched-no-answer; labeled website/phone/staffing. NOT allowed: implied named owner, implied verified doctors without a check record, scores outranking trust states).
7. **Map** — living-map (already census-wired) as a lens inside Directory/Job Hunt, colored by trust lane, not by score.
8. **Admin/Data Health** — System + Review Desk queues + Methodology.

**Design verdict (3-way panel):** adopt **FunnelWorks' spine** (single `src/lib/census/funnel.ts` stage-derivation module — the only way counts can never diverge across pages; F27-style vitest source-walk to ban derivation elsewhere) + **Shortlist's surface minimalism** (8 surfaces, everything else folds) + **EDGE's leverage lanes** (Equity-Path reframe of /buyability; DSO negotiation context from 527 deals; outreach-table durability pattern). All three independently concluded ~80% of the MVP already exists.

## 4. TRUST MODEL (exact labels; extend `SOURCE_CLASSES` in ownership-truth.ts additively, never rename)

| Label | Backed by | UI may say | UI may NOT say |
|---|---|---|---|
| **Website-verified** | fresh JHV row (≤90d) | "Site lists Drs. Patel, Kim (checked 2026-07-08)" + evidence links | anything beyond what the cited page states |
| **Ownership-reviewed** | `ownership_tier` + evidence URLs | "Dentist-owned group (hand-reviewed, high confidence)" | the word "verified" (reserved); "DSO-affiliated" for T2/T3 (labeling law) |
| **Registry only** | NPPES/state registry | "Phone on file with federal registry" | that it is current or confirmed |
| **Commercial estimate** | Data-Axle | "~8 employees (commercial estimate)" | any fact framing; may never feed an uncapped lane |
| **Researched, no answer** | `census_review_status` held/undetermined; JHV `no_usable_website` | "Researched — no public answer found" (an honest, visible state) | "unknown/not started" (it WAS researched) |
| **Conflict** | JHV `ownership_conflict`; queued corrections | red chip + link to dispute | anything outreach-actionable until resolved |
| **Missing** | no record | "Not yet researched" | any inferred value |
| **Stale** | last check >90d (60d for hiring/openings) | prior value + "last checked N days ago — recheck queued" | present-tense claims |

**The word "verified" means exactly one thing: a job_hunt_verification-backed website check.** Current violations to purge: Home hero badge + census card, /intelligence VerificationBadge, launchpad dossier `?? "verified"` default, intel-audit accepting "high", launchpad AI-prompt "verified minimum" framing.

## 5. SCORING RESET — trust lane ALWAYS outranks score

**Kill:** warroom 0-100 composite + hot/warm/cool/cold tiers (detector ownership points, −30/−40 penalties, census columns fetched-but-ignored); launchpad 0-100 track scores + 20-signal TRACK_MULTIPLIERS; Confidence stars; MGMA comp band; "acquisition-ready = buyability≥50" KPIs. **Demote to admin/methodology:** buyability_score, opportunity_score, market_type (all labeled "older automated score"). **Keep:** capped explainable sub-signals inside a lane (job-lane.ts caps + `laneReason`/`capReason`/`missing[]` already shipped); Data-Axle signals only when enrichment-checked and never in the uncapped lane; `recent_acquisition_warning` reworded to "change-log signal — not an ownership adjudication" (tier always wins).

Six lanes (today's grounded counts):

| Lane | Rule | Today |
|---|---|---|
| **Outreach-ready** | fresh JHV roster_verified/hiring_page_found + ownership-reviewed (T1-T3, or T4/T5 with DSO toggle) + no conflict | **31** |
| **Good lead — verify details** | ownership-reviewed + website + strong signal (2+ providers / hiring flag / 50+ reviews@4.0+), no fresh JHV row — or JHV row with gaps | head of **149** (→694 pool) |
| **Research first** | D4 profile match, missing website/signals; incl. 300 untiered-with-banked-research | ~**1,773** pool remainder |
| **Call required** | JHV call_required; no-usable-website rows with registry phone (after 17%-false-negative adversarial recheck) | 2 + ~10 |
| **Do not trust yet** | conflict rows, queued corrections, stale >90d, synthetic-suspect | 5 JHV + 6 queued corrections (7 total incl. 1 rejected; reconciliation 20260709) |
| **Not job-relevant** | T6 (59), T4/T5 with toggle off (179), closed/duplicate/da_unverified, MA (parked) | — |

**The 43-vs-47 decision (handoff §2), ratified here:** keep census-first precedence — a website-checked office with no reviewed ownership tier can NEVER be Outreach-ready; it renders as **Good lead — verify details** with `missing: ["ownership answer"]` (not buried in needs_research). The 4 affected rows all have banked recovery research; P5's write dissolves most of the discrepancy.

## 6. VERIFICATION FACTORY

**Per-practice capture (JHV schema, per row):** public name · legal/census name (census layer + authorized_official — cross-ref only) · address match (**ADD `address_match` boolean** — currently prose-only) · website status (5-enum) · website phone (**ADD `verified_phone`** — currently no column) · current doctors (jsonb) · owner/operator stated · hiring/careers page + URL · dentist openings (jsonb) · evidence URLs (≥1 per positive claim) · last_checked_at · checked_by · gaps remaining (derived = job-lane `missing[]`, not stored).

**Pipeline (per wave):** queue builder (next-N by lane rank, skip existing location_ids, attach Lane A prefill — 990 banked website rows cover ~22% of universe) → research fleet or Batch-API run (clone Lane A workflow with JHV output contract, or dossier_batch 4-layer gate) → **result→seed converter** (missing today; model on `_merge_lane_a_intel_20260702.py` URL gate) with two hard rules: **false-website-match kill** (page must corroborate THIS address or phone — never name alone; proven failure class) and **successor-practice rule** (Kulig pattern → ownership_conflict, not no_usable_website) → `import_job_hunt_verification.py` validate → `--allow-db-write` (user gate) → `--verify` (live==seed hard gate) → `--export` + commit → CI `JOB_HUNT expect_min` ratchet → **edge-bucket QA gate** (codified, per wave: 100% adversarial recheck of no_usable_website [measured 17% bucket error], manual review of every ownership_conflict, 10% roster sample vs cited URLs, empty-evidence audit) → WaveRecord logged (the 48 rows = wave-0).

Ownership conflicts feed `practice_manual_corrections` → Review Desk → the missing `apply_manual_corrections.py` (P0 builds it); applying to census columns stays consolidate-gated — user notes can never silently mutate hand-verified census.

## 7. COVERAGE PLAN — WAVES 0-5 (grounded funnel: 4,439 → 1,773 profile → 694 (2+prov∩website) → 149 (hiring∪reviews — the ~150 exists TODAY with zero new research) → 48 verified → 31 outreach-grade · parallel DSO lane 179)

| Wave | Records | Agent cost | Time | Human QA | Output tables | App-visible change |
|---|---|---|---|---|---|---|
| **0 — Infrastructure** (P0 remainder; §Sunday gate first) | 0 | $0 | 1-2 sessions | Gates: sync patch go, launchd decision | CI guards (JOB_HUNT≥48, DEALS=527, queue-accounting, corrections floor); `funnel.ts`; corrections export + apply script; sync CASCADE protection | Counts single-sourced; Home undetermined card real; JHV survives Sunday |
| **1 — Top 50** | recheck 48 + ~15 net-new from the 149 | ~$1-2 batch (or 1 fleet evening, $0 API) | 2-3 days | Edge-bucket gate + user write-gate | JHV ≥50 fresh; `verified_phone` + `address_match` cols; WaveRecord v1 | Verified Shortlist fully populated; Outreach-ready ≈35-40 |
| **2 — Top 300** | ~250 net-new from ranked 694 (prefill: 407 have dossiers, 990 have Lane A websites) | ~$3-6 all-in | ~1 week batch / 2 fleet evenings | Same gate per batch of ~100-150 (tested cohort size) | JHV ≈300 | Every top-300 row shows Website-verified or Researched-no-answer — no blanks in Product B's core |
| **3 — 251 busy independents** | remainder of profile∩3+providers (553) not yet covered | ~$3-5 | ~1 week | Same | JHV ≈550 | Opportunity List complete through the busy-independent tier |
| **4 — Groups/DSOs/networks** | 179 T4/T5 via ~25-30 **brand-level** careers checks + employer profiles (platforms table) + network_id normalization | ~$1-2 | 2-3 days | PM network rulings only (R4: one-network-one-decision) | employer_profiles view; JHV brand rows | DSO Associate toggle lane usable; negotiation context panels |
| **5 — The rest (~3,000)** | **ONLY if useful — explicitly unscheduled.** Full 4,439 ≈ $45-90 batch | — | — | — | — | Documented ceiling, not a commitment. The full-coverage vision stays retired |

Independent of waves: **P5 census recovery write** (banked 1,259: 488 classified/766 undetermined/5 needs-verify, post-PM-rulings + post-QA) moves coverage 3,180 → ~3,668/4,439 = **82.6%** and re-tiers the 300 untiered profile rows — the single highest-ROI data move, all 13 gates documented (validate-only → backup+md5 → --allow-db-write → SQLite verify → both sync legs → read-back → CI/invariant updates in the same commit incl. `EXPECTED_OWNERSHIP_REVIEWED` in check_fetch_invariants.mjs). Also free: re-score the 1,133 profile dossiers to light up the 100%-empty `new_grad_friendly_score`/`mentorship_signals` columns (local pass, $0).

## 8. DATA DECAY POLICY

- **Current** = checked ≤90 days (aligned to shipped `STALE_AFTER_DAYS=90`); **hiring/openings 60 days** (fastest-moving claims).
- Stale rows: auto-demote lane (Outreach-ready → Good lead), label per §4, enter the next wave's suggested cohort (recheck queue on Review Desk). **No "verified forever" — ever.**
- **practice_intel cliff:** 2,236 locations (74% of covered) hit the 90d TTL within ~a month. Decision: do NOT mass-refresh ($ for low pivot-value); auto-label "AI-cited, stale"; refresh only rows in the active cohort.
- Steady-state recheck cost ≈ $15-30/quarter at top-300 scale.

## 9. IMPLEMENTATION SEQUENCE P0-P7

| Phase | Content | Acceptance |
|---|---|---|
| **P0** | ✅ pagination/counts/invariants DONE (11cb6e5, deployed, 86 vitest green — do not re-fix). **Remainder:** Sunday CASCADE gate; CI guards (JOB_HUNT, DEALS, queue-accounting, corrections); corrections export + `apply_manual_corrections.py`; `funnel.ts` + source-walk vitest; census.ts undetermined bug; migrate 6 `fetchAllWarroomPages` call sites + un-ranged changes.ts/launchpad.ts batches + benchmarks.ts to `fetchAllRowsStable`; ownership-truth bypass fix (use-practice-card); "verified" purge (§4); fetchNetworkSiblings limit(200) | All CI + `check_fetch_invariants.mjs` green; JHV survives a forced full_replace in staging; grep: zero hand-rolled tier switches |
| **P1** | Six trust lanes on Job Hunt + Directory; kill 0-100 scores + dso-tiers + MGMA band; rewire ask/zip-mood AI routes to census buckets; 43-vs-47 rendering per §5 | Every card: lane + why + missing[]; drift-check manifest passes; no detector share reaches any AI prompt unlabeled |
| **P2** | `job_hunt_outreach` table (JHV durability pattern) + /api/outreach (clone practice-corrections route; single-user; never open census tables to client writes) + board + practice-page tab + localStorage pin migration (blocking-once, log count) | Status change survives reload on second device; seed round-trip `--verify` passes |
| **P3** | Wave 1 (top 50) via the Factory | JHV ≥50 fresh; Outreach-ready ≥35; QA sign-off recorded |
| **P4** | Wave 2 (top 300) | Top-300 rows all carry a §4 trust state; CI ratchet |
| **P5** | Census recovery write + both sync legs + read-back (user gates; §7 note) | Live = SQLite ≈3,668 exact; floor 268/1,152 untouched; invariants updated same commit |
| **P6** | Network/owner normalization: network_id rollout, employer profiles, Equity-Path lane (T1/T2 + age + signals), DSO context panels | Every leverage claim carries a source chip; unresolved rows say "not assessable yet" |
| **P7** | Kill sweep: route triage §2 executed; warroom Hunt mode + sitrep detector KPIs removed; Streamlit + gzip-push + deal/ADSO/ADA scrapers frozen out of refresh.sh; Methodology updated; CLAUDE.md rewritten for the new mission | grep: no imports of killed modules; build + all tests green; refresh.sh runs NPPES/sync/invariants only |

Waves 3-4 slot after P5 (they benefit from the re-tiered rows). Every DB write, sync, launchd change, and API spend above = explicit user go, per-run.

## 10. DEFINITION OF DONE

Open the app →
1. **Dashboard** shows the funnel with live, reconciling counts (S0 = 4,439 exactly; every stage clickable; sums audited by CI).
2. **Opportunity List** is clean: six lanes, no 0-100 scores, every card explains itself (lane + why + missing).
3. **Top 50 are trustworthy**: each Outreach-ready row has roster/owner/hiring claims with evidence URLs + check dates ≤90d.
4. **Verified vs unverified is unmissable**: the eight §4 labels appear on every fact; "verified" appears ONLY on website-check-backed claims.
5. **Outreach is tracked**: statuses/notes/next-actions persist server-side across devices; Dashboard surfaces the next action.
6. **No fake precision, no contradictions**: no number appears on two pages with two values (funnel.ts + CI make it structural); no score outranks a trust state; stale data says it's stale; the Directory claims only what §3.6 allows.

**And explicitly:** the original full-coverage vision (named owner + roster for all 4,439) is retired, not solved — Wave 5 documents its cost ($45-90 agent-verified breadth; the *true* legal-owner version was the $250k/yr treadmill) and nothing in the app implies it happened.

---
*Single thread of authority: per the P0-session handoff, that session is closed with nothing queued; this pivot session (and its successors reading this plan) is the only writer. Frontend repo is separate (`dental-pe-nextjs`, Codex QA identity) — check its git log before every edit.*
