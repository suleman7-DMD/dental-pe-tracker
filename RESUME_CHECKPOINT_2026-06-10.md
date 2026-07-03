# RESUME CHECKPOINT — 2026-06-10 (Chicagoland data-integrity audit, mid-fix)

> **Read this entire file before doing anything.** It is the saved state of an in-progress
> session. Everything below is verified fact unless marked otherwise. The DB referenced is
> `data/dental_pe_tracker.db` (SQLite, ground truth). A pre-session backup exists:
> `data/dental_pe_tracker.db.pre_phase4_bak`. No DB writes have happened yet this session.

---

## 1. THE PROBLEM BEING SOLVED (user's mandate, verbatim intent)

User message 1: act as a PE specialist who knows the dental market. Go through every tab of
the Next.js app (dental-pe-nextjs.vercel.app). Numbers "seem extremely suspect." Focus ONLY
on Chicagoland (269 IL ZIPs). Verify every practice record is REAL (real-life directory),
verify % corporate / % consolidated / maps / graphs are legitimate, not hallucinated.
**Fix everything at the root level; don't stop until the glaring issues are figured out.**

User message 2 (explicit multi-agent opt-in): fan out agents — a PE-specialist agent with
web-researcher subagents verifying each practice is legitimate (FIRST: figure out how many
practices actually exist across the 269 Chicagoland ZIPs and check our number), then
software-engineer agents to make fixes.

Operating autonomously. The deliverable is FIXES, not just a report.

---

## 2. WHAT THE AGENT FLEET FOUND (10-agent workflow, COMPLETED — verdicts final)

Workflow output (101,608 chars, valid JSON) is at:
`/private/tmp/claude-501/-Users-suleman-dental-pe-tracker/6af2d387-c4e5-498c-9266-ab776f499b68/tasks/wh2jjg21d.output`
(keys: summary/agentCount/logs/result; result keys: census/registry/spots/liveapp).
NOTE: `result.spots` contains only stage labels — the 6 spot-check agents' detailed verdicts
did not propagate into the JSON (fallback: agent-<id>.jsonl in the session transcript dir).

### 2a. Census agent — IS 4,608 the real Chicagoland GP count? NO — INFLATED ~12-25%
- True GP-location count for the 269 IL ZIPs ≈ **3,800** (range 3,527–4,082).
- Method: Census ZBP 2022 NAICS 621210 = 4,219 all-dental employer establishments in scope,
  ×1.14 nonemployer uplift, ×0.79 GP share; county CBP independent path → ~3,799.
- Primary inflation source: **450 DA_-keyed synthetic locations** (Data-Axle-only, no NPI
  evidence), 411 of them inside the GP denominator.
- **163 DA_-only solo_inactive** (= 97% of ALL solo_inactive) likely closed/phantom → PURGE
  from GP denominator (census agent's top recommendation).
- **135 DA_-only solo_high_volume** suspicious → manual review.
- NPI-evidenced GP count = 4,217. If denominator ~3,900, corporate floor ≈ 6.8% not 5.77%.

### 2b. Registry agents — is the NPI backbone real? YES
- 48/48 stratified-sample NPIs exist in the CMS registry, 0 deactivated, 47 clean matches,
  1 address-staleness (1720954985 MCGRADY ORTHODONTICS). Federal data is REAL, not hallucinated.

### 2c. Evenly-verifier — 21 suspicious "corporate" locations reviewed
- **Evenly Technologies** ("EVENLY ORTHODONTICS DUPONT") is an ortho-service partner for
  INDEPENDENT GPs — owns ZERO practices. Data-Axle `parent_iusa='000000000'` placeholder
  caused the false corporate linkage.
- Verdict: **16 false-corporate** (13 Evenly-only, 1 JLL/Izzo landlord-confusion, 2 bad UDP
  seeds), **2 uncertain** (demote per floor principle: no hard evidence = not corporate),
  **3 confirmed corporate** (keep). → **DEMOTION SET = 18** (full mapping in §4).

### 2d. Liveapp agent — page-by-page KPI audit of the live Vercel site
Correct: Home 4,970 / 381,598 / 290 / 5.7% / 10.6% / 14.6% all verified. Warroom 266/5.8%
correct. Job Market corporate floor 5.8% correct. Data Breakdown 5,637 correct-by-app-logic
(5,657 − 20 residential).
Bugs/staleness found (ALL still unfixed):
1. **Market Intel "Data Axle enriched 2,992"** — stale hardcoded `GLOBAL_DATA_AXLE_ENRICHED_NPI_COUNT`
   in `dental-pe-nextjs/src/lib/constants/data-snapshot.ts`. Actual: 2,981 (practices w/
   data_axle_import_date) or ~2,900 (location-level). Fix: update constant (or query live).
2. **Market Intel labels 5,637 as "NPI rows"** — it is the non-residential LOCATION count.
   Real NPI rows = 13,818. Label fix only.
3. **Job Market labels 5,169 as "Federal NPI records"** — it is the IL practice_locations
   scope count. Real IL NPI rows = 11,690. Label fix only.
4. **Job Market labels 4,608 as "total NPI rows for Chicago"** — it is GP locations. Label fix.
5. **Data Breakdown "Deals by source" = 2,962** — query misses sources `beckers` (19) +
   `beckers+gdn` (3); 22 deals invisible vs the 2,984 "Deals by year" total. Fix:
   add BECKERS to `getDealsBySource()` sources array.
6. Job Market "Enriched 2,596 (50.2%)" — NEEDS VERIFICATION (scope/denominator mismatch vs
   Supabase 2,900; possibly fine).
7. Warroom "Flagged Practices: -- (pending)" — data IS synced (zip_signals 290, practice_signals
   13,818); likely client-side load/render issue, investigate later.
8. Warroom "PE Deals in Scope: 0" — all 63 IL deals have target_zip=NULL (scraper data-quality
   limitation, not a display bug).
CLAUDE.md staleness found: Supabase practices corporate is actually 1,089 (590 reg + 499 natl),
NOT 875 as CLAUDE.md says; `zip_signals` IS synced (290 rows), CLAUDE.md "0 Supabase" note stale.
Supabase practices lags SQLite 1,178 by the 89 Phase-4 flips. Deals: Supabase 2,984 vs SQLite
2,975 (+9 sync lag, normal).

---

## 3. FIXES ALREADY APPLIED THIS SESSION (uncommitted, in working tree)

**Frontend ×100 percent-scale bug — FIXED in 3 components, `npm run build` exit 0:**
`zip_scores.corporate_share_pct` / `buyable_practice_ratio` are 0–1 FRACTIONS in the DB
(verified: max 0.6667 / 1.0; `merge_and_score.py:470-472` writes `round(x,4)`), but
`formatPercent()` expects 0–100. Three drawers were rendering "0.06%" instead of "5.8%":
- `dental-pe-nextjs/src/app/warroom/_components/zip-dossier-drawer.tsx` (lines ~614/620) → `* 100` added
- `dental-pe-nextjs/src/app/warroom/_components/dossier-drawer.tsx` (lines ~1158/1172) → `* 100` added
- `dental-pe-nextjs/src/app/launchpad/_components/zip-dossier-drawer.tsx` (lines ~338/345) → `* 100` added

**NOT yet committed. Nothing else has been changed (no DB writes, no Python edits).**

---

## 4. NEXT TASK — Task #1: demote the 18 false-corporate locations (FULLY SPECIFIED, ready to write)

Write `scrapers/demote_false_corporate_il.py` modeled on (reverse of)
`scrapers/reclassify_verified_corporate_il.py` (read it — promotion mechanics to mirror).

### The 18 demotions (location_id → target class | evidence)
| location_id | name | new class | evidence note |
|---|---|---|---|
| feaa63bd7ced2c0e | SUN DENTAL CARE PC (Naperville 60563) | solo_established | Evenly-only linkage; Evenly owns no practices |
| 4ca83acbcd91a330 | OAK BROOK DENTAL CENTER (60523) | small_group | Evenly-only |
| 1adac605c6abd972 | EMAD ZAIDI DMD PC (Bolingbrook 60490) | family_practice | Zaidi brothers; Evenly-only |
| 58af66ee2bf4b9c6 | ARLINGTON HEIGHTS DENTAL GROUP (60004) | large_group | 5 providers; UDP seed ADDRESS MISMATCH (UDP is at 1044 W Rand Rd, not 201 N Arlington Heights Rd) |
| 5ead583d8354e6e4 | FAVIA FAMILY DENTAL (60004) | solo_established | prov_cnt 0; org NPI 1851083182 → **org_only_npi**; junk affiliated_dso='General Dentistry' |
| e6ce96c5946ab89f | Vivirito Dental (Des Plaines 60018) | solo_established | bad UDP seed (web-verified independent) |
| 2cb946f04fa11798 | City Dental (Chicago 60614) | small_group | Evenly-only |
| 42d1dfe2d92fb435 | VETERANS SQUARE DIAGNOSTICS (60630) | small_group | "Calera Capital" = landlord of building, not owner |
| 778740224402dbd4 | BRIGHTON PARK DENTAL (60632) | solo_established | Evenly-only |
| d3b3b09cc6ed98dd | ASIAN VILLAGE DENTAL (60640) | solo_established | Evenly-only |
| bb925c602eb1ffb6 | Fresh Dental (60657) | solo_established | Evenly-only |
| 06559964fbcc65b8 | 176 DENTAL ASSOCIATES (Bloomingdale 60108) | small_group | Evenly-only; junk dso='General Dentistry' |
| cdcdf30342969078 | DENTAL HEIGHTS DDS PC (Glendale Hts 60139) | family_practice | 3 Bader brothers; Evenly-only |
| c0d81e7b77101c7a | Izzo Karen DDS (Norridge 60706) | small_group | "JLL PARTNERS" false-positive |
| 10350cbe9ba08042 | DRS. DELMONICO & TROCCHIO (Elmwood Pk 60707) | large_group | 9 providers; Evenly-only |
| 4cdf3ef029ab464c | Bender Dental Care (Elgin 60123) | solo_established | Evenly-only |
| 83edaeef42709b35 | ENVISION A SMILE (St Charles 60174) | solo_established | Evenly-only; junk dso='General Dentistry' |
| 541ae39cadc867b6 | MA BOULE DMD PC (Plano 60545) | solo_established | Evenly-only |

Two of these are the "uncertain → demote per floor principle" cases (no hard evidence =
not corporate; flag them `needs_reverification: true` in the audit file).

### KEEP corporate (3, verified):
- ce3f980988601d21 WHEATLAND SLEEP SOLUTION — UDP/Calera confirmed (app.nexhealth.com/appt/unitedentalpartners)
- c6078e6641ef7f48 CHICAGO DENTAL COSMETICS — now "Advanced Family Dental", UDP confirmed
- cedf0257b26ccce2 Oral Health Ctr Maywood — Loyola Medicine / TRINITY HEALTH (53 NPIs)

### Fresh verification (this session, just before checkpoint):
All 18 targets are currently `dso_regional` in SQLite. Per-location NPI counts (total/corp):
SUN 2/2, OAK BROOK 4/3, ZAIDI 3/3 (primary 1801428263 + ["1417641580","1124290671"]),
ARLINGTON HTS 6/6, FAVIA 1/1 (org NPI 1851083182), VIVIRITO 1/1, CITY 2/2, VETERANS 3/3,
BRIGHTON 2/2, ASIAN VILLAGE 2/2, FRESH 1/1, 176 DENTAL 3/3, DENTAL HEIGHTS 5/5, IZZO 3/3,
DELMONICO 10/10 (primary 1326179789), BENDER 1/1, ENVISION 2/2, MA BOULE 2/2.
Total corp NPIs attached to the 18 = **50** (sum above; flip the dso_* ones only).

### ⚠️ RE-PROMOTION HAZARD (discovered this session — must handle):
Seed-file membership check (xref_key vs `data/dso_research/il_dso_locations_merged.json` +
`il_dso_data_axle_verified.json`): **2 of the 18 ARE in the merged seed file** —
`58af66ee2bf4b9c6` (Arlington Heights Dental Group) and `e6ce96c5946ab89f` (Vivirito), both
under "All Family Dental & Braces (United Dental Partners)". If
`reclassify_verified_corporate_il.py` ever re-runs, it would RE-PROMOTE those two.
**Required:** the demotion script must write an exclusion file
(`data/dso_research/il_false_corporate_demotions_20260610.json`) AND
`reclassify_verified_corporate_il.py` must be patched to skip any location_id/xref_key
present in that file. (The 2 keepers in the seed file — ce3f98…, c6078e… — stay corporate, fine.)

### Script spec (write `scrapers/demote_false_corporate_il.py`):
1. DEMOTIONS dict from the table above (location_id → {new_ec, evidence}).
2. Assert each row currently dso_regional/dso_national; snapshot before-state into audit JSON.
3. UPDATE practice_locations: entity_classification=new_ec, ownership_status='independent',
   affiliated_dso=NULL, affiliated_pe_sponsor=NULL,
   classification_reasoning='False-corporate demotion 2026-06-10: <evidence>; was dso_regional
   (Evenly Technologies parent_iusa=000000000 placeholder / bad seed). Verified independent
   by web research.', classification_confidence=85, **updated_at=datetime('now')** (REQUIRED —
   raw sqlite3 bypasses ORM onupdate; stale updated_at breaks incremental sync).
4. Flip attached NPIs (primary_npi, org_npi, provider_npis JSON) WHERE practices.entity_classification
   IN ('dso_regional','dso_national') → location's new class; ownership_status='independent';
   updated_at bump. SPECIAL CASE: Favia org NPI 1851083182 → 'org_only_npi' (prov_cnt=0).
   NOTE: practices.entity_type values are STRINGS 'individual'/'organization'/None (not 1/2).
5. Recompute zip_scores for IL: corporate_location_count = COUNT(dso_* per zip from
   practice_locations); corporate_share_pct = **ROUND(1.0*n/total_gp_locations, 4)** —
   FRACTION scale (0–1). ⚠️ The promotion script's recompute uses `ROUND(100.0*...,2)` —
   that is a LATENT SCALE BUG (canonical scale per merge_and_score.py:470-472 is fraction).
   Fix it in `reclassify_verified_corporate_il.py` too (100.0 → 1.0, round 4).
6. Write audit file `data/dso_research/il_false_corporate_demotions_20260610.json`:
   demoted 18 (with evidence + before/after), kept 3 (with evidence), the 2
   needs_reverification flags, and the exclusion list for the re-promotion hazard.
7. `--dry-run` flag first; print BEFORE/AFTER floor. Idempotent (only touches dso_* rows).

### Expected outcome after demotion:
Floor 285 → **267** / 4,970 = **5.37%** (CHI 266→248/4,608 = 5.38%; BOS 19/362 unchanged).
NPI-row corporate 1,178 → ~1,128 (−50).

### Post-demotion follow-ups (same task):
- `scripts/check_data_invariants.py` FLOOR guard `expect_min` 285 → **267**.
- Recompute `CONFIRMED_PER_DENTIST_CORPORATE` (IL currently 824/7,792=10.57% in
  `dental-pe-nextjs/src/lib/constants/consolidation-honesty.ts`) using
  `practices` watched-IL `entity_type='individual'` corporate count / total individual
  dentists; update constant + the CorporateBandBar ASCII diagram comment if present.
- `npm run build` + F27 vitest.

---

## 5. REMAINING TASKS AFTER TASK #1

**Task #3 — Synthetic/junk record cleanup (addresses census-agent inflation verdict):**
- Purge/flag 163 DA_-only solo_inactive locations from the GP denominator (likely closed).
  Decide mechanism: either reclassify to a new excluded class or set a flag merge_and_score
  excludes from total_gp_locations. This SHRINKS the denominator → floor % rises (~5.5-5.7%).
- Review 135 DA_-only solo_high_volume (manual/heuristic).
- Fix `scrapers/data_axle_importer.py` Pass 6: ignore `parent_iusa='000000000'` placeholder
  (the Evenly root cause); ignore junk franchise/dso value 'General Dentistry'.
- 15 DA street-key duplicates; 32 'nan' string values (from earlier audit).
- After any denominator change: recompute zip_scores, re-check 20-ZIP off-by-one
  (Task #5: SUM(total_gp_locations)=4,970 spec vs observed slight variance — check
  merge_and_score GP definition).

**Task #4 — Supabase sync:**
- `practices` lags SQLite by 89 Phase-4 flips, will lag more after demotions (weekly full
  sync self-heals, or run `scrapers/fast_sync_watched.py`).
- After demotion + cleanup: run `scrapers/_sync_floor_tables_only.py` (zip_scores +
  practice_locations + dso_locations) and verify read-back.
- CLAUDE.md note "zip_signals 0 in Supabase" is STALE (actually 290 synced) — update docs.

**Task #5 — Frontend/docs cleanup (liveapp findings §2d):**
- data-snapshot.ts stale 2,992 constant; "NPI rows" mislabel on Market Intel; "Federal NPI
  records" + "NPI rows" mislabels on Job Market; getDealsBySource() missing BECKERS.
- Update root CLAUDE.md + dental-pe-nextjs/CLAUDE.md stale numbers (Supabase 1,089 not 875;
  zip_signals synced; new floor after demotions).
- Final: `npm run build`, commit everything (frontend fixes + demotion script + audit file +
  docs), push to main, verify Vercel deploy + live floor read-back.

---

## 6. KEY TECHNICAL FACTS (do not re-derive)

- `zip_scores.corporate_share_pct` & `buyable_practice_ratio`: 0–1 FRACTIONS (canonical,
  merge_and_score.py:470-472). Frontend `formatPercent()` expects 0–100 → display sites ×100.
- `reclassify_verified_corporate_il.py` line ~192 has the latent ×100 recompute bug.
- `practices.entity_type`: strings 'individual'/'organization'/None.
- NPI flip mechanics: practice_locations row carries primary_npi, org_npi, provider_npis
  (JSON array); update practices via those; always bump updated_at.
- dso_classifier Pass 3 only touches `entity_classification IS NULL` rows → demotions are
  durable against weekly refresh (same durability argument as the promotions).
- merge_and_score recomputes corporate_location_count FROM practice_locations — demotions
  survive it (it will see the demoted classes).
- xref_key from `scrapers.seed_il_dso_locations` is the address-match key for seed files.
- Floor CI guard: scripts/check_data_invariants.py, `Invariant` dataclass, `expect_min` field.
- Workflow run dir: /private/tmp/claude-501/-Users-suleman-dental-pe-tracker/6af2d387-c4e5-498c-9266-ab776f499b68/
- Full prior transcript: ~/.claude/projects/-Users-suleman-dental-pe-tracker/6af2d387-c4e5-498c-9266-ab776f499b68.jsonl

## 7. RESUME INSTRUCTIONS

Start in `/Users/suleman/dental-pe-tracker`. Read this file top to bottom, then:
1. Execute §4 (write + dry-run + apply `scrapers/demote_false_corporate_il.py`, patch
   reclassify script's scale bug + exclusion handling, FLOOR guard 285→267, per-dentist
   constant recompute, build + vitest).
2. Then §5 Task #3 → #5 in order.
3. Commit + push + sync + verify live, per §5 Task #5 final bullet.
