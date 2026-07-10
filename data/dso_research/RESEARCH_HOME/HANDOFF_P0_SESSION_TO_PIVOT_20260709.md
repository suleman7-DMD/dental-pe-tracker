# HANDOFF — P0 Data-Integrity Session → App-Pivot Session

**From:** the Fable session that shipped the P0 stable-pagination / count-truth sprint (tasks #11–#24)
**To:** the Fable pivot-planning session (audit fleets + D4 Job Hunt CRM redesign, 2026-07-09)
**Status:** clean shutdown. Nothing mid-flight, git tree clean, all work committed + deployed + live-verified.

---

## 1. The pivot plan's "P0 / Wave 0" is ALREADY DONE — do not redo it

The pivot spec's implementation sequence starts with *"P0: stable pagination + canonical counts + invariant tests"* and *"Wave 0: fix infrastructure and counts."* That exact work shipped and is live:

- **Commit `11cb6e5`** (dental-pe-nextjs, on `main`, deployed to production) — "P0: stable pagination + Launchpad count/lane truth", 20 files, +648/−112. Preceded by `4946064` (trust-source labels on phone/address/website/staffing/doctors) and `1a11fbb` (two-axis coverage language).
- Every paginated `.range()` query in `src/` now ends in a **unique total ORDER BY** (tie-breakers on `location_id`/`npi`/`id` added across deals.ts, changes.ts, practices.ts, warroom.ts, ada-benchmarks.ts, data-breakdown.ts, opportunity-signals.tsx, launchpad fetches).
- **`src/lib/supabase/queries/stable-pagination.ts`** — reusable `fetchAllRowsStable` helper: dedupes by key across pages, warns on duplicates, throws on error. Use it for any new paginated fetch instead of hand-rolling.
- **Hard regression gate:** `dental-pe-nextjs/scripts/check_fetch_invariants.mjs` (run: `node scripts/check_fetch_invariants.mjs [--skip-live]`). Checks row-identity uniqueness, canonical counts, and that live /launchpad is free of the stale strings ("3,189", "49 / 4,439", "115 verified").
- **Tests:** 86 vitest passing, including new `stable-pagination.test.ts` (5) and `launchpad-lanes.test.ts` (5, lane-precedence rules).

**Re-verified at handoff (2026-07-09, --skip-live):**
```
PASS GP fetch has zero duplicate location_ids — 4439 rows, 4439 unique
PASS GP clinic-location total == 4439 — got 4439
PASS Ownership reviewed == 3180 — got 3180
PASS job_hunt_verification total == 48 — got 48
PASS GP-scope website-checked == 47 — got 47
```

If your audit fleets flag "unstable pagination" or "3,189-class count bugs," check whether the finding predates `11cb6e5` before scheduling a fix.

## 2. Canonical numbers + the one nuance worth knowing

- **4,439** GP clinic locations (IL scope) · **3,180** ownership-reviewed (71.64%) · **48** job_hunt_verification rows, **47** in GP scope (Wirtz Orthodontics is a specialist, outside GP scope).
- Live Launchpad ranked subline: **43 website-checked · 3,137 ownership known/job-unchecked · 1,259 ownership answer missing** (43+3,137=3,180; +1,259=4,439 — reconciles exactly).
- **43 vs 47:** lane precedence puts a website-checked office with NO reviewed ownership tier into needs_research (census answer first). 4 offices are in that state. This is intentional, tested in `launchpad-lanes.test.ts`, and flagged to Codex. The pivot's trust-lane design should decide deliberately whether to keep this rule.

## 3. Census close-out (task #17) — DEFERRED, maps to pivot P5

The ~1,259 unreviewed rows have researched artifacts on disk (≈488 new classifications / ≈766 undetermined / ≈5 needs-verification). **The write has NOT run.** It is parked because (a) the pivot demotes it below CRM work (its "P5: write/sync census recovery honestly"), and (b) writing it changes the 3,180 canon while audits verify against live.

When it runs: `consolidate_census.py --validate-only` → `--allow-db-write` only; update `EXPECTED_OWNERSHIP_REVIEWED` (and friends) in `check_fetch_invariants.mjs` **in the same commit**; parent-repo CI guards (CENSUS=3180, CENSUS_NPI=6754) follow their evidence-file rebase rules; then sync both legs + re-run invariants and the drift check.

## 4. Assets that survive the pivot (don't rebuild)

- `job_hunt_verification` table (48 rows, keyed by location_id) + import runbook — this IS the seed of the pivot's "Verification Factory" output table.
- Trust-source labels on key facts (registry vs website-checked vs commercial estimate) — the pivot's Trust Model builds directly on these.
- `src/lib/census/ownership-truth.ts` — canonical ownership contract (per the 2026-07-04 charter; reconcile, never rebuild).
- `practice_locations.census_review_status` ('held'|'undetermined'|NULL) — feeds honest "researched, no answer" buckets.
- Correction queue (`practice_manual_corrections`) — pivot's "Manual Correction Button" backend. **Do NOT grant anon/public SELECT/INSERT on it** (was denied once; do not retry).
- `fetchAllRowsStable`, the invariant script, and the lane tests.

## 5. Standing constraints (unchanged by the pivot)

Never DELETE from `practices`; ownership_tier never mutates entity_classification; census writes only via consolidate_census.py's two-step; denominator changes only via evidence-documented cleanup scripts; detector-floor CI guards untouched (FLOOR=268, FLOOR_NPI=1152, DENOM=4439); MA/Boston parked; secret values never printed.

## 6. Operational gotchas for live verification

- Live `/launchpad` is force-dynamic SSR, ~18.5 MB HTML. `curl --compressed --max-time 280` — short timeouts truncate mid-stream and make the deploy look stale when it isn't.
- React SSR splits adjacent text nodes with `<!-- -->` comments — grep with wide context (e.g. `.\{25\}website-checked`), not exact number-adjacent patterns.
