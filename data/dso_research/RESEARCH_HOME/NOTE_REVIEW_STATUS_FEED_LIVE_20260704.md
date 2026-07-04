# NOTE → truth-app session: `census_review_status` feed is LIVE (2026-07-04)

**From:** Fable PM (data-ops session) · **To:** the truth-app charter session
(`SESSION_CHARTER_FABLE_TRUTH_APP_20260704.md`) · Full proof: runbook
`MASTER_RESUME_LANE_A_FLEET_20260702.md` **§6n**.

The gap your contract module anticipated is closed. `ownership-truth.ts` says:
> "Until a `census_review_status` column syncs, NULL maps to `unreviewed`… Pass `reviewStatus`
> when that feed lands; the UI upgrades automatically."

**It landed.** Supabase `practice_locations` now carries `census_review_status` VARCHAR(20),
values exactly matching `deriveSourceClass`'s parameter type:

| Value | Count (live, read-back verified 2026-07-04) | Meaning |
|---|---:|---|
| `'held'` | 178 | Behind a PM/gate hold (adjudication, positive-proof audit, R4/Aspen, closure suspect, PM hold file) |
| `'undetermined'` | 477 | Lane-A researched, evidence too thin to tier |
| `NULL` | rest | Never researched, out of scope, or already tiered |

Rules you can rely on:
- **Tier wins, always**: `status ∧ tier` overlap is 0 by construction (backfill guard-skips tiered
  rows) and your tier-first `deriveSourceClass` makes any future staleness benign.
- The column is location-level only — it does NOT exist on `practices` (review status is Review
  Desk metadata, not a tier; no NPI mirroring).
- It is ORM-mapped, so weekly syncs carry it; CI guards (CENSUS 3180 / CENSUS_NPI 6754) watch the
  tier layer it derives from.
- Source of truth for the mapping: `data/dso_research/census_review_status_backfill_20260704.json`
  (655 rows with per-row reason).

**Action for you:** select `census_review_status` in your practice_locations queries and pass it
as `reviewStatus` to `deriveSourceClass` — the held/undetermined buckets become real instead of
collapsing into `unreviewed`. No schema work needed on your side.
