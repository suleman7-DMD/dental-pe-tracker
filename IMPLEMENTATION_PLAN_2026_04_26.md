# Implementation Plan — Dental PE Tracker
**Source:** `AUDIT_REPORT_2026-04-26_FULL.md` + `RECONCILIATION_VERDICT_2026_04_26.md` + Agent A–F sub-reports
**Compiled:** 2026-04-26
**Scope:** Every issue surfaced by the audit, converted to a discrete fix unit. Each fix names the file, the lines (where known), the change, and the verification step.

---

## How to Use This Document

1. Fixes are grouped by **priority** (P0 → P3) and within priority by **dependency order** (schema before data before sync before frontend before docs).
2. Each fix has a stable ID (`F##`) so you can reference it in commits, PRs, and TaskList items.
3. **Status** column tracks `[ ]` not started → `[~]` in progress → `[x]` shipped + verified.
4. **Verify** column is a runnable SQL query, shell command, or HTTP probe — not "test it manually."
5. Run fixes in ID order within a priority band unless explicitly marked independent.

---

## P0 — Data integrity bugs that produce wrong customer-facing numbers

### F01 — Split `solo_inactive` classifier into two distinct rules (B10)
| Field | Value |
|-------|-------|
| File | `scrapers/dso_classifier.py` (Pass 3 entity classification) |
| Bug | Single `solo_inactive` label covers both "no phone AND no website" (165 IL rows) AND "Organization NPI without individual providers" (561 IL rows, of which 157 have BOTH phone+website). |
| Impact | ~21% of `solo_inactive` rows (157/726 IL) are misclassified active practices. Drives wrong Buyability scoring, wrong Warroom Sitrep ranking, wrong reconciliation filters. Also cascades into `practice_signals.solo_inactive_flag` and Launchpad track scoring. |
| Change | (1) Add new entity_classification value `org_only_npi` to the 11-value enum (now 12). (2) Split the existing rule: if reasoning hits "Organization NPI registered but no individual providers at address" AND has phone or website, classify as `org_only_npi`. (3) Keep `solo_inactive` for the contact-less case only. (4) Update `INDEPENDENT_CLASSIFICATIONS` in `dental-pe-nextjs/src/lib/constants/entity-classifications.ts` to include `org_only_npi`. (5) Update `BUYABLE_TYPES` in `merge_and_score.py:357-390` to include `org_only_npi` (these are buyable like other independents). |
| Verify | `SELECT entity_classification, COUNT(*) FROM practice_locations WHERE state='IL' GROUP BY entity_classification` — `solo_inactive` ≤ 200 IL rows after fix; `org_only_npi` shows ~561 IL rows. Smoke-test SUKHJINDER THIND DDS now reads `org_only_npi`, not `solo_inactive`. |
| Status | [ ] |

### F02 — Stop hygienist NPIs (taxonomy 124Q*) from leaking into `practices` (B4)
| Field | Value |
|-------|-------|
| File | `scrapers/nppes_downloader.py:213-220` (`get_primary_taxonomy`), plus a one-shot SQL cleanup |
| Bug | 222 watched-ZIP rows have `taxonomy_code` like `124Q…` (hygienist), data_source=`nppes`. The `is_dental_row()` admit-filter checks all 15 NPPES taxonomy slots for `1223` prefix, but somewhere downstream the row's `taxonomy_code` is overwritten with the row's primary slot (which can be `124Q`). |
| Impact | 1.58% NPI-level inflation in watched scope; violates the `scrapers/CLAUDE.md` invariant *"NPPES taxonomy: Only `1223` prefix = Dentist."* |
| Change | (1) Audit which code path overwrites `taxonomy_code` post-import (search `practices.taxonomy_code` writes in `nppes_downloader.py`, `data_axle_importer.py`, `dso_classifier.py`). (2) Add a guard: never store `taxonomy_code` unless it starts with `1223`. (3) One-shot SQL: `UPDATE practices SET taxonomy_code = (first 1223 from secondary slots, if any) WHERE taxonomy_code NOT LIKE '1223%'` — but this requires the row's full 15-slot list, which we may not have stored. Realistic fix: `DELETE FROM practices WHERE taxonomy_code LIKE '124Q%' AND data_source='nppes'` (these were never supposed to land in `practices` anyway). |
| Verify | `SELECT COUNT(*) FROM practices WHERE taxonomy_code NOT LIKE '1223%' AND data_source='nppes'` → 0. Re-run NPPES import on a sample ZIP and confirm no 124Q rows enter. |
| Status | [ ] |

### F03 — Frontend Job Market map uses `ownership_status` instead of `entity_classification` (Agent D P0 BUG)
| Field | Value |
|-------|-------|
| File | `dental-pe-nextjs/src/app/job-market/_components/practice-density-map.tsx` |
| Bug | Map color-codes practices by `ownership_status`, but `ownership_status` is ~zero in SQLite/Supabase since the `dc18d24` location-dedup rewrite. Map renders monochrome or wrong colors. |
| Impact | Job Market's headline visualization shows wrong ownership distribution. Direct violation of CLAUDE.md's *"Entity classification is primary — ALWAYS use `entity_classification`, with `ownership_status` as fallback only when entity_classification is NULL."* |
| Change | Replace `ownership_status` reads with `classifyPractice(entity_classification, ownership_status)` from `src/lib/constants/entity-classifications.ts`. Color the map dots by the returned `'independent' \| 'corporate' \| 'specialist' \| 'non_clinical' \| 'unknown'` taxonomy. |
| Verify | `npm run build` clean. Open `/job-market` Map tab — corporate cluster around Aspen/Heartland addresses should show in red, independents in blue. Hex density layer should match Market Intel consolidation map color distribution. |
| Status | [ ] |

### F04 — Reset Sonnet escalation so two-pass research actually runs (B5)
| Field | Value |
|-------|-------|
| File | `scrapers/practice_deep_dive.py` (escalation gate) + `scrapers/intel_database.py::store_practice_intel()` |
| Bug | `SELECT COUNT(*) FROM practice_intel WHERE escalated=1` → 0 for ALL 2,013 rows. Either: (a) thresholds too strict, (b) `escalated` boolean is never set after Pass 2 merge, (c) Pass 2 never fires because the budget cap prevents it. |
| Impact | High-readiness practices never get Sonnet's deeper search. ~$50/run never spent (10% × 2013 × ~$0.20 marginal). Quality of dossiers for the most promising acquisition targets is depressed. |
| Change | (1) Add unit-test for the escalation predicate — feed a fake Pass 1 dossier with `readiness=high, confidence=medium`, assert it escalates. (2) Log every (npi, decision, reason) triplet in escalation gate so we can see why it never fires. (3) Verify `store_practice_intel()` actually persists `escalated=1` after a Pass 2 merge — check SQLAlchemy column write. (4) If thresholds are intentionally tight, document them in CLAUDE.md and lower the bar to `readiness IN (high, medium)` (no confidence requirement) to bootstrap a sample. |
| Verify | Re-run a small batch (`practice_deep_dive.py --zip 60657 --top 5 --deep`); `SELECT COUNT(*) FROM practice_intel WHERE escalated=1` → ≥ 1. Sample dossier should show `escalation_findings` populated and `model_used` containing `sonnet-4-6`. |
| Status | [ ] |

### F05 — Re-research the 186 DA_-prefix synthetic NPI dossiers (B6)
| Field | Value |
|-------|-------|
| File | `scrapers/dossier_batch/launch_DA_prefix_only.py` (NEW), reusing `engine.build_batch_requests` |
| Bug | 186 rows in `practice_intel` with `npi LIKE 'DA\_%' ESCAPE '\'` (Data-Axle-only synthetic NPIs) predate the 4-layer anti-hallucination defense. They have no `verification_searches`, no `verification_quality`, no per-section `_source_url`, were stored before `validate_dossier()` quarantine gate existed. |
| Impact | Up to 186 dossiers may contain hallucinated services/technology/reviews. Customer-facing on Intelligence + Launchpad pages. |
| Change | (1) Write a launcher that selects all 186 DA_-prefix NPIs. (2) Submit to Anthropic with the bulletproofed protocol (`force_search=True`, max_searches=5, evidence-protocol prompt). (3) `poll.py` already runs `validate_dossier()` — quarantined rows stay quarantined. (4) Replace the existing 186 rows in-place; the bulletproofed dossiers overwrite. (5) Budget: 186 × $0.008 ≈ $1.50. |
| Verify | After run, `SELECT COUNT(*) FROM practice_intel WHERE npi LIKE 'DA\_%' ESCAPE '\' AND verification_searches IS NOT NULL` should equal stored count. Quarantine rate should match the 87% stored / 13% quarantined of the 200-practice canonical run. |
| Status | [ ] |

### F06 — Push `zip_signals` to Supabase (sync gap) (CLAUDE.md noted)
| Field | Value |
|-------|-------|
| File | `scrapers/sync_to_supabase.py` runtime invocation |
| Bug | `zip_signals` has 290 rows in SQLite but **0 rows in Supabase** as of 2026-04-26. Warroom ZIP-level overlay (`ada_benchmark_gap_flag`, `deal_catchment_24mo`) is silent. |
| Impact | Warroom Investigate mode misses ZIP-level signal flags; Sitrep KPI strip undercounts contextual signals. |
| Change | Run `python3 scrapers/sync_to_supabase.py --tables zip_signals`. Confirm with read-back assertion (already in sync code via `_verify_table_count`). |
| Verify | After sync: query Supabase `SELECT COUNT(*) FROM zip_signals` → 290. Open `/warroom` and confirm ZIP-level signal flags render in Sitrep panel. |
| Status | [ ] |

---

## P1 — Pipeline correctness and security bugs

### F07 — Tighten `verification_quality` validation gate to reject enum drift (B2)
| Field | Value |
|-------|-------|
| File | `scrapers/weekly_research.py:147` (`validate_dossier`) |
| Bug | Gate only rejects `evidence_quality == 'insufficient'`. Non-spec values like `"high"`, `"verified - MISMATCH DETECTED"`, `"sufficient"`, `"insufficient_for_requested_classification"` slip through and persist. 14 such rows currently in `practice_intel`. |
| Impact | Schema invariant violated; downstream code that checks `if quality == 'verified'` misses the 10 `"high"` rows. |
| Change | Replace the `if quality == 'insufficient'` check with `if quality not in {'verified','partial','insufficient'}: return False, f'enum_drift:{quality}'`. Also tighten the system prompt in `research_engine.py` PRACTICE_USER schema to enumerate the 3 allowed values explicitly. One-shot SQL backfill: `UPDATE practice_intel SET verification_quality='partial' WHERE verification_quality='high'` (downgrade the 10 ambiguous rows; quarantine the 4 longer-string rows for re-research). |
| Verify | `SELECT DISTINCT verification_quality FROM practice_intel` returns exactly `{NULL, 'verified', 'partial', 'insufficient'}`. Run a fresh batch and confirm no new drift values appear. |
| Status | [ ] |

### F08 — Add GitHub Actions secret `SUPABASE_DATABASE_URL` for keep-alive (Agent A) + add freshness alarm (NEW)
| Field | Value |
|-------|-------|
| File | `.github/workflows/keep-supabase-alive.yml` + GitHub repo settings |
| Bug | The keep-alive workflow runs every 3 days but `SUPABASE_URL` and `SUPABASE_ANON_KEY` secrets are missing in GitHub repo settings, so the workflow no-ops. Free-tier Supabase will pause if no read activity for 7 days. |
| Impact | Risk of Supabase free-tier auto-pause. If it pauses, Vercel pages 500 across the board until manually unpaused. |
| Change | (1) User action: add the two secrets in GitHub Settings → Secrets and variables → Actions. (2) Add an alarm step: if response code != 200, send a webhook to a Discord channel or open a GitHub issue. (3) Cron remains `'0 12 */3 * *'`. |
| Verify | Run the workflow manually via `gh workflow run keep-supabase-alive.yml`. Inspect the run log — should see HTTP 200 from `/rest/v1/`. |
| Status | [ ] |

### F09 — Reactivate PESP scraper after Aug-2024 Airtable structural block (Agent A)
| Field | Value |
|-------|-------|
| File | `scrapers/pesp_scraper.py` |
| Bug | PESP shifted from HTML deal pages to an Airtable embed in Aug 2024. Our scraper assumes HTML and has been silently returning 0 deals for ~18 months. Estimated 540–1,440 missing PE deals. |
| Impact | Deal Flow page is missing nearly two years of PESP coverage. Several known deals (PE acquisitions of large IL/MA platforms) are absent. |
| Change | (1) Inspect the live Airtable embed — is there a public JSON endpoint, or does it require an API key? (2) If JSON: rewrite `pesp_scraper.py` to fetch the Airtable view JSON. (3) If API key required: switch to a manual CSV export workflow + an `pesp_csv_importer.py` that imports the CSV through the same dedup gate. (4) Document the new method in CLAUDE.md. |
| Verify | Deal count for date range Aug-2024 → present grows by ≥ 200. Spot-check 5 known PESP deals (e.g., MB2 Dental acquisitions in IL) appear in `deals` table. |
| Status | [ ] |

### F10 — Add hard timeout escape for ADSO scraper (Agent A)
| Field | Value |
|-------|-------|
| File | `scrapers/adso_location_scraper.py` |
| Bug | Already has `MAX_SECONDS_PER_DSO=300` and `MAX_SECONDS_TOTAL=1500` per April 2026 audit, BUT Agent A flagged that some DSO sites still escape via JavaScript-rendered iframes that the timeout doesn't cover (the page `requests.get` returns immediately, then the parser hangs on `BeautifulSoup` over malformed HTML). |
| Impact | Pipeline can still hang on certain DSOs; cron may not finish in its window. |
| Change | Wrap the parsing step in a `signal.alarm()` block (Unix-only) or a `concurrent.futures` thread with `.result(timeout=60)`. Log the timeout-skip event via `pipeline_logger`. |
| Verify | Synthetic test: parse a 100MB nested-iframe HTML file → returns within 60s with skip event logged. Production run: total ADSO step ≤ 25 min. |
| Status | [ ] |

### F11 — Backfill `practice_changes` ON DELETE CASCADE in Supabase (Agent E referenced indirectly via Agent A bug fix table) — verify still in place
| Field | Value |
|-------|-------|
| File | Supabase Postgres schema (no local file; use `supabase` CLI or a migration script) |
| Bug | The April 2026 audit fix moved `_sync_watched_zips_only` to use `TRUNCATE TABLE practices CASCADE` to dodge the `practice_changes_npi_fkey` (ON DELETE NO ACTION) error. CASCADE works on Postgres, but only because the FK is set to ALLOW cascade. Verify the FK definition still has `ON DELETE CASCADE` (or NO ACTION + the sync still uses TRUNCATE CASCADE). |
| Impact | If the FK definition has drifted, the next watched-zip sync will throw `ForeignKeyViolation` and abort. |
| Change | Run `SELECT confdeltype FROM pg_constraint WHERE conname='practice_changes_npi_fkey'`. If `c` (CASCADE) — fine. If `a` (NO ACTION) — keep relying on TRUNCATE CASCADE in `_sync_watched_zips_only` and document this dependency in `sync_to_supabase.py` as a comment. |
| Verify | Trigger a watched-zip sync and confirm it completes without FK errors. |
| Status | [ ] |

### F12 — Re-deploy frontend after env var changes (no concrete file, but operational)
| Field | Value |
|-------|-------|
| File | Vercel project env vars |
| Bug | `ANTHROPIC_API_KEY` must be set in Vercel for `/api/launchpad/compound-narrative` to work. UNKNOWN whether it's currently set in Production + Preview + Development. |
| Impact | Without it, the route returns `503: Compound narrative disabled`, breaking the Launchpad thesis card. |
| Change | (1) Check Vercel dashboard. (2) If missing in any env, add it and redeploy. (3) Add a CI check: a smoke test that hits `/api/launchpad/compound-narrative` after each deploy and asserts it doesn't 503. |
| Verify | `curl -s 'https://dental-pe-nextjs.vercel.app/api/launchpad/compound-narrative?npi=...&track=...' | jq .` returns `narrative` field, not `error`. |
| Status | [ ] |

---

## P2 — Doc drift and data-quality issues

### F13 — Replace 287 synthetic `zip_qualitative_intel` placeholders (B7)
| Field | Value |
|-------|-------|
| File | `scrapers/qualitative_scout.py` invocation + `data/dental_pe_tracker.db` |
| Bug | 287/290 ZIPs have synthetic placeholder rows (`cost_usd=0`, `model_used=NULL`). Only 3 ZIPs have real research. |
| Impact | Intelligence page implies broad coverage that doesn't exist. KPIs overstate. |
| Change | Two-step. (1) Add a `is_synthetic` boolean column to `zip_qualitative_intel` (`ALTER TABLE` on both SQLite + Supabase). (2) Mark the 287 placeholders `is_synthetic=1`. (3) Update `getZipIntel()` and `getIntelStats()` queries in `dental-pe-nextjs/src/lib/supabase/queries/intel.ts` to default-filter `is_synthetic=0`. (4) Background batch: `python3 scrapers/qualitative_scout.py --metro chicagoland` to fill real research progressively, $5/run × ~58 runs = $290 over time, OR raise budget cap and do it in one $80–100 batch. |
| Verify | Intelligence page shows "3 ZIPs researched (287 pending)" honestly. Setting filter to "include synthetic" reveals all 290. |
| Status | [ ] |

### F14 — Refresh `dental-pe-nextjs/CLAUDE.md` "5,265 GP clinics" headline (B3)
| Field | Value |
|-------|-------|
| File | `dental-pe-nextjs/CLAUDE.md` |
| Bug | Headline says "5,265 GP clinics" — predates `dc18d24` location dedup. Live count is 4,889 watched (4,575 CHI + 314 BOS). |
| Impact | Future agents read 5,265 from doc, get confused when SQL returns 4,889, waste cycles re-deriving. |
| Change | Update headline + every count cite. Add a note: "This count was 5,265 prior to the `dc18d24` ULTRA-FIX dedup; current canonical = 4,889 (CHI 4,575 + BOS 314)." |
| Verify | `grep -n "5,265\|5265" dental-pe-nextjs/CLAUDE.md` returns 0. |
| Status | [ ] |

### F15 — Refresh `CLAUDE.md` watched_zips count to 269 IL + 21 MA = 290 (B9)
| Field | Value |
|-------|-------|
| File | `CLAUDE.md` line 17 |
| Bug | Says "268 expanded ZIPs across 7 sub-zones." Live SQLite = 269 IL Chicagoland + 21 MA Boston Metro. No outlier exists. |
| Change | Replace "268 expanded ZIPs" → "269 expanded ZIPs". Remove "+ 1 other" from the watched_zips description. |
| Verify | `grep "268 expanded" CLAUDE.md` returns 0. `grep "1 other" CLAUDE.md` returns 0. |
| Status | [ ] |

### F16 — Refresh `dso_classifier.py` line count + 3-pass docs (Agent F)
| Field | Value |
|-------|-------|
| File | `CLAUDE.md` Pipeline File Quick Reference table |
| Bug | Says `dso_classifier.py | 547 | …`. Real file is 1,570 lines. Pass-3 doc claims it queries `practice_locations` (per `889edc2`) but the live code queries `practices`. The location-level rewrite is in `reclassify_locations.py` (separate script, not run by pipeline). |
| Change | Update line count. Either (a) make `dso_classifier.py` Pass 3 actually query `practice_locations` and run `reclassify_locations.py` logic in-process, OR (b) document that Pass 3 still operates on `practices` and the location-level rewrite is a manual cleanup script that must be run separately. Pick (a) for consistency. |
| Verify | `wc -l scrapers/dso_classifier.py` matches CLAUDE.md figure. Run Pass 3 → `practice_locations.entity_classification` is updated, not just `practices.entity_classification`. |
| Status | [ ] |

### F17 — Document `_reconcile_deals` does not exist; preserve cleanup intent (B8)
| Field | Value |
|-------|-------|
| File | `scrapers/merge_and_score.py` + `CLAUDE.md` |
| Bug | CLAUDE.md and `ac2140a` commit message reference `_reconcile_deals` function. Function not present in 1,074-line file. The 25-row ghost cleanup it documented was a one-off SQL. |
| Change | Either (a) add the function back as a re-runnable cleanup, OR (b) rename CLAUDE.md reference to `_reconcile_deals_one_off_sql_run` and link the actual SQL inline. Pick (a) so future drift can be cleaned. Implementation: a function that finds Supabase deal rows missing in SQLite (by composite key platform_company+target_name+deal_date) and DELETEs them with a dry-run flag. |
| Verify | `grep "def _reconcile_deals" scrapers/merge_and_score.py` → 1 match. Dry-run print shows the +34 ghost rows currently drifted in Supabase. |
| Status | [ ] |

### F18 — Update doc counts: 6 KPI cards on Home, 7 nav cards, 6 Launchpad dossier tabs (Agent D)
| Field | Value |
|-------|-------|
| File | `CLAUDE.md` |
| Bug | Doc says 8 KPIs / 6 nav / 5 dossier tabs. Live = 6 / 7 / 6. |
| Change | Search-and-replace in CLAUDE.md. |
| Verify | Manual count of live `/` page matches doc. |
| Status | [ ] |

---

## P3 — Polish, hardening, and tech debt

### F19 — Apostrophe normalization for GDN scraper dedup (April 2026 audit, "Known Limitations")
| Field | Value |
|-------|-------|
| File | `scrapers/gdn_scraper.py` |
| Bug | "Smith's Dental" (U+2019 right single quote) and "Smith's Dental" (U+0027 ASCII) deduplicate as different entities. |
| Change | Add a Unicode NFKC normalization + curly-quote → straight-quote substitution before fuzzy-match dedup. |
| Verify | Test case: pass two practice names that differ only by curly quote to `_normalize_address_for_grouping` — they collapse to one. |
| Status | [ ] |

### F20 — Backfill `ada_hpi_benchmarks.updated_at` (April 2026 audit, "Known Limitations")
| Field | Value |
|-------|-------|
| File | `scrapers/ada_hpi_importer.py` |
| Bug | All 918 rows have `updated_at = NULL`. System page reads `created_at` as a workaround. |
| Change | In the importer, set both `created_at` and `updated_at` on every UPSERT. Backfill: `UPDATE ada_hpi_benchmarks SET updated_at = created_at WHERE updated_at IS NULL`. |
| Verify | `SELECT COUNT(*) FROM ada_hpi_benchmarks WHERE updated_at IS NULL` → 0. System page freshness card no longer needs the fallback. |
| Status | [ ] |

### F21 — Fix GDN parser "Partners" lookahead ambiguity (April 2026 audit, "Known Limitations")
| Field | Value |
|-------|-------|
| File | `scrapers/gdn_scraper.py::extract_platform()` |
| Bug | `partners/partnered/partnering` are in `_DEAL_VERB_SET` as verbs, so entity names ending in "Partners" (e.g., "Zyphos & Acmera Dental Partners") get truncated. KNOWN_PLATFORMS catches the common cases but missed multi-word entity names. |
| Change | Add a lookahead: if the word after "Partners" is "with" → it's a verb; if it's a noun ("acquires", "of", end-of-sentence) → it's part of an entity name. |
| Verify | Re-parse the 5 known truncation examples; entity names extract intact. |
| Status | [ ] |

### F22 — Cleanup `dental-pe-nextjs/scrapers/` deprecated mirror (April 2026 audit, "Known Limitations")
| Field | Value |
|-------|-------|
| File | `dental-pe-nextjs/scrapers/` directory |
| Bug | Mirror copies of scrapers exist with DEPRECATED markers, but the directory is gitignored — markers are stranded on local disk. Cron reads from `/scrapers/`, so this isn't actively harmful, but it's a confusion vector. |
| Change | `rm -rf dental-pe-nextjs/scrapers/`. Add the directory back to `.gitignore` if it's not already (so a future re-creation doesn't sneak into git). |
| Verify | `ls dental-pe-nextjs/scrapers/` → "No such file or directory". Cron still runs from `/scrapers/`. |
| Status | [ ] |

### F23 — Make `/tmp/full_batch_id.txt` durable (April 2026 audit, "Known issues")
| Field | Value |
|-------|-------|
| File | `scrapers/dossier_batch/launch.py` + `scrapers/dossier_batch/poll.py` |
| Bug | `launch.py` writes the batch ID to `/tmp/full_batch_id.txt`; `poll.py` reads it. `/tmp` is wiped on macOS reboot, so the cross-process handoff is fragile. |
| Change | Pass `batch_id` as a CLI arg to `poll.py`, OR write to `data/last_batch_id.json` (gitignored but persistent). |
| Verify | After a reboot, `poll.py` can still find the in-flight batch. |
| Status | [ ] |

### F24 — Make SQLite `ALTER TABLE` migration idempotent (April 2026 audit, "Known issues")
| Field | Value |
|-------|-------|
| File | `scrapers/dossier_batch/migrate_verification_cols.py` (or new sibling for SQLite) |
| Bug | SQLite has no `ADD COLUMN IF NOT EXISTS`. Re-running the migration fails with "duplicate column". |
| Change | Wrap each `ALTER TABLE` in `try: cursor.execute(stmt); except sqlite3.OperationalError as e: if 'duplicate column' not in str(e): raise`. |
| Verify | Run migration twice in a row → second run is a no-op, no exception. |
| Status | [ ] |

### F25 — Bump hardcoded `$11` cost cap in `launch.py` to a configurable budget arg (April 2026 audit, "Known issues")
| Field | Value |
|-------|-------|
| File | `scrapers/dossier_batch/launch.py` |
| Bug | Cost cap is hardcoded to `$11`. `launch_2000_excl_chi.py` raised it to `$250` by forking the file — copy-paste maintenance debt. |
| Change | Replace hardcoded `11` with `argparse.add_argument('--budget', type=float, default=11.0)`. Delete `launch_2000_excl_chi.py` once the param is in. |
| Verify | `python3 launch.py --budget 250` runs the same flow as the old fork. |
| Status | [ ] |

### F26 — Remove `mirror DEPRECATED` markers in scraper files if any (Agent F)
| Field | Value |
|-------|-------|
| File | `scrapers/*.py` |
| Bug | Some DEPRECATED docstrings reference removed mirror dirs. |
| Change | `grep -rn "DEPRECATED" scrapers/` and remove stale markers. |
| Verify | No "DEPRECATED" tokens remain except for ones tied to active code paths. |
| Status | [ ] |

---

## Cross-Cutting Quality Improvements (No Single File)

### F27 — Add a smoke-test for entity_classification primary usage across frontend
| Field | Value |
|-------|-------|
| File | `dental-pe-nextjs/src/__tests__/classification-primary.test.ts` (NEW) |
| Bug | F03 surfaced one bug; there may be others where `ownership_status` is read directly without falling back through `classifyPractice()`. |
| Change | Write a grep-test: scan `src/**/*.{ts,tsx}` for direct `ownership_status` reads not wrapped in `classifyPractice()`. Fail the test if any are found outside `classifyPractice()` itself + entity-classifications.ts. |
| Verify | `npm test` passes. |
| Status | [ ] |

### F28 — Add CI check that runs the audit's reconciliation queries on every push
| Field | Value |
|-------|-------|
| File | `.github/workflows/data-invariants.yml` (NEW) |
| Bug | Several invariants (no 124Q in `practices`, no enum drift in `verification_quality`, all 290 zip_scores agree with practice_locations rollup) silently regress without alarms. |
| Change | A weekly workflow that runs the verification queries from this plan against Supabase and fails if any return non-zero drift. |
| Verify | First run reports green or pinpoints which invariants are broken. |
| Status | [ ] |

### F29 — Document the canonical IL active-GP count derivation
| Field | Value |
|-------|-------|
| File | `CLAUDE.md` + `RECONCILIATION_VERDICT_2026_04_26.md` |
| Bug | The 4,574 IL GP / 4,409 active-GP / 14% surplus-vs-Dentagraphics derivation is currently in this audit doc only. New agents won't find it. |
| Change | Cross-link from CLAUDE.md to the reconciliation doc. Add a "Numbers cheat-sheet" section: NPI rows, watched locations, IL GP, IL active GP, gap to Dentagraphics. |
| Verify | A new agent can answer "what's the IL clinic count and how does it reconcile to Dentagraphics" in one read. |
| Status | [ ] |

### F30 — Read Dentagraphics methodology + close the 13–17% gap definitively
| Field | Value |
|-------|-------|
| File | `RECONCILIATION_VERDICT_2026_04_26.md` (update §3) |
| Bug | We don't know if the 4,574 vs 3,900 gap is our error or methodology difference. |
| Change | (1) Fetch Dentagraphics's published methodology page (or contact them). (2) Run a sample-level overlap test: pick 200 named IL practices and check which are in both datasets. (3) Quantify asymmetric exclusions. (4) Update §3 with the resolved verdict. |
| Verify | We can either (a) say "we match within X%" with confidence, or (b) say "we have N ghost rows in `practice_locations`, here's the cleanup script." |
| Status | [ ] |

---

## Summary Table

| ID | Title | Priority | File | Effort* |
|----|-------|----------|------|---------|
| F01 | Split `solo_inactive` into `solo_inactive` + `org_only_npi` | P0 | dso_classifier.py | M |
| F02 | Block hygienist 124Q leak | P0 | nppes_downloader.py | S |
| F03 | Frontend Job Market map → entity_classification | P0 | practice-density-map.tsx | S |
| F04 | Reset Sonnet escalation | P0 | practice_deep_dive.py | M |
| F05 | Re-research 186 DA_-prefix dossiers | P0 | dossier_batch/ | S + ~$1.50 |
| F06 | Push zip_signals to Supabase | P0 | sync_to_supabase.py invocation | XS |
| F07 | Tighten verification_quality gate | P1 | weekly_research.py | S |
| F08 | GHA secrets + freshness alarm | P1 | .github/workflows/ | S |
| F09 | Reactivate PESP scraper | P1 | pesp_scraper.py | L |
| F10 | ADSO hard timeout escape | P1 | adso_location_scraper.py | M |
| F11 | Verify CASCADE on practice_changes_npi_fkey | P1 | Supabase schema | XS |
| F12 | Re-deploy with ANTHROPIC_API_KEY | P1 | Vercel env | XS |
| F13 | Replace 287 synthetic zip_qualitative_intel | P2 | qualitative_scout.py | M + ~$80 |
| F14 | Refresh "5,265 GP" doc | P2 | dental-pe-nextjs/CLAUDE.md | XS |
| F15 | Refresh "268 ZIPs" doc → 269 | P2 | CLAUDE.md | XS |
| F16 | dso_classifier.py line count + Pass 3 location query | P2 | dso_classifier.py + CLAUDE.md | M |
| F17 | Restore `_reconcile_deals` function | P2 | merge_and_score.py | S |
| F18 | Doc counts (KPIs, nav, dossier tabs) | P2 | CLAUDE.md | XS |
| F19 | GDN apostrophe normalization | P3 | gdn_scraper.py | S |
| F20 | Backfill ada_hpi_benchmarks.updated_at | P3 | ada_hpi_importer.py | XS |
| F21 | GDN "Partners" lookahead | P3 | gdn_scraper.py | S |
| F22 | Cleanup deprecated mirror | P3 | dental-pe-nextjs/scrapers/ | XS |
| F23 | Durable batch_id handoff | P3 | dossier_batch/ | S |
| F24 | Idempotent SQLite migration | P3 | dossier_batch/migrate*.py | XS |
| F25 | Configurable budget arg | P3 | dossier_batch/launch.py | XS |
| F26 | Remove DEPRECATED markers | P3 | scrapers/*.py | XS |
| F27 | Test for entity_classification primary | Quality | __tests__/ | M |
| F28 | CI invariant check | Quality | .github/workflows/ | M |
| F29 | Document canonical IL count | Quality | CLAUDE.md | XS |
| F30 | Close Dentagraphics gap | Quality | (research) | M |

*Effort buckets are coarse: XS=<30min, S=30min-2hr, M=2-6hr, L=>6hr. They're a relative sense, not a timeline.

---

## Suggested Sequencing (one possible order)

**Phase 1 — Stop the bleeding (P0 first, do all in parallel):** F03 (frontend map), F06 (zip_signals sync), F12 (Vercel env), F02 (hygienist purge SQL), F07 (varchar gate tighten + 14-row backfill).
**Phase 2 — Fix the data (P0 cont'd):** F01 (classifier split — this is the biggest single change). After F01 ships, re-run `merge_and_score.py` + Supabase sync.
**Phase 3 — Plug research holes (P0 cont'd):** F04 (Sonnet escalation reset), F05 (DA_ re-research).
**Phase 4 — Pipeline correctness (P1):** F09 (PESP), F08 (GHA secrets), F10 (ADSO timeout), F11 (FK verify).
**Phase 5 — Doc + polish (P2 + P3):** Batch-update all doc fixes (F14, F15, F16, F17, F18) in one PR. Then P3 polish in a second PR.
**Phase 6 — Quality moat (Quality bucket):** F27, F28, F29, F30 — automate the invariants so they never regress.

Each phase ships a self-contained PR. Each fix has a discrete commit.

---

## What this plan does NOT include

- Performance work (Supabase query timeouts beyond the warroom chunking already shipped in `9e3375c`)
- New features (no scope expansion)
- Refactors that aren't tied to a fix
- Tests for code that's already passing — only invariants for things that have regressed

If a fix above turns out to be larger than its effort estimate, **stop and re-scope rather than expanding silently.** The audit's job is to surface honestly; the plan's job is to fix decisively.
