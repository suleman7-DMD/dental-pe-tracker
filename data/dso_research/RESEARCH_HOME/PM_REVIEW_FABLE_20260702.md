# PM Review — Fable, 2026-07-02

Author: Fable (incoming project lead)
Scope: Full technical + methodology review of the Chicagoland ownership-census work, per the retiring PM's handoff (`PROJECT_MANAGER_HANDOFF_20260702.md`).
Method: Direct verification of frozen state + four parallel investigation lanes (backend/validator, workflow/evidence, frontend/live-app, denominator quality), all run on Fable. This document supersedes the strategy sections of the 2026-07-02 Codex handoff where they conflict; the handoff's artifact map and audit-trail rules remain current.

---

## 0. Decision

**MODIFY the current `ownership_tier` path — do not redesign it, do not continue it as-is.**

- KEEP: the two-axis data model (`entity_classification` legacy detector vs `ownership_tier` earned census), the T1–T6 tier taxonomy, the fail-closed `consolidate_census.py` validator, the evidence bar for T4/T5, the QA artifacts as immutable audit trail.
- REPLACE: the human-courier 4-session orchestration, per-row adversarial QA on low-risk rows, broad Fleet B fan-out, files-only state that never lands in the DB.
- ADD: two hard blockers fixed (ORM columns, Supabase migration verification), validator URL-format check, a denominator closure pass (free — data already in DB), a deterministic classification funnel (locator verifier + practice_intel T1 pass + queue generator), and frontend census-coverage semantics before anything is published.

Verified frozen state on 2026-07-02 (matches handoff exactly): DB md5 `e2a89a02900d0366fad6d9ee06d23422`, `ownership_tier` 0/0 both tables, LEDGER 1 line, PROGRESS 0 reviewed / 4,439 undetermined, 310-row ready file validates clean.

---

## 1. Strategy assessment

**The evidence methodology is sound. The delivery mechanism is not.**

Evidence quality — verified, not assumed:
- Both Wave-4 QA verdicts are substantive (formal AB/HB/AH rule bars, bucket reconciliation to the row, set-membership proofs against the 310, independent verification of the +1 Dentologie corporate claim). Not rubber stamps.
- All 20 merge-eligible Wave-4 rows and both Fleet B 51–100 merge candidates carry transcribed exact-address locator URLs.
- The Wave-1 quarantine (349 rows written to the DB with weak `name_chain`-basis promotions, 92 unverified T2s, 177 fast-pattern T1s) proves the evidence bar is necessary, not bureaucratic.

Throughput — fatal at current pace:
- Distinct location_ids touched by ANY review across all artifacts: **618 of 4,439 (13.9%)** after ~2 weeks of 4-session work plus one full reset.
- Net-new merge-eligible output of the June 21–22 sprint: **20 rows in 2 days**. Linear extrapolation to the remaining 3,821: **~13 months**. Not viable.
- Cost drivers, in order: (1) human copy-paste relay between sessions (~8–10 context switches per merged row), (2) the Wave-1 reset destroying weeks of work, (3) Gate-normalization as a serial bottleneck (Fleet B 51–100 delivered June 22, still un-normalized on July 2), (4) doc sprawl (7 competing "start here" files), (5) full adversarial QA applied identically to a +1 DSO promotion and a trivial brand-substring rejection.

Fleet B yield curve confirms the handoff's "stop fan-out" call: ranks 51–100 produced 2 merge candidates and 25 rejections; the remaining pool is 52 brand_chain-only + 3 brand_chain+keyword rows. Continuing 101+ as-is would be waste.

**The single highest-leverage untapped asset:** `practice_intel` dossiers cover 2,069 IL GP locations (46.6%) and are ignored by the current protocol, which treats fresh per-location web search as the primary method. A scripted pass over existing dossiers can (a) resolve a large share of solo-practice T1 confirmations and (b) surface ~192 already-documented closures.

---

## 2. Codebase findings (blockers and defects)

### Blockers — must fix before any `--allow-db-write`

1. **ORM models missing ownership columns** (`scrapers/database.py`): `PracticeLocation` (~lines 968–1005) and `Practice` (~line 112) do not declare the 6 ownership columns (`ownership_tier`, `pe_backed`, `ownership_evidence_basis`, `ownership_evidence_urls`, `ownership_confidence`, `network_id`) even though SQLite has them. `sync_to_supabase.py` enumerates columns via ORM mapper introspection (`_get_column_names` / `_model_to_dict`), so every sync would **silently strip ownership data** before it reaches Supabase. The census would never appear on the live app, and no error would fire.
2. **Supabase columns unverified**: `migrate_ownership_tier_cols.py` only runs its Postgres leg when `SUPABASE_DATABASE_URL`/`DATABASE_URL` is set; no artifact proves it ever ran against live Supabase. Verify via `information_schema.columns` or run the migration before any sync.

### High-priority defects

3. **Validator accepts prose as evidence URLs** (`consolidate_census.py` ~135–138): any non-empty `evidence_urls` list passes. The 310 file contains **47 prose strings** in URL fields plus bare domains (e.g. `sonrisadental.net`). Add a URL-format check; move prose to `evidence_artifacts`/notes.
4. **Audit-vulnerable DSO rows in the 310**: 7 `branded_dso` rows on `structural` basis and 61 DSO-tier rows on `name_chain` basis (all with artifacts, so they pass, but they are the weakest promotions in the file). PM spot-review before write.

### Medium/low

5. `consolidate_census.py` (~243–250) propagates tiers to `practices` only via `primary_npi`/`org_npi`, not the full `provider_npis` array — acceptable, but document it.
6. Manifest buckets live under `manifest["buckets"]`, not top-level — a future queue generator must read the right path.
7. The LEDGER's "PROGRESS schema mismatch — do not run consolidate_census.py" warning is **stale/resolved**: current script reads/writes exactly the current PROGRESS.json structure; validate-only runs clean with zero writes (re-verified today).

### Positives

- `consolidate_census.py` is genuinely fail-closed: never touches `entity_classification`, blocks MA rows, idempotent LEDGER hashing, single commit, validate-only confirmed write-free.
- The 310 ready file is structurally clean: all location_ids exist, all IL GP watched, zero duplicates, tier counts match the manifest.

---

## 3. Denominator audit — the finding the prior plan missed

**The 4,439 is a defensible working roster, not a verified directory of operating practices.** Publishing any census percentage against it as-is would repeat the exact sin the census exists to fix.

- **Closures counted as active: est. 220–400 locations (5–9%).** 192 of 2,069 dossier-covered locations (9.3%) have "closed"/"no longer" in `practice_intel.red_flags`; sampled cases are explicitly confirmed (Optimal Dental Lombard "permanently closed", Liberty Dental of Maplebrook "closed July 2025, merged into Smile Obsession", Gulati "Yelp CLOSED 2022", etc.). Only 4 locations carry `solo_inactive`. The evidence is already in the DB and unused.
- **Residual duplicates: est. 75–100 locations (1.7–2.3%).** 221 same-ZIP+same-phone combos with >1 location_id (246 excess rows); ~30–40% are true address-variant duplicates (typos, suite notation) that the exact-normalized-address dedup can't see. The other ~60–70% are distinct practices on shared DSO/answering-service trunk lines — do NOT mass-mark.
- **~27% of the roster (~1,200 locations) has zero non-NPPES liveness signal** (no website, no Data-Axle, no dossier). Highest-risk tail. 22 locations have no phone AND no website.
- The CA stray (`951701941a7097e5`) is handled coherently: in `practice_locations` (4,440) but excluded by `zip_scores` state filter (4,439). Raw queries need a `state='IL'` guard.

Ruling: census classification proceeds **in parallel** on this roster (waiting would stall everything), but the free closure pass runs first and the published denominator carries a roster caveat until liveness coverage is high.

---

## 4. Frontend / live-app findings

Confirmed: zero `ownership_tier` usage in `dental-pe-nextjs/src`; the live app is 100% legacy (`entity_classification` + `zip_scores`). Live site matches code (5.6% floor, band subtitle, CorporateBandBar on Market Intel).

Honesty problems to fix before publishing anything census-derived:
1. **"Independent: 94.4%"** (Market Intel; same pattern in Warroom Sitrep + Job Market) presents "not detected corporate" as verified independence. Relabel to "Not confirmed corporate" / "Unconfirmed".
2. **Per-ZIP surfaces carry no floor qualifier** (DSO penetration table, consolidation map, ZIP score table, both ZIP dossiers, saturation table) — a 0–3% ZIP reads as "low DSO penetration" when 119 IL ZIPs are known detector blind spots.
3. **AI routes state the floor as fact** (`api/launchpad/ask/route.ts:68`, `zip-mood/route.ts:41`) — inject floor framing into the prompt context.
4. **`solo_inactive` appears in target lists** (Warroom Hunt, Launchpad ranking at 0.6 weight, Job Market directory solo filter) with no "possibly closed" warning. Only 4 rows today, but the closure pass will grow this class — add the warning treatment now.

Census-coverage display spec (from the frontend lane, ~2–3 days of work when authorized): new `ownership-tiers.ts` constants + `queries/census.ts` (paginated) + `census-coverage-panel.tsx`; panel coexists with the legacy band; no census-derived percentage shown below a coverage threshold; "among reviewed" percentages always paired with coverage fraction; `CENSUS_UNIVERSE_IL` constant instead of scattered 4,439 literals.

---

## 5. Answers to the six architecture questions

1. **Should `ownership_tier` remain a separate axis from `entity_classification`?** Yes — unambiguous. `entity_classification` is a detector output (size/structure heuristics over NPPES+DataAxle); `ownership_tier` is earned evidence. Keeping them separate is what allowed the Wave-1 disaster to be fully reversed without touching production. `consolidate_census.py` must never write `entity_classification` (verified it doesn't).
2. **Legacy floor vs census display?** Coexist, staged. Phase now: legacy band only, with honesty fixes (§4). When census coverage > ~10% in SQLite AND synced: add the coverage panel (counts only). When coverage crosses a publication threshold (recommend ≥50% of the *cleaned* denominator, decided per-surface): show "among reviewed" percentages with coverage always adjacent. Retire the ADA-anchor band only when census coverage makes it redundant, never before.
3. **T3 dentist-owned multi-location groups in "consolidated" but not "DSO/PE"?** Yes. Consolidated = T2+T3+T4+T5; DSO/PE = T4+T5 only. This matches the tier table and is the honest read: a dentist owning 5 offices is consolidation of ownership but not institutional capital. Display language must show both numbers, labeled. Consequence: Archer Dentistry (rank 83) enters as T3 `dentist_multi` when its band is normalized — it should not remain a hold once the T3 policy is confirmed.
4. **Institutional/FQHC, Affordable Dentures, ClearChoice, protected networks, operating-status holds?**
   - Institutional/FQHC → T6, own bucket, excluded from both consolidated and DSO/PE numerators, shown as its own line. Never silently dropped.
   - ClearChoice → out of the GP denominator (implant centers are specialist-scope); classify as specialist-scope hold, consistent with existing ortho exclusions.
   - Affordable Dentures → in the GP denominator where the location is a general/denture practice; tier T5 (it is a branded network with corporate structure). Flag `pe_backed` per current ownership facts, not assumption.
   - Protected networks (NITTINGER/SHAFI etc.) → remain explicit holds; only whole-network adjudication can release them.
   - Operating-status holds → route into the closure/liveness pass. A closed practice exits the denominator; it does not get a tier.
5. **Consolidate the current 310 + QA-passed Wave 4 now, or redesign first?** Neither extreme. Fix blockers 1–3 (§2), spot-review the 68 weak-basis DSO rows, then consolidate **to SQLite only** in one versioned batch. **[ACCOUNTING CORRECTED 2026-07-02, coder-verified — see SESSION_PROTOCOL_FABLE_PM_20260702.md]:** 310 + Wave-4 19 merge-eligible + Lane-2 15 (1 corporate + 2 true-independent + 12 corroborates-existing-corporate no-floor-lift, all verified net-new location_ids) + (after Gate normalization + QA) Fleet B's 2 ≈ **346 coverage rows ≈ 7.8% coverage** before Archer/holds/downgrades. Coverage ≠ floor lift: DSO/PE floor-lift additions remain ~5. The earlier 332/334 figures undercounted by excluding the 12 no-lift corroborations, which conflated "new floor lift" with "reviewed census coverage." Files-only state was itself a failure mode — it's why docs drifted and why every session re-derived reality. Supabase sync and any UI exposure stay gated behind the ORM fix, migration verification, and the coverage panel. Do not redesign the validator; it's the best artifact this project produced.
6. **How to scale to 4,439 without lowering the evidence bar?** Invert the funnel — deterministic first, agents last (see §6). The old plan pointed agents at the whole problem and used humans as the message bus; the new plan uses scripts for the ~60% that's mechanically resolvable, cheap structured-output agents for the ambiguous middle, and reserves full adversarial QA for exactly the categories where Wave-1-style damage is possible (T4/T5 net-new, demotions, protected networks, scope). Orchestration runs inside one PM session (me) spawning agents directly — the human courier role is abolished.

---

## 6. Implementation plan

### Phase 0 — Unblock and clean (order matters; ~1–2 days of work when authorized)
1. Add 6 ownership columns to `PracticeLocation` + `Practice` ORM models; verify/run Supabase migration; add URL-format validation to `consolidate_census.py`; document the NPI-propagation scope.
2. **Closure pass (free):** script extracts intel-flagged closure candidates (~192) + the 22 zero-contact rows into a review file; PM adjudicates; confirmed closures get a roster status (recommend a new `operating_status` column or `likely_closed` location class rather than overloading `solo_inactive`) and exit the GP denominator with an evidence file, same discipline as the 2026-06-12 purge. CI floor guards re-based with evidence.
3. **Dup pass (cheap):** script the 221 phone+ZIP combos into a review file; mark only verified address-variant duplicates as `duplicate_location` (~75–100 expected).
4. Frontend honesty fixes (§4 items 1–4) — these are legacy-app fixes, safe to ship independently.

### Phase 1 — First consolidation (SQLite only)
5. Gate-normalize Fleet B 51–100 (one agent task, not a human relay); QA the 2 T5 candidates + Archer T3 under the confirmed T3 policy.
6. Assemble versioned addendum (310 + 19 + 1 + 2 + Archer if confirmed); validate-only; PM review of the 68 weak-basis rows; then `--allow-db-write`. Re-baseline DB md5 deliberately, record in LEDGER.

### Phase 2 — Deterministic funnel (the scale unlock)
7. **Queue generator** (`build_census_work_queue.py`): one ranked artifact from SQLite per the handoff §9C spec, reading `manifest["buckets"]`, excluding MA/specialist/da_unverified/duplicate/closed and already-adjudicated rows.
8. **Exact-address locator verifier**: deterministic scraper for the ~10 known platforms (Heartland, Aspen/TAG, Dental Dreams/KOS, NADG, GLDP, DCA, Smile Brands, Familia, Dentologie, Affordable) producing the handoff's JSON evidence shape. Targets the D1 brand-tagged pool (~200–250 locations) → T4/T5 candidates with gold-standard evidence, batched to QA.
9. **practice_intel T1 pass**: script reads existing dossiers for solo-class locations (2,069 covered; ~1,500–2,000 candidates), auto-drafts T1 `true_independent` rows where own-website named-owner evidence exists, flags the rest. Light validation, not full adversarial QA.
10. Optional paid leg: batch dossiers for the ~2,370 uncovered locations (~$19 at $0.008/practice) — closes both the liveness tail and the T1 evidence gap in one purchase.

### Phase 3 — Research pool + publication
11. Remaining ambiguous middle (~1,600–1,900: small_group/large_group/solo_high_volume needing structure checks): structured-output agent batches from the queue, tiered QA (full adversarial for T4/T5/demotions/protected/scope; light for T1/T2/rejects).
12. Frontend coverage panel ships when SQLite census coverage is real and synced; percentages unlock per the §5 Q2 thresholds.

### Standing rules
- One canonical state ledger (LEDGER.jsonl + PROGRESS.json); immutable evidence/verdict artifacts; no new "START_HERE" files.
- All DB writes only through `consolidate_census.py` or an evidence-file-documented cleanup script with CI guard re-base.
- Boston stays parked.
- Every batch: validate-only before write; md5 re-baseline after.

---

## 7. Cross-references

- Lane reports were produced in-session (Fable forks) and are summarized faithfully above; underlying artifacts: handoff (`PROJECT_MANAGER_HANDOFF_20260702.md`), QA verdicts (`_wave4_20260621/autonomous/VERDICT_QA_*.json`), Fleet B evidence (`wave4_lane3_phasec_51_100_evidence_20260622.json`), ready file + manifest (20260621), `consolidate_census.py`, `migrate_ownership_tier_cols.py`, `database.py`, `sync_to_supabase.py`, `consolidation-honesty.ts`, `entity-classifications.ts`.
- No files or DB rows were modified during this review. Validate-only was run twice (sessions `PM_DOC_AUDIT_20260702` by Codex, `FABLE_PM_LANE_BACKEND` today); LEDGER/PROGRESS confirmed untouched after both.
