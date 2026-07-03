# Chicagoland Ownership Census — Research Home

**Created:** 2026-06-20 (Opus 4.8, synthesizing 5 prior investigation sessions).
**What this is:** the durable, cross-session operating system for **Goal 2** — building a fully investigated ownership **DIRECTORY** of every Chicagoland watched-ZIP general dental practice. Research does **not stop** until all **~4,439 IL GP locations** are placed in the 6-tier ownership hierarchy with documentary evidence — or explicitly marked **Undetermined** (never silent-defaulted to independent).

This folder is additive. It does not change the DB, the live app, or any classification. It is where findings live so they survive a session dying mid-task — the failure mode that ate the previous five sessions.

---

## ⛔ THE NO-ANCHOR RULE (user ruling, 2026-06-20 — read first, governs everything)

> "stop anchoring the 'whats supposed to be the consolidated percent' against the 14.6 ADA number. stop anchoring it to anything … we have no anchor. your research finds it by investigating each of the 4400ish chicagoland practices in the research home."

Concretely, binding on every metric, doc, and frontend surface from now on:

1. **No external anchor.** The ADA ~14.6% per-dentist figure, the "some metros are 30% DSO" figures — methodology unknown, **not used as a target, ceiling, or band.** Delete the floor→ADA band device (`consolidation-honesty.ts` `getCorporateBand` / `CorporateBandBar` / the `ada_hpi_benchmarks` anchor presentation) in the frontend revamp.
2. **The 5% detector floor is NOT the answer.** The user's ruling: "your findings of 5% consolidated/corporate are definitively false" (too low). 5.58% is the *starting point the census corrects upward*, never presented as truth.
3. **The census IS the source of truth.** Every published consolidation number is computed **from the LEDGER** — what we have actually verified — and shown **with its coverage**: `X% consolidated among N reviewed of 4,439 practices (Y% coverage)`. Unreviewed practices are **Undetermined**, shown explicitly. As coverage -> 100%, the reviewed rate converges to the empirical truth. No fabricated point estimate, ever.
4. **Honest during the build:** a partial census can show two different readouts, but they must be labeled differently:
   - **Reviewed-rate:** consolidated / reviewed practices. Useful for research progress, but biased until coverage is high.
   - **Confirmed-to-date whole-universe floor:** consolidated / 4,439 with unreviewed held out as unknown. Useful as a conservative floor, never the true rate.
   Never show a finished-looking single percent over incomplete data.

---

## The locked model (user decisions, 2026-06-20)

**6 ownership tiers + a PE flag + Undetermined.** Stored as a new `ownership_tier` column (+ `pe_backed` bool + evidence cols) on BOTH `practices` and `practice_locations`, BOTH SQLite + Supabase. `entity_classification` stays as the SIZE axis (backward-compat, F27 vitest untouched). This subsumes the competing "add `group_practice`/`stealth_dso` enum values" proposal — those map onto tiers below; the column is chosen because 6 tiers × a PE flag don't fit one enum and the enum path touches ~22 TS files with no detection chokepoint (silent-failure-prone).

| # | `ownership_tier` | Definition | In "Consolidated"? | In "DSO/PE"? |
|---|---|---|---|---|
| T1 | `true_independent` | One dentist owns ONE location (authorized official appears at a single ZIP; solo or family). **EARNED, never defaulted.** | no | no |
| T2 | `single_loc_group` | 2+ unrelated dentists, one location, dentist-owned. | **yes** | no |
| T3 | `dentist_multi` | One dentist-owner, 2+ locations, non-PE (mini-DSO / "stealth owner"). The Shafi / Brunetti class. | **yes** | no |
| T4 | `stealth_dso` | PE/MSO-backed friendly-PC, operating under local names. The Heartland-under-a-local-name class. | **yes** | **yes** |
| T5 | `branded_dso` | The brand IS the NPPES name (Aspen, Dental Dreams). | **yes** | **yes** |
| T6 | `institutional` | FQHC, hospital, university, government / Medicaid safety-net. | no (own bucket) | no |
| — | `undetermined` | Not yet reviewed OR genuinely ambiguous. Shown explicitly; never folded into independent. | excluded | excluded |

`pe_backed` (bool) is an **orthogonal cross-cutting badge**, not a tier (T4 always pe_backed; T5 may or may not be; T3 never).

**Two published headlines, both computed live from the census (NO anchor):**
- **Consolidated %** = (T2+T3+T4+T5) / reviewed — "not owned by a single dentist" (your redefinition).
- **DSO/PE %** = (T4+T5) / reviewed — operates as a DSO, branded or stealth.
- Both always shown with **coverage %** (reviewed / 4,439) and **Undetermined %**. For partial-census reporting, `undetermined_pct` can be shown two ways and must be labeled: reviewed-undetermined / reviewed, and unreviewed+undetermined / 4,439.
- If the UI also shows whole-universe numbers before 100% coverage, label them **confirmed-to-date floor**, not "the rate."

---

## How to resume a session (the loop that never stops)

1. **Read `PROGRESS.json`** — the heartbeat. It tells you coverage, tier tallies, and `next_batch`.
2. **Read `FINDINGS.md`** (current synthesis) and the relevant `CENSUS_PROTOCOL.md` step.
3. **Pull the next batch** of unreviewed `location_id`s (start with `next_batch`, then the dense zero-corp ZIPs).
4. **Verify each per `CENSUS_PROTOCOL.md`** — structural first (free), then candidate-pool levers (D1–D4), then web last-mile. Documentary evidence or `undetermined`.
5. **Append one line per practice to `LEDGER.jsonl`** (schema below). Zero fabrication.
6. **Update `PROGRESS.json`** (coverage, tallies, next_batch) and **append to `SESSION_LOG.md`**.
7. If you make DB flips (only post-sign-off), also write a dated `data/dso_research/il_*_YYYYMMDD.json` evidence file per the binding rules.

The census is **done** when `PROGRESS.json.census_status.remaining == 0`: every IL GP location is either classified-with-evidence into a tier or explicitly `undetermined`.

---

## Research-mode write boundary

Until the user explicitly approves DB/frontend mutations, research sessions are allowed to write only durable research artifacts:

- Append real reviewed rows to `LEDGER.jsonl`.
- Update `PROGRESS.json` using its existing schema (`reviewed_via_protocol`, `coverage_pct`, `tier_tally`, `next_batch`).
- Append `SESSION_LOG.md`.
- Write read-only evidence/candidate JSON files under `data/dso_research/`.

Prohibited without explicit mutation approval:

- DB updates or classification/tier writes.
- Schema migrations, including `scrapers/migrate_ownership_tier_cols.py` (local SQLite columns already exist; Supabase status still needs verification before production use).
- Sync scripts.
- Frontend edits/deploys.
- `scrapers/consolidate_census.py` in its current form. It is write-capable, updates `practice_locations` and `practices`, and rewrites `PROGRESS.json` using stale key names (`reviewed`/`coverage` instead of `reviewed_via_protocol`/`coverage_pct`).

Existing read-only or candidate-building scripts (`build_census_batches.py`, `build_ownership_census.py`, detector scripts) may be used only as candidate inputs. Their outputs are not classifications until ledgered through the protocol.

---

## Binding rules (carry into every step — superset of the old plan §4)

- **NO ANCHOR** (above). The census is the only source of truth; show coverage.
- **GP only.** Specialists / non-clinical / `da_unverified` / `org_only_npi` / `duplicate_location` never enter the GP denominator.
- **Documentary evidence per classification.** Acceptable: DSO locator exact street+ZIP; PE-sponsor + real shared EIN across 3+ ZIPs with ≥1 corroborating member; the NPI's own legal/parent name = a DSO; a web-verified brand; an authorized-official cluster gated by mailing-address concentration; a `practice_intel` dossier naming a DSO with its citation URL. **Never a single weak signal.**
- **Never silent-default to independent.** Ambiguous → `undetermined`. **T1 is EARNED** (verified single-owner single-location), never a fallback.
- **Never re-promote a demoted `location_id`** (`il_false_corporate_demotions_*.json` blocklist).
- **Mailing-address concentration is a CONFIDENCE signal, not an exclude:** ≤2 addrs across many ZIPs = high-confidence real group; a high address count (e.g. Sweis 12 addrs) falls through to web verification, **never auto-reject**.
- **Never DELETE from `practices`.** Flips bump `updated_at`. Sync via `_sync_floor_tables_only.py` + `_sync_practices_changed_rows.py --since DATE`; **never `--tables practices` alone**.
- **Boston PARKED** — IL only; MA stays in the DB (do not delete) but is filtered from view and never censused until the user un-parks it. Later frontend work must preserve the IL choke points in `dental-pe-nextjs/src/lib/supabase/queries/watched-zips.ts`, `zip-scores.ts`, and `practice-locations.ts`; do not reintroduce MA in metro selectors, maps, totals, or candidate queues.
- **Map semantics must be explicit.** A dot is not always a practice: Market Intel consolidation points are ZIP centroids; Job Market practice dots may be Data-Axle coordinates or ZIP-centroid jitter; Launchpad/Warroom target dots can be exact or approximated depending on coordinate availability. The app must label approximate/jittered dots and default broad density analysis to hex/bin views where useful.
- **Commit/push only when the user asks.** DB gzipped for git push.
- **Free data only** (NPPES, locators, WebSearch). No paid Anthropic batch without sign-off.

---

## File index

| File | Role |
|---|---|
| `README.md` | This file — entry point, model, no-anchor rule, resume loop, binding rules, ledger schema. |
| `MASTER_PLAN.md` | The integrated, re-sequenced execution plan (Phases 0–7). Supersedes `../../CHICAGOLAND_FLOOR_PLAN_2026-06-20.md` (kept for history). |
| `PROGRESS.json` | Machine-readable cross-session heartbeat: coverage, tier tallies, candidate pools, `next_batch`, per-ZIP sweep state. **Update every session.** |
| `LEDGER.jsonl` | Append-only, one line per reviewed IL GP location. The hand-verified record of all ~4,439 practices. |
| `CENSUS_PROTOCOL.md` | The per-practice verification recipe + the D1–D4 lever order + the discovery method (codified, not session-bound). |
| `FINDINGS.md` | Birds-eye synthesis of all 5 sessions: ground truth, levers with verified counts, contradictions resolved, magnitude. |
| `SESSION_LOG.md` | Append-only audit trail of what each session did. |

## LEDGER.jsonl record schema (also embedded as line 1 `_meta` of the file)

```
location_id        practice_locations PK (the census unit)
primary_npi        int       org_npi int|null
practice_name, city, zip
current_entity_classification   the pre-census class (size axis)
assigned_tier      true_independent | single_loc_group | dentist_multi | stealth_dso | branded_dso | institutional | undetermined
pe_backed          bool|null
owner_identity     str|null   authorized-official / owner dentist that links a network
network_id         str|null   groups locations under one owner/brand (e.g. "ao:SHAFI_SOHAIL")
evidence_basis     locator | web_verified | ein_cluster | ao_cluster | name_chain | intel_dossier | structural | none
evidence_urls      [str]      >=1 required for any non-structural classification
evidence_artifacts  [str]      local files / SQL query refs for DB-derived evidence (required for ao_cluster, ein_cluster, name_chain, structural)
confidence         high | medium | low
status             classified | undetermined | needs_verification
reviewer_session   str        reviewed_at YYYY-MM-DD
```
