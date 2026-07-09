# DESIGN — Solving the Codex Analyst's P1–P10 (Truth App, Chicagoland)
**Author:** Fable (PM/architect) · 2026-07-07 · investigation run wf_d1768cd8 (14 agents, 74 verified gaps, live-mirror probes)
**Status:** DESIGN ONLY — nothing here is implemented. Every item cites file:line or DB evidence from the investigation.
**Governing law (unchanged, binding):** SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md §2 hard truth rules ·
SPEC_TRUTH_APP_ROUTES_20260704.md · DATA_CONTRACT_TRUTH_APP_20260704.md · PURGE_LIST_LEGACY_TRUTH_CLAIMS_20260704.md ·
DECISION_TRUE_INDEPENDENT_HEADLINE_20260703.md
**Standing human gates that survive every design below:** no Supabase sync without explicit user go; census writes only
through `consolidate_census.py --validate-only` → human-approved `--allow-db-write` (`--allow-rereview` for overwrites);
never DELETE from `practices`; frontend push = live deploy, push only on user instruction; detector floor CI guards untouched.

---

## 0. Root-cause diagnosis (what P1–P10 actually are)

The analyst called it a four-layer trust collision. The investigation found **five** layers and three
structural causes that generate nearly all ten complaints:

**The five colliding layers**
1. **Census truth** (`ownership_tier` + 5 OWN_COLS + `census_review_status`) — the only sanctioned ownership layer. Clean; `ownership-truth.ts` never reads anything else.
2. **Detector legacy** (`entity_classification`, `zip_scores.corporate_*`) — purged from priority-1–3 surfaces, still headline on warroom map (`living-map.tsx:47-56`), buyability, Home.
3. **Qualitative intel** (`practice_intel`, 3,370 rows) — uniformly 72+ days old (max `research_date` 2026-04-26), NPI-keyed, doctor names trapped in prose, never rendered on the practice page.
4. **Data Axle** (`da_*`, employee_count, coordinates) — feeds scores without provenance discount.
5. **Legacy manual layer** (`ownership_status` + `/api/practices/[npi]` PATCH + `/system` Update Practice tab) — a live direct-write path into the Supabase mirror that the next TRUNCATE-CASCADE sync silently erases; enum drift (`pe-backed` vs `pe_backed`) written by our own pipeline scripts; still rendered un-framed at `warroom/dossier-drawer.tsx:926`.

**The three structural causes**
- **A. Facts have no schema home.** Owner names, current doctors, believed network sizes, and public-facing
  names exist only in prose (`ownership_evidence_basis`, `provider_notes`), in slugs (`ao:SHAFI_SOHAIL`), or
  nowhere (`doing_business_as` is 100% literal `<UNAVAIL>` — 622/622 IL location rows, 1,032/1,032 practices rows).
  The UI can only show what has a column. P1, P2, P3, P7 are all this one cause.
- **B. Verification asymmetry in the prior fleet.** Adversarial verify guarded only T4/T5 tier escalations;
  intel fields (doctors, owner, notes) were never verified; `owner_identity` was dropped from the Lane-A v2 row
  contract (spec'd at EVIDENCE_FLEET_SPEC.md:37, populated 0/3,180); `research_date` records store-time, not
  page-observation time; the weekly refresh re-researches only `acquisition_readiness='high' LIMIT 10` (~97%
  of intel can never refresh). This is why agent output "disappointed": the fields the user actually reads
  were the unverified ones. P3, P4, P9 are this cause.
- **C. Landing/closure gaps.** 1,543 fresh Lane-A intel blocks (July 2026, source-backed) sit UNLANDED in 133
  result files — the dry-run says "would store 775" and was never run live. The corrections queue has a write
  side and no read side (0 rows ever, no consumer, no health check). The merge gate computes network totals
  then discards them (`_merge_lane_a_results:272-287`). Work was done and then not connected. P2, P7, P8 partly dissolve
  the moment these land.

**Design rule for everything below** (charter-compatible): *every displayed fact carries a source class and an
observed-at date, and every layer-5 write path is closed or routed through the corrections queue.*

---

## 1. Highest-leverage moves first (zero/near-zero new code)

These come before any new build. Each needs only existing scripts + your explicit go.

| # | Action | Mechanism (already exists) | Gate | Impact |
|---|---|---|---|---|
| 0.1 | **Land the 775 unlanded intel rows** | `_merge_lane_a_intel_20260702.py` dry-run → live → `upsert_practice_intel.py` → intel sync leg | Your go on live run + sync | Freshest source-backed intel in the system reaches the app; P3 staleness partially relieved before any fleet runs |
| 0.2 | **Corrections health check** | One sentinel POST to prod `/api/practice-corrections` (`submitted_by='health_check'`), read back via secret key, mark rejected | Your go (writes 1 row) | Proves P8's capture path actually works in production — 0 rows have ever been written; success is currently only inferred |
| 0.3 | **Normalize `ownership_status` enum drift** | One-shot SQLite `UPDATE … REPLACE(ownership_status,'-','_')` on practices + practice_locations, evidence file per repo law; fix the two writer scripts (`reclassify_verified_corporate_il.py:157,185`, `promote_verified_chicagoland_dso_matches.py:471`); re-sync | Your go on write + sync | 115 IL rows (47 `dso-affiliated` + 50 `pe-backed` + 18 `pe_backed` mismatch) stop rendering as raw tokens and escaping warroom filters |
| 0.4 | **Settle the GP denominator** | Recheck: docs say 4,439 IL GP; live measurement says 4,639 (`state='IL' AND is_specialist_only=0`). Find the 200-row exclusion (synthetic NPIs / closures), then either document it in DATA_CONTRACT or fix the constant | None (read-only, then doc edit) | Every headline percentage depends on this denominator; 71.64% may actually be 68.5% |

---

## 2. The data-model spine (five schema additions everything else hangs on)

All migrations are SQLite-first (source of truth) with a matching Supabase migration and a new
`SYNC_CONFIG` entry; all writes flow through pipeline scripts, never through API routes.

### 2.1 `display_name` (P1)
On `practice_locations`:
- `display_name TEXT` — the public-facing name users recognize
- `display_name_source TEXT CHECK IN ('website_title','gbp','dba','cleaned_legal','manual')`
- `display_name_verified_at TEXT` (ISO date the source page was observed)

Population ladder (best available wins):
1. `manual` — accepted corrections (`practice_name` field key already exists in the queue)
2. `website_title` / `gbp` — agent workstream W2 (below) reads the practice's own site title/og:site_name
   (2,112 rows have `website`; intel adds `website_url` on 2,254)
3. `cleaned_legal` — deterministic pass (no agent): title-case, strip `LLC/PC/LTD/SC/P.C.` suffixes,
   treat `<UNAVAIL>` as NULL, collapse `DR. IMTIAZ AHMED, PC` → `Dr. Imtiaz Ahmed` shapes. Runs over all
   5,188 IL rows in seconds; instantly kills the worst of P1 while agents fill in real brand names.

Frontend contract: ONE shared helper `src/lib/census/display-name.ts` exporting `displayName(row)`
(display_name ?? cleaned legal fallback) — replacing the five copy-pasted cleaners
(`practice-directory.tsx:78`, `practice-detail-drawer.tsx:127`, `consolidated-practice-tree.tsx:27`,
`practice/[locationId]/_components/format.ts:6`, `launchpad/display.ts:11`) and the raw renders
(`api/practice-search/route.ts:24`, `practice-directory.tsx:186`, warroom `dossier-drawer.tsx:919`,
`track-list-card.tsx:132`, `practice-dossier.tsx:1340`, `smart-briefing-builder.tsx:55`,
`practice-density-map.tsx:323`). Legal entity name becomes a secondary "Legal entity" line on the practice
page and drawers — visible, never the headline.

### 2.2 `networks` registry table (P2, P7)
New table (SQLite + Supabase, read-mostly):
```
networks(
  network_id TEXT PRIMARY KEY,          -- canonical, post-normalization
  display_name TEXT NOT NULL,           -- "Webster Dental Care", "Dr. Sohail Shafi group"
  network_type TEXT CHECK IN ('dentist_owned_group','branded_dso','stealth_dso','institutional'),
  owner_or_sponsor TEXT,                -- "Dr. Sohail Shafi" / "KKR (Heartland Dental)"
  operator_pc_names TEXT,               -- JSON array: friendly-PC / operating-PC names
  believed_total_locations INTEGER,     -- what the network claims / public sources say
  believed_total_source_url TEXT,
  believed_total_as_of TEXT,            -- observation date
  reviewed_location_count INTEGER,      -- derived, refreshed by consolidate step
  notes TEXT,
  verified_at TEXT
)
```
This is the schema home for the Shafi problem: the UI can finally say
**"15 reviewed offices · ~19–20 believed (source, as of date)"** instead of implying 15 is the total.
Seeds already on disk: LEDGER `ao_reach` artifacts, `dso_locations` (633 rows: Ideal 154, Heartland 105,
Aspen 46, Tend 30, GLDP 28, Webster 17), `affiliated_dso` counts — the merge gate already computes
`net_counts` and throws them away; this table is where they land instead.

**network_id normalization (prerequisite, mostly mechanical):** today 950 IL rows / 634 distinct ids in
4 formats — `ao:` (427 distinct, 325 singletons), `brand:` (181), `domain:` (5), and 26 free-text ids on 53
rows (e.g. `Heartland Dental / Dental Professionals of Illinois, P.C.`). Rules: free-text → `brand:` slugs;
Heartland's 4 ids merge to one; `ao:` singletons stay valid (a solo owner is still an owner) but the registry
only gets rows for networks with ≥2 locations OR a believed_total >1. Every rename is written through
`consolidate_census.py` (it owns OWN_COLS), with an evidence file mapping old→new.

Frontend contract: `formatNetworkId` becomes the ONLY formatter (delete/re-export the divergent
`formatNetworkName` in `census-badge.tsx:74-86`; today both run on the same practice page and disagree),
and it passes punctuation-heavy names through verbatim. It is currently duplicated 7×.

### 2.3 `owner_identity` on `practice_locations` (P2)
- `owner_identity TEXT`, `owner_identity_source_url TEXT`, `owner_identity_observed_at TEXT`
This was in the fleet spec and dropped from the v2 row contract — 0/3,180 populated. Recovery is cheap:
(a) re-extraction pass over existing LEDGER reasoning prose + `ao:` slugs (deterministic + small-model,
no web needed for the 630 ao: rows — the slug IS the owner name, just needs casing), (b) W2 agent
verification for anything user-facing. `authorized_official_*` (populated on 4,740 IL practices rows) renders
only with an explicit "NPI registry official — may be owner, may be office manager" label, never as "Owner".

### 2.4 `practice_doctors` roster table (P3)
```
practice_doctors(
  id INTEGER PRIMARY KEY,
  location_id TEXT NOT NULL,            -- location-keyed, NOT NPI-keyed (intel's NPI keying reaches only 2,131 locations)
  doctor_name TEXT NOT NULL,
  role TEXT,                            -- 'dentist','associate','specialist','hygienist-lead',...
  source_url TEXT NOT NULL,             -- the page the name appears on
  page_observed_at TEXT NOT NULL,       -- when an agent SAW the page (not store time)
  status TEXT CHECK IN ('active','departed','unverified') DEFAULT 'unverified',
  verified_by TEXT,                     -- fleet run / unit id
  superseded_at TEXT                    -- set when a newer roster replaces this row
)
```
Write policy: **supersede, don't overwrite** — a new verified roster marks prior rows `superseded_at`
(keeps history, fixes the never-overwrite-makes-stale-permanent trap). UI freshness states, rendered on the
practice page and every dossier:
- ✅ *Verified from the practice's website* (`status='active'`, observed ≤90d)
- 📇 *NPI registry providers (may be stale)* — the cheap join: `practices` names for the raw NPI chips at
  `practice-tabs.tsx:513-534` (today the page shows bare 10-digit numbers as its ONLY provider surface)
- ⚠️ *Older research — needs refresh* (intel prose > 90d)
- ∅ *Unknown — not yet researched*
The Dental Smiles failure (app shows Samaan/Graves; site shows Numera/Khan/Pai/Agrawal/Shareef) becomes
structurally impossible to present as current: prose names never render as "current doctors"; only
`status='active'` rows with a fresh `page_observed_at` do.

### 2.5 Corrections lifecycle completion (P8)
Capture exists (`practice_manual_corrections`, 7 field keys, POST route, panel). Missing pieces:
- **Ownership-domain suggestion keys** — extend the CHECK + `ALLOWED_FIELDS` with
  `ownership_tier_suggestion`, `network_membership`, `pe_backed_claim`, `doctor_roster_note`. These are
  *suggestions*, adjudicated by W3 against census protocol; the legacy `ownership_status` vocabulary never
  enters the queue. (Today the fields users most need to correct — owner/tier/DSO — have only the unsafe
  bypass path.)
- **`scrapers/apply_manual_corrections.py`** (the missing consumer): pull `status='queued'` via secret key →
  adjudication pass (W3) → accepted display/roster fields write to SQLite directly with evidence file;
  accepted ownership suggestions become inputs to the census queue (never auto-applied) → mark rows
  `applied`/`rejected` with reviewer note → surgical column sync. This deliberately reuses the fleet's
  adjudication-disposition shape so the merge machinery stays one system.
- **Panel on the practice page** — `/practice/[locationId]` is the canonical click-through from search, maps,
  directory, and both trees, and has NO correction entry point (panel exists only in two secondary drawers).
- **Queue health**: flush-on-load for the write-only localStorage fallback
  (`manual-correction-panel.tsx:52-71`), a queued/applied/rejected count on `/system`, and a CI invariant
  asserting the table is reachable.

### 2.6 Map/geo columns (trust-architecture extra)
- `geocode_source TEXT` (`'data_axle'|'census_batch'|'zip_centroid'`) added alongside the one-shot **free US
  Census Bureau batch geocode** of the 2,415 unmapped-with-address IL rows. Today geocode precision is
  *inversely* correlated with review value: verified T1 independents are the worst-mapped tier (37.9% precise)
  vs stealth DSO 71.4% / branded 64.2% — every dot map visually fades the census's most important finding.
  No geocoder exists anywhere in scrapers/ today; this is a pipeline script, not a fleet.

---

## 3. Problem-by-problem solution design

### P1 — Practice identity (`<UNAVAIL>` / legal-entity names)
**Root cause:** `doing_business_as` is 100% garbage; five divergent name cleaners, none of which title-case or
strip suffixes; several surfaces skip cleaning entirely.
**Solution:** §2.1 in full. Order: (1) treat `<UNAVAIL>` as NULL everywhere + shared `display-name.ts`
(hours, kills the literal `<UNAVAIL>` renders including cmd-K search results), (2) deterministic
`cleaned_legal` pass (hours), (3) W2 website-title backfill (fleet), (4) manual corrections feed `manual`.
**Legal entity** stays as an audit line. FUTURE_DATA_INTEGRATION_PLAN line 30 already sanctions this.
*Effort: hours-solo-dev + agent-fleet-small (inside W2).*

### P2 — True owner / who really runs this practice
**Root cause:** no owner field anywhere; network_id format anarchy; no registry; believed totals discarded at
merge; verification never covered owner claims.
**Solution:** §2.2 + §2.3 + workstream W2. The practice page ownership tab answers, in order:
1. **What is this?** — five-bucket census label (unchanged contract)
2. **Who owns/operates it?** — `owner_identity` (with source + date) or "Owner not yet verified"
3. **Part of a group?** — registry join: "Webster Dental Care — 6 reviewed of 17 believed offices (source)";
   operator/friendly-PC line for MSO cases ("Operated by Dental Professionals of Illinois, P.C. — a
   Heartland Dental supported practice")
4. **PE money?** — `pe_backed` + registry `owner_or_sponsor` (today `sponsorNode` renders the literal string
   "PE-backed" and nothing else — near-content-free)
**Reviewed-vs-believed language** becomes law on every count surface: tree, siblings tab
(`fetchNetworkSiblings` also silently caps at 200 — disclose it), market-analytics "Offices" header
(`market-analytics.tsx:221` — the exact "Heartland: 10 offices" misread; the correct pattern already exists at
`ownership-landscape.tsx:178`).
*Effort: days-solo-dev (schema+UI) + agent-fleet-small (W2 registry) — the ao: slug re-extraction is nearly free.*

### P3 — Current operating doctors
**Root cause:** no structured doctor storage; intel prose only; store-time dates; ~97% of intel can never
refresh; practice page never reads intel and shows raw NPI digits.
**Solution:** §2.4 + workstream W1 (the flagship fleet), preceded by move 0.1 (land the 775 rows) and the
cheap NPPES-name join (days-solo-dev, honest "registry snapshot" label). Weekly refresh queue widens from
`readiness='high' LIMIT 10` to a staleness-ordered queue (oldest `page_observed_at` first, W4).
*Effort: days-solo-dev (join + UI states) + agent-fleet-large (W1).*

### P4 — Scores too confident
**Root cause:** lanes shipped but leak; two divergent audit implementations; AI routes accept client-supplied
intel unaudited; dead code with wrong copy; legacy boosts.
**Solution (all solo-dev, mostly hours each):**
- Raise/remove `INTEL_FETCH_LIMIT=200` (`queries/launchpad.ts:32`) — verified_target is currently unreachable
  beyond the structural top-200; move the source-backed gate INTO `resolveLane` (today it's an undocumented
  pre-filter) so the lane function is the single authority.
- One shared `auditIntel()` (90d, strict) replacing launchpad-vs-compound-narrative divergence; server-side
  audit in `ask`/`smart-briefing`/`interview-prep` routes (today client-supplied intel is injected unaudited).
- Fix blocking regexes matching negated phrases ("no conflicting evidence" currently blocks).
- Delete dead ScoreTab (wrong base/caps copy); fix `track-list-card.tsx:304` labeling stale dossiers
  "Current verified dossier"; make the 'Archived research only' chip reachable.
- Remove `buyability_score`'s +25 unprovenance boost and Data-Axle count boosts, or discount by source class.
- Practice page: replace bare "86 / 100" renders (`page.tsx:79`, `practice-tabs.tsx:384-387`) with the lane
  verdict; raw score demoted to Older-data tab. Verdict lanes map 1:1 to the analyst's asked-for labels:
  verified_target="Verified strong target", promising_lead="Promising but needs review",
  needs_research="Interesting lead — do not trust yet"; census T4/T5/pe_backed="Avoid".
*Effort: ~2–3 days solo-dev total. No fleet needed.*

### P5 — Too many tabs / P6 — Language too technical
**Root cause:** accretion + jargon leaks (~30 sites) + headline babel (4 different "corporate share" values,
3 different "acquisition targets" values — `buyability-shell.tsx:306` hardcodes '~34' and admits the mismatch
in its own tooltip).
**Solution:**
- **Practice page 5→3 tabs**: Overview (census ownership + owner + roster + evidence, one column) ·
  Related offices (registry-aware) · Older data (detector + registry + raw NPIs + Data Axle, quarantined).
  Job Hunt + Acquisition tabs are 4-field shells duplicating header MetricBlocks with drifted strings — fold
  into one "Use this practice" header card. (The route spec's "5 tabs deliberate" verdict predates the
  finding that two tabs are near-empty duplicates; this is a refinement, not a reversal — flagging for your sign-off.)
- **Directory**: keep the front door, collapse sub-tabs, delete ~600 lines of dead dossier-tab code, fix
  h1/aria mismatch ("Chicagoland Practice Directory" vs "Job Market tabs").
- **One headline module**: `src/lib/census/headline-stats.ts` — every KPI card on Home/Directory/Ownership/
  Buyability imports the same computed numbers with the same labels from `summarizeBuckets` + the settled
  denominator (§1 move 0.4). No page computes its own headline again. This is the single fix for headline babel.
- **Jargon sweep** with the analyst's exact vocabulary: "Census coverage"→"Hand-reviewed so far",
  "DLD-GP/10k"→"Dental offices per 10k people", bucket names from BUCKET_META only, kill "Legacy heuristic"
  user-facing (worst offenders: `home-shell.tsx:497,513,521-522,270`; `market-intel-shell.tsx:405` renders a
  raw network_id in a code tag; `zip-score-table.tsx:97,152`).
- **Home recompose** (Phase 3 of settled law): orientation page — "what is this data, how much is reviewed,
  what changed lately, where do I go" — not a KPI dashboard; removes the dead 'Batch Progress' card
  (`home-shell.tsx:409`), raw NPIs (:270), Legacy Floor KPI, and the 8 NAV_CARDS duplicating the sidebar.
- **Route/name mismatch**: add `redirects()` in `next.config.ts` mapping friendly paths (`/directory` already
  re-exports; add `/ownership`→`/market-intel`, `/job-hunt`→`/launchpad`, etc.), align sidebar labels.
*Effort: ~1 week solo-dev spread across Phase 3 execution. No fleet.*

### P7 — Consolidated practice tree
**Root cause:** ships honest but thin — exact-network_id grouping over a normalization mess, no believed
totals, no operators, no click-through, silent scope dependence.
**Solution:** after §2.2 lands, the tree joins `networks`: believed totals with source links, operator-PC
lines, `network_type` chips replacing tier-derived grouping, click-through to `/practice/[locationId]`,
explicit scope line ("within living-location ZIPs"), `formatGroupId` lowercasing bug dies with the shared
formatter. Aspen fix: its 16 rows sit in R4 triage — releasing that queue (existing warroom ops flow, your
gate) makes the most famous DSO stop showing near-zero.
*Effort: days-solo-dev once registry exists.*

### P8 — Manual corrections loop
**Root cause:** write-side only; PLUS the layer-5 bypass that must close first (see W3 + §5 Phase 1).
**Solution:** §2.5 + workstream W3. Order matters: health-check (0.2) → close bypass → extend field keys →
panel on practice page → apply loop. The bypass close is non-negotiable design-wise: `/api/practices/[npi]`
PATCH writes ownership fields straight to the Supabase mirror with the service key, is wide open from any
local `npm run dev` (admin token skipped when `NODE_ENV !== 'production'`, `admin-token.ts:17`), logs
`change_type='acquisition'` which fires Launchpad's recent-acquisition warning (`launchpad.ts:569`), and its
writes are erased by the next TRUNCATE-CASCADE sync anyway (which also permanently destroys the Supabase-only
`practice_changes` audit rows). Delete the PATCH (or 410) + remove the Update Practice tab; same decision
applies to `/api/deals` POST and `/api/watched-zips` POST (also clobbered by full_replace). Standardize the
three routes bypassing `createServerClient` (they read only `SUPABASE_SERVICE_ROLE_KEY`, which does NOT exist
in Vercel — only `SUPABASE_SECRET_KEY` does — so they silently run as anon today).
*Effort: hours-solo-dev (close bypass, keys, panel) + days-solo-dev (apply script) + agent adjudication inside W3.*

### P9 — Agent work needed (sized)
Covered by workstreams W1–W5 in §4. Universe sizes from live counts: 2,116 stale-intel locations · 1,507 IL GP
with neither website nor intel (hardest cohort) · 2,008 untiered (477 undetermined + 178 held + 1,353
untouched; 804 GP-scope with neither tier nor status) · 634 raw network ids → ~150–200 real registry rows ·
73.6% of intel at partial/insufficient verification quality.

### P10 — Solo dev work
Consolidated into the phased backlog in §5. The "weekly sync fails when data breaks" complaint maps to:
deterministic pre-sync validators (`check_data_invariants.py` extensions: corrections-table reachable, enum
whitelists, denominator constant), read-backs after each leg (already law), and the narrow-refresh-queue fix (W4).

---

## 4. Agent workstreams (the fleets) — specs + QA doctrine

### 4.0 Why prior fleet output disappointed — and the doctrine that fixes it
Diagnosis (evidence-backed): (a) verify pass covered only T4/T5 tier claims — intel fields sailed through
unverified; (b) `owner_identity` silently dropped from the row contract; (c) `research_date` = store time;
(d) results left unlanded (1,543 blocks); (e) no schema home for the facts users read, so agents wrote prose.

**Fleet doctrine v2 — binding on every workstream below:**
1. **Row contract completeness check is a merge-gate assertion**, not a convention: if a spec'd field
   (owner_identity, page_observed_at) is absent from the emitted row, the row fails closed and the unit is
   flagged — a contract field can never silently vanish again.
2. **Every written fact gets verified, not just escalations.** Verifiers receive the claim + source_url and
   must confirm the fact appears on that page *today*. Verdicts: CONFIRM / REFUTE / STALE / INSUFFICIENT.
   Only CONFIRM writes user-facing state (`active` doctors, registry rows); INSUFFICIENT lands as
   `unverified` — stored but never displayed as current.
3. **`page_observed_at` is mandatory** on every claim; store-time is recorded separately and never displayed.
4. **Deterministic validators before the human gate**: URL liveness sample (10%), name-shape checks (no
   ALL-CAPS legal entities in doctor_name, no digits), dedup within unit, enum whitelists.
5. **Acceptance sampling by you**: per merge batch, 10 random rows presented with claim + source URL for
   eyeball check; <9/10 pass → batch rejected, prompts revised. This is the direct answer to "I'm still not
   satisfied" — you sample-audit every batch before it lands, cheaply.
6. **All existing human gates preserved** (validate-only → --allow-db-write, --allow-rereview, both sync legs).
7. **Model split as before**: Sonnet-5 researchers, Opus-4.8/Fable verifiers; forced web_search; per-claim
   `_source_url`; ≤16-practice units; fail-closed merges.

### W1 — Current-doctors roster fleet (P3) — *the flagship*
- **Queue:** all IL GP locations with a known website (2,738 have one via `website` ∪ intel `website_url`),
  ordered: user's named cases (Dental Smiles, Shafi network, Webster, Family Dental) → launchpad
  verified_target/promising cohort → staleness order. The 1,507 no-website cohort is a later rung (needs a
  find-the-website step first — harder, more hallucination-prone, do NOT mix into rung 1).
- **Researcher contract per practice:** open the practice's own site (team/about/providers pages); emit
  `practice_doctors` rows (name, role, source_url, page_observed_at) + `display_name` candidate from the
  site title (feeds §2.1) + optional `owner_identity` candidate if the site states it ("Dr. X, owner").
  If no roster page exists: emit `roster_unavailable` with the URL tried — never guess from directories.
- **Verifier contract per doctor:** confirm the name appears on the given URL now. REFUTE/absent → row lands
  `unverified`. Old intel names not found on the site land `departed` (supersede semantics, §2.4).
- **Merge:** fail-closed → validators → your 10-row sample → `--allow-db-write` equivalent for the new table
  (own write script, same gates) → sync leg with read-back.
- **Cost/scale:** ~2,700 practices × (1 research + ~4 doctor-verifies) ≈ $40–80 total at Lane-A batch rates;
  run in 4–6 unit waves so sampling can stop a bad wave early. First wave: 200 practices (your named cases +
  top launchpad cohort) to validate the contract end-to-end.

### W2 — Owner identity + network registry (P2, P7, P1-assist)
- **Rung 0 (no web, near-free):** deterministic + small-model pass over `ao:` slugs + LEDGER reasoning prose →
  `owner_identity` candidates with `source='ledger_extraction'` (displayed with that framing until rung-1
  verified); network_id normalization map (old→new) for your review.
- **Rung 1 (fleet, ~150–200 networks):** one agent per multi-location network: verify owner/sponsor, operator
  PC names, believed_total_locations from the network's own site + credible public sources (locator pages,
  state filings; S13/S14/S15 signals are pre-approved future adds). Emit one `networks` row, every field
  source-URL'd. Adversarial verify on every row (these are exactly the claims that embarrassed the app).
  Shafi/Webster/Family Dental/Heartland-IL are named acceptance cases: W2 is not done until the app can
  state their reviewed-vs-believed counts correctly.
- **Cost:** ~200 networks × research+verify ≈ $10–20. Small, high leverage.

### W3 — Corrections adjudication loop (P8, recurring)
- **Trigger:** cron or manual, whenever queued rows exist. Per correction: agent checks suggested_value
  against its source_url + current census record → disposition (accept / reject / needs-census-review).
  Display-layer accepts (name, website, roster note) write via `apply_manual_corrections.py`; ownership-domain
  suggestions convert into census-queue entries (handled by the census protocol with `--allow-rereview` since
  targets are already tiered) — never auto-applied.
- **You gate:** every apply run (it's small — corrections arrive at human speed).

### W4 — Stale-intel revalidation (P3/P9, recurring)
- Replaces the `readiness='high' LIMIT 10` refresh: staleness-ordered queue over intel >90d, budget-capped
  per week (e.g. 100/week ≈ $1), re-research using the W1 contract (so refreshes produce structured rows,
  not more prose). High-score Job Hunt targets get priority — this is the "recheck my top targets" ask.

### W5 — Hidden-DSO escalation, rung 1 (P9)
- Queue: T2/T3 rows with DSO-pattern signals (shared operator PC names from W2, shared phones/domains,
  believed_total mismatches) + the 477 undetermined. Two-pass: pattern-collector (cheap) → escalation
  researcher on flagged rows only. Writes go through the standard census chain (T4/T5 only on CONFIRM —
  unchanged law). This rung waits until W2 lands, because operator-PC names are its best signal.

### W6 — Geocode backfill (not a fleet)
- One pipeline script: Census Bureau batch geocoder over 2,415 addresses → lat/lng + `geocode_source`,
  evidence file, sync with your go. Fixes the inverted map bias (§2.6).

---

## 5. Solo-dev phased backlog (P10 + trust extras)

**Phase 1 — Trust hygiene (≈2–3 days, no schema, no fleet)**
1. Close the layer-5 bypass: delete/410 `/api/practices/[npi]` PATCH + Update Practice tab; distinct
   change_type for any surviving log path; gate `/api/deals` + `/api/watched-zips` on token regardless of
   NODE_ENV; route all three through `createServerClient`; fix misleading error string (`server.ts:16`).
2. Shared `display-name.ts` (+`<UNAVAIL>`-as-NULL) across the 11 render/search sites.
3. One `formatNetworkId`; delete `formatNetworkName` divergence + the 6 other copies.
4. Shared `escapeHtml` for density + saturation map popups (XSS); delete dead `getPracticesWithCoords`
   (latent bias filter); delete dead ScoreTab + ~600-line dead dossier tab.
5. P4 fixes: INTEL_FETCH_LIMIT, gate-into-resolveLane, shared auditIntel + server-side audit on AI routes,
   negation regexes, "Current verified dossier" label, buyability boost removal.
6. `ownership_status` render-site cleanup: legacy-frame `dossier-drawer.tsx:926`; fix warroom underscore-only
   filters (`warroom.ts:654,660,721`) — or purge the axis per purge-list law (respect the F27 vitest allowlist).
7. `redirects()` + sidebar/h1/aria alignment; map click-through to `/practice/[locationId]` (location_id is
   already in feature properties); ManualCorrectionPanel onto the practice page; localStorage flush-on-load.

**Phase 2 — Schema spine + mechanical passes (≈3–4 days + your gates)**
Migrations (§2.1–2.6) → deterministic display-name pass → ao:-slug owner extraction → network_id
normalization map (your review) → geocode backfill → NPPES roster join UI with freshness states.

**Phase 3 — Fleets (order: W2 → W1 wave 1 → sample-audit → W1 remaining → W3 → W4 standing → W5)**
W2 first because it's small, high-leverage, and feeds W1's owner cross-checks and W5's signals.

**Phase 4 — Settled-law Phase 3 execution + UI consolidation (≈1 week)**
Home recompose · warroom census-ops queues (12 legacy sitrep KPIs out; holds 91 / triage 649 / undetermined
477 / never-researched ~950 queues in; Hunt/Investigate game removed) · buyability reframe (candidate set =
census T1/T2, `categorize()` at `buyability-shell.tsx:37-57` currently lets hand-reviewed DSOs rank as
targets) · headline-stats module · practice-page 3-tab redesign · jargon sweep · warroom/launchpad map lens
swaps to census buckets (kills the hardcoded 5-brand "DSO Avoid" list).

---

## 6. Open decisions for you (nothing proceeds on these without your call)
1. **Practice page 5→3 tabs** — refines the route spec's "5 tabs deliberate" verdict. Approve?
2. **GP denominator** — 4,439 (docs) vs 4,639 (measured). Document the exclusion or change the constant?
3. **`ao:` singleton networks (325)** — keep as owner labels only (my recommendation) or registry rows too?
4. **W1 wave-1 scope** — 200 practices starting with your named cases; approve cost (~$5–8) and the
   10-row sample-audit workflow?
5. **Aspen R4 release** — 16 rows in triage; release through the existing warroom ops flow?
6. **Land the 775** (move 0.1) and the **sentinel POST** (0.2) — both need your explicit go.

---

## 7. AMENDMENTS — 2026-07-08 (decisions ratified + analyst deltas accepted)

### 7.1 The six §6 decisions are ANSWERED (user, 2026-07-08)
1. Practice page 5→3 tabs — **APPROVED**.
2. GP denominator — resolved by derivation: **4,439** = 4,639 IL not-specialist-only − 179
   da_unverified − 12 non_clinical − 5 duplicate_location − 4 specialist. Documented as law in
   `DATA_CONTRACT_TRUTH_APP_20260704.md` §7. It is a filter with SQL provenance, not a choice.
3. `ao:` singleton networks — **labels only**, never registry rows. Additionally (analyst delta):
   `ao:` slugs render as **"owner (candidate)"** until a verifier CONFIRMs the owner identity;
   never displayed as unqualified "owner".
4. W1 doctors fleet wave 1 (200 practices, 10-row human sample audit per batch) — **APPROVED**.
5. Aspen R4 (16 triage rows) — **release through the existing warroom ops gate** (no new path).
6. Land the 775 + sentinel corrections POST — **DONE 2026-07-08** (see §7.3).

### 7.2 Analyst feedback — debate verdicts (accepted / rejected, with evidence)
- **ACCEPTED — denominator is a documented filter:** verified by SQL (exclusions sum exactly to
  200; `zip_scores` matches 4,439 with 0 residual). §2 language of this doc that framed it as an
  open "choice" is superseded.
- **ACCEPTED — enum re-baseline:** fresh counts were 97 hyphenated rows in `practice_locations`
  (47 dso-affiliated + 50 pe-backed) and 140 in `practices` (90 + 50), matching the analyst. The
  earlier "115" figure in this doc was a mis-sum that included the underscore variant
  `pe_backed` (18 rows). Executed 2026-07-08 — see
  `data/dso_research/ownership_status_enum_normalization_20260708.json`.
- **ACCEPTED — doctor-table semantics:** absence from a re-scraped site ≠ `departed`. Status enum
  becomes `active | not_reconfirmed | departed | unverified`; `departed` requires positive
  evidence (announcement, obituary, new-practice bio); silent absence maps to `not_reconfirmed`.
  §2.4 amended accordingly.
- **ACCEPTED — display-name provenance fields:** `display_name_source_url` (nullable) +
  `display_name_observed_at` (nullable) replace the single `display_name_verified_at` in §2.1.
  `cleaned_legal`/`dba` sources have no URL — that's what nullable means; a NULL URL displays as
  "derived", never as "verified".
- **ACCEPTED — network aliases:** normalization of free-text/legacy `network_id`s writes a
  `network_aliases (old_id → canonical_id)` mapping table; old ids never destroyed, deep links
  keep resolving. §2.2 amended.
- **ACCEPTED — 775 rows are partial/opportunistic forever:** they carry
  `verification_quality='partial'` + `research_method='lane_a_census_opportunistic'` (enforced by
  the merge script itself) and must NEVER render under a "Current verified dossier" style label.
  The frontend label fix (track-list-card.tsx:304) is in Phase 1.
- **PUSHBACK (recorded):** the analyst's enum-count "correction" agreed with the investigation's
  raw data — the discrepancy was my summation error, not a data disagreement. And the 775's
  partial labeling was already designed into the merge gate; the analyst's demand changed the
  frontend label priority, not the data plan.
- **ACCEPTED — execution order:** (1) close PATCH bypass entirely (delete route, not token-gate),
  (2) denominator documented + pre-sync invariant, (3) land 775 labeled partial, (4) sentinel
  POST with read-back, (5) enum normalization with fresh counts, (6) schema-spine migrations land
  TOGETHER (SQLite + ORM + Supabase DDL + sync + TS types), (7) W2 before W1 wave 1.

### 7.3 Executed 2026-07-08 (this session)
- **775 Lane-A intel rows landed** (SQLite `practice_intel` 3,370 → 4,145; gates: 0 FK misses,
  763 existing rows untouched, 5 empty-after-gate skipped). Supabase leg via surgical
  `scrapers/dossier_batch/upsert_practice_intel.py` (ON CONFLICT DO UPDATE, no TRUNCATE):
  4,145/4,145, 0 errors; independent REST read-back: 775 `lane_a_census_opportunistic` rows,
  max `research_date` matches local exactly. Quality mix now partial 3,056 / verified 891 /
  insufficient 198.
- **Sentinel corrections POST proven in production** (row id=2: POST → queued → read-back →
  PATCH to rejected). P8 capture path works end-to-end.
- **Enum normalization executed both legs** (140 + 97 local; Supabase 102 + 57 + 47 + 50, plus
  2 genuine value-drift NPIs 1023549078/1790819340 aligned to local `dso_affiliated`). Writer
  scripts fixed at `reclassify_verified_corporate_il.py:157,185` +
  `promote_verified_chicagoland_dso_matches.py:471`. All four CI guards re-verified intact
  (268 / 1,152 / 3,180 / 6,754).
- **Denominator documented** — `DATA_CONTRACT_TRUTH_APP_20260704.md` §7.
