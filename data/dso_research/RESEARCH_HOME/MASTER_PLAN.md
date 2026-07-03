# MASTER PLAN — Chicagoland Ownership Census

The integrated execution plan for Goal 2. Supersedes `../../CHICAGOLAND_FLOOR_PLAN_2026-06-20.md` (kept verbatim for history; its §9 ADA-anchor framing is **revised away** per the no-anchor rule). Read `README.md` first for the model + binding rules.

**Strategy = LIFT, THEN CENSUS** (user choice): verify+promote the high-signal candidate pools first (fast, defensible coverage), then grind the full ~4,439 per-practice census across sessions until every location is tiered or Undetermined. Both feed ONE LEDGER. **All of Phases 1+ are gated on user sign-off** ("plan first, don't flip yet"); Phase 0 (this scaffold) is additive docs only and is DONE.

---

## Phase 0 — Research home scaffold ✅ DONE (this session)
README, MASTER_PLAN, PROGRESS.json, LEDGER.jsonl, CENSUS_PROTOCOL, FINDINGS, SESSION_LOG written. No DB/app/commit change. The cross-session operating system now exists.

## Phase 1 — Denominator audit (gate before any flip)
Local read-only audit artifacts already exist, but the duplicate count must be reconciled before any collapse.
- `data/dso_research/il_denominator_pressure_test_20260620.json` found an upper-bound pressure-test of 87 duplicate excess rows / 79 clusters.
- `data/dso_research/denominator_audit_20260620.json` flags 48 exact ZIP+phone+street-core suite-variant candidates / 48 excess rows.
- No denominator collapse is authorized until those files are reconciled row-by-row. Do NOT collapse the Naperville Ashton pair.
- Reconcile `org_only_npi` vs `solo_established` disagreements at location level.
- Re-confirm `zip_scores.total_gp_locations` IL sum = 4,439 with the dedup applied.
- Output: `data/dso_research/denominator_audit_YYYYMMDD.json`. No classification flips here.

## Phase 2 — Schema migration (the spine)
- Local SQLite already has `ownership_tier`, `pe_backed`, `ownership_evidence_basis`, `ownership_evidence_urls`, `ownership_confidence`, `network_id`, and ownership-tier indexes on BOTH `practices` and `practice_locations`; values are currently NULL. Supabase/frontend status must be verified before production use.
- If running a migration later, it must be idempotent and must not overwrite values. Do not run `scrapers/migrate_ownership_tier_cols.py` in research-only mode without explicit approval.
- Keep `entity_classification` untouched (size axis; F27 vitest stays green).
- Add `classifyTier()` + T1–T6 arrays to `entity-classifications.ts`, but keep **Layer-1 structural output as candidate metadata only**: solo/family -> T1 candidate, small/large_group -> T2 candidate, dso_regional -> T4 candidate, dso_national -> T5 candidate. Do **not** assign these as final `ownership_tier` values without evidence. Unreviewed rows ship as `undetermined` until earned through the protocol.

## Phase 3 — LIFT: verify the candidate pools into the LEDGER (the fast coverage)
Order per `CENSUS_PROTOCOL` batch order. In research mode, each verified practice writes **LEDGER + evidence JSON only**. DB `ownership_tier` population is a separate post-sign-off mutation step.
- **D1 brand-tagged PE pool** → mostly T4/T5 (`pe_backed=true`), locator-confirmed. Investigate the Pass-3 escalation gate first.
- **D2 authorized-official clusters** (de-chained discoverer) → T3 dentist-owned multi-location or T4 stealth DSO depending on web/PE evidence; AO/mailing is discovery + confidence, not automatic promotion.
- **D3 name-chains** → corroborate D2.
- **`practice_intel` mine** — harvest owner/brand names from the 2,069 existing dossiers before any web call.
- Use existing candidate builders (`build_census_batches.py`, `build_ownership_census.py`, `consolidate_census.py` only after mutation approval) carefully: current `build_ownership_census.py` output is known flawed if transitive; `consolidate_census.py` is write-capable and currently rewrites `PROGRESS.json` with stale key names. Build or repair `scrapers/discover_owner_clusters.py` (de-chained, pair-level) so discovery is reproducible, not session-bound.

## Phase 4 — CENSUS: the zero-corp + long-tail sweep (the grind)
- Sweep all 269 ZIPs, dense zero-corp first (60614, 60622, 60068 …; 119 ZIPs / 1,457 locations). Each location through the full A–G ladder. Expect mostly T1/T2 but catch missed T3/T4.
- Earn every T1 (verified single-owner single-location). Ambiguous → Undetermined.
- Heartbeat discipline: update `PROGRESS.json` coverage + tallies and append `SESSION_LOG.md` every session. Log every ZIP swept (no silent caps).

## Phase 5 — Pipeline metric emit (durable, census-derived)
- Extend `merge_and_score.py` to emit `consolidated_location_count` (T2+T3+T4+T5) and `dso_pe_location_count` (T4+T5) per ZIP, recomputed FROM `practice_locations.ownership_tier` weekly (same durability invariant as the floor). Add per-tier shares.
- CI guard: `ownership_tier` coverage never silently drops; tier counts monotone unless an evidence file documents a demotion.

## Phase 6 — Frontend revamp (NO ANCHOR)
- **Remove** the floor→ADA band device (`consolidation-honesty.ts` `getCorporateBand`/`CorporateBandBar`, the `ada_hpi_benchmarks` anchor presentation). Replace with a **census readout**: two headline numbers (Consolidated %, DSO/PE %) + a **coverage/confidence meter** ("based on N of 4,439 reviewed, Y%") + explicit Undetermined %.
- Build the **directory view**: every IL GP practice with its tier, owner/network, pe_backed badge, evidence link. The 6-tier hierarchy is the primary lens.
- **Tier-number remap:** old analyst notes may say "T3 stealth DSO / T4 branded DSO." In this RESEARCH_HOME model, `T3=dentist_multi`, `T4=stealth_dso`, `T5=branded_dso`, `T6=institutional`. Frontend copy and code must use the locked names, not stale analyst numbering.
- **Fix the known display bugs precisely:**
  - `market-intel/_components/consolidation-map.tsx`: tooltip must not use `zip_scores.independent_count` beside location-deduped totals. That legacy field comes from older ownership-status logic, not the current GP-location denominator. Use `total_gp_locations - corporate_location_count` (or tier-derived counts once emitted).
  - Same map fallback path: do not compute a location percent from `dso_affiliated_count + pe_backed_count` NPI-row counts. If a ZIP lacks saturation metrics, show unknown/needs recompute rather than mixing units.
  - `market-intel/_components/market-intel-shell.tsx`: sub-metro independent % must not sum `zip_scores.independent_count` over a GP-location denominator. All-Chicagoland already uses live `practice_locations`; make sub-metro use the same unit path or compute independent as denominator minus corporate/tier counts.
  - Launchpad KPI copy: current Launchpad query uses `practice_locations`; do not label `summary.totalPracticesInScope` as raw federal NPI rows.
  - ZIP dossier percent scale rule: `corporate_share_pct` and `buyable_practice_ratio` are fractions and need `* 100`; `independent_pct_of_total`, `consolidation_pct_of_total`, and `pct_unknown` are stored as percent values and must not be multiplied again.
- **Map semantics:** Market Intel consolidation points are ZIP centroids; Job Market practice dots may be exact coordinates or ZIP-centroid jitter; Launchpad/Warroom dots vary by coordinate source. Default broad density analysis to hex/bin views where appropriate and label approximate/jittered point layers.
- **Filter from view = IL only:** `getWatchedZips()` + `getDistinctMetroAreas()` get or preserve `.eq("state","IL")`; `zip-scores.ts` and `practice-locations.ts` stay IL-scoped for Goal 2. MA stays in DB, never shown.

## Phase 7 — Sync, CI, verify-live
- Sync via `_sync_floor_tables_only.py` + `_sync_practices_changed_rows.py --since DATE` (+ new tier columns). NEVER `--tables practices` alone.
- Read-back verify Supabase = SQLite. Re-base CI guards. Playwright-verify the live app shows the census readout + directory.

---

## Sequencing note
Phase 1+2 are prerequisites and can run together. Phase 3 (lift) and Phase 4 (census) interleave — both append to the same LEDGER; lift front-loads defensible coverage, census guarantees completeness. Phases 5–7 productionize whatever the LEDGER holds and re-run as coverage grows. The census is never "blocked" on the frontend — the LEDGER is the deliverable; the app reflects it.
