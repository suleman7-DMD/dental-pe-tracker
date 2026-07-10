# HANDOFF — GPT-5.6 watcher for Fable pivot work

**Date:** 2026-07-10  
**Purpose:** Start a fresh `dpetyolo` Codex session with enough context to review
Fable's updates on the D4 Job Hunt CRM pivot without relearning the whole saga.

## How to use this file

Launch:

```bash
dpetyolo
```

Then paste:

```text
Read AGENTS.md and then read:
data/dso_research/RESEARCH_HOME/HANDOFF_GPT56_WATCH_FABLE_20260710.md

I am going to paste a Fable coder update. Your job is to verify it like a skeptical
engineering/product auditor: check current files, current commits, current invariant
scripts, and live/state claims where needed. Do not assume Fable is right because it
sounds confident. Tell me what is true, what is stale, what is risky, and the exact
next instruction I should give Fable.
```

## User pain points

The user is a D4 dental student trying to find the best first associate job in
Chicagoland and is willing to live in any of the 269 watched ZIPs. The original
vision was a "god mode" dental market app: for all 4,439 Chicagoland GP offices,
know reliable ownership, true owner/operator, current doctors, real phone/address,
hiring/openings, DSO/PE context, and best-opportunity ranking.

The core frustration: the app repeatedly displayed backend guesses as confident
truth. Fable would fix a visible issue, then Codex would probe a deeper layer and
find a pre-existing crack: unstable pagination, stale counts, "verified" language
without website verification, detector scores outranking trust state, fake-precision
scores, registry phone numbers displayed like confirmed contact data, etc.

The emotional issue is not just bugs. The user felt misled because nobody clearly
said early enough that full all-4,439 named-owner/current-doctor/hiring verification
is a data-operations project, not a one-shot AI app build.

## Product pivot

Do not treat the old "fully verified everything for all 4,439" as the product goal.
The current pivot is:

1. **Broad Honest Directory** — all 4,439 GP clinic locations can be shown, but only
   with labels that make source/trust level obvious.
2. **D4 Job Hunt CRM** — deeply verify the smaller set that matters:
   top 300 AI/research-assisted candidates, top 100 strong candidates, top 50
   human/action-ready targets.

The desired middle ground is:

```text
Broad imperfect map across 4,439
+ high-confidence verified layer for top 300
+ human-confirmed layer for top 50
= extremely powerful solo-AI D4 job-hunt system
```

This is not a waste of the existing work. The valuable foundation is the location
universe, ownership census framework, trust labels, job_hunt_verification table,
manual correction queue, stable pagination/invariants, Supabase/Next.js app,
Mapbox/map infrastructure, and runbooks. The bloat is any UI that lets weak backend
capability become a user-facing feature before it earns trust.

## Current hard facts to start from

Trust the current invariant code and latest commits over older prose in planning docs.
Some docs still mention the earlier 48-row / 3,180-reviewed state.

Current commits observed 2026-07-10:

- Root repo latest includes:
  - `b01cb44 Full JHV signal-pool run: 560 practices researched, seed 48->642, live-verified, JOB_HUNT floor rebased`
  - `5af4481 Bank LITE Sonnet JHV pilot: 34-practice results (raw + normalized + cohort)`
  - `3f52726 P5 census recovery close-out: 3,692/4,439 = 83.17% live, both sync legs read-back verified, CI + claims + skills rebased`
  - `e3e45d3 P0 durability: JHV survives practice_locations full_replace + queue truth`
  - `e171bf2 Bank P0 handoff for pivot session`
- Frontend latest includes:
  - `a391c7b Rebase JHV fetch invariants for the 2026-07-10 full signal-pool run (642/641)`
  - `f6780c3 Honest-labeling kill set: retire acquisition-verdict framing + fake confidence stars`
  - `4e2d0de Rebase EXPECTED_OWNERSHIP_REVIEWED 3180 -> 3692`
  - `d9be5d2 P0: canonical funnel spine (src/lib/census/funnel.ts) + tests + CI structure audit`
  - `11cb6e5 P0: stable pagination + Launchpad count/lane truth`

Current canonical state:

- IL GP clinic locations: **4,439**
- Ownership reviewed via census: **3,692 / 4,439 = 83.17%**
- Remaining ownership-undetermined: **747**
- Tier tally from `PROGRESS.json`:
  - true_independent 1,612
  - single_loc_group 1,105
  - dentist_multi 645
  - stealth_dso 63
  - branded_dso 196
  - institutional 71
  - undetermined_unreviewed 747
- `job_hunt_verification` seed rows: **642**
- GP-scope JHV rows in frontend invariant: **641** because Wirtz Orthodontics is specialist/outside GP scope.
- JHV seed tally:
  - roster_verified 336
  - hiring_page_found 43
  - call_required 25
  - no_usable_website 66
  - ownership_conflict 172
- Fable's 2026-07-10 full-run claim was verified locally:
  - 560 new rows from 94 Sonnet batches
  - full-run tally: roster_verified 288 / ownership_conflict 160 /
    hiring_page_found 38 / no_usable_website 53 / call_required 21
  - seed before 48, pilot 34, seed after 642
  - zero duplicate location_ids in the seed and zero enum remaps
- Important wording correction: Fable said "every roster_verified and
  hiring_page_found practice is outreach-ready in the app right now." Under the
  canonical funnel rule, this is **close but overbroad**:
  - roster/hiring JHV rows total: 379
  - outreach-ready under T1-T3 dentist-owned rule: 373
  - not T1-T3 outreach-ready: 4 missing ownership, 1 DSO-toggle-only, 1 Wirtz
    Orthodontics outside GP scope
  - therefore the honest claim is: "373 are outreach-ready under the default
    dentist-owned rule; 1 more is DSO-toggle-only; 4 need ownership; 1 is outside
    GP scope."
- Correction queue reconciliation artifact says live Supabase `practice_manual_corrections` has **7 total**:
  - 6 queued edge-QA rows
  - 1 rejected health_check row

Critical invariant file:

```text
dental-pe-nextjs/scripts/check_fetch_invariants.mjs
```

It currently pins:

```text
EXPECTED_GP_TOTAL = 4439
EXPECTED_OWNERSHIP_REVIEWED = 3692
EXPECTED_JHV_TOTAL = 642
EXPECTED_JHV_GP = 641
```

## Files to read first

Start with:

```text
AGENTS.md
data/dso_research/RESEARCH_HOME/PLAN_PRODUCT_RESET_D4_JOBHUNT_20260709.md
data/dso_research/RESEARCH_HOME/PROGRESS.json
JOB_HUNT_VERIFICATION_RUNBOOK.md
scrapers/test_job_hunt_durability.py
dental-pe-nextjs/scripts/check_fetch_invariants.mjs
dental-pe-nextjs/src/lib/census/funnel.ts
dental-pe-nextjs/src/__tests__/funnel.test.ts
data/dso_research/correction_queue_reconciliation_20260709.json
data/dso_research/jhv_full_run_merge_evidence_20260710.json
data/dso_research/jhv_full_run_observations_20260710.json
```

Important: `PLAN_PRODUCT_RESET_D4_JOBHUNT_20260709.md` is the strategic pivot,
but parts of it predate later work. If it conflicts with current invariant code,
recent commits, or `PROGRESS.json`, prefer the current machine-checked state.

## What the app should become

The app should stop being a PE-ish dashboard that exposes every backend artifact.
It should become:

1. **Dashboard / Mission Control** — live funnel, stale/recheck queue, next actions.
2. **Opportunity List** — six trust lanes, no arbitrary score outranking lane.
3. **Verified Shortlist** — high-confidence records with evidence URLs and check dates.
4. **Practice Detail** — one truthful CRM record per office.
5. **Outreach Tracker** — server-side outreach status/notes/next action.
6. **Directory** — all 4,439, broad and honest.
7. **Map** — colored by trust lane, not fake scores.
8. **Admin/Data Health/Methodology** — where legacy detector internals and pipeline health live.

The original full-coverage named-owner/current-doctor vision is retired as a
near-term product goal. It can remain a long-run possible Wave 5, but the app
must never imply it has been solved.

## What to watch Fable for

High-value Fable work:

- Makes counts single-sourced through `src/lib/census/funnel.ts`.
- Adds tests/invariants before claiming "done."
- Keeps `job_hunt_verification` durable through sync/full_replace paths.
- Preserves seed/live equality for JHV.
- Treats `practice_manual_corrections` as a live Supabase queue with export/apply path.
- Replaces "verified" with precise labels unless backed by JHV website check.
- Uses trust lanes instead of 0-100 scores.
- Labels registry-only phone/address and commercial estimates.
- Keeps ownership category separate from true named owner/operator.
- Builds top-300/top-50 verification workflow instead of trying all 4,439 at once.

Red flags:

- Claims "all 4,439 true owners are known."
- Treats ownership-reviewed as job-hunt verified.
- Treats all roster_verified/hiring_page_found rows as outreach-ready without
  applying the ownership-tier gate and GP-scope filter.
- Uses old 48/47 or 3,180 numbers after the 642/641 and 3,692 updates.
- Quotes "6 corrections" without acknowledging 7 total live rows.
- Says "verified" for `practice_intel`, AI dossiers, Data Axle, registry data, or detector floor.
- Lets `buyability_score`, `opportunity_score`, warroom scores, confidence stars, or MGMA comp bands drive user-facing ranking.
- Runs broad research fleets before P0/P1 durability and product simplification are settled.
- Runs DB writes/syncs without explicit user gate.
- Deletes/rewrites large surfaces before banking and verifying current state.
- Confuses `entity_classification` detector floor with `ownership_tier` census truth.
- Presents "95.7% research-touched" as job-hunt verification. It is ownership-grade touch, not D4-actionable verification.

## Verification commands

Use these before believing Fable's claims:

```bash
cd ~/dental-pe-tracker
git status --short
git log --oneline -8

cd ~/dental-pe-tracker/dental-pe-nextjs
git status --short
git log --oneline -8
npx vitest run --run
node scripts/check_fetch_invariants.mjs --skip-live
npm run build
```

For JHV seed truth:

```bash
cd ~/dental-pe-tracker
python3 - <<'PY'
import json, collections
rows=json.load(open('data/job_hunt_verification_seed.json'))
print('seed rows', len(rows))
print(collections.Counter(r.get('verification_status') for r in rows))
PY
python3 -m scrapers.import_job_hunt_verification --verify
python3 scrapers/test_job_hunt_durability.py
```

For ownership census truth:

```bash
python3 - <<'PY'
import json
d=json.load(open('data/dso_research/RESEARCH_HOME/PROGRESS.json'))
print(d['census_status'])
print(d['tier_tally'])
PY
```

## Decision posture for GPT-5.6 watcher

Be skeptical but constructive. The user is not asking for cheerleading. They need:

1. What is true now?
2. What changed since the last known state?
3. What is stale or misleading in Fable's report?
4. What hidden risk remains?
5. What exact message should the user send Fable next?

Do not make the user relay massive essays unless needed. Prefer short "copy this
to Fable" instructions that preserve the direction and prevent new drift.

## Current Codex launch state

`dpetyolo` currently requests GPT-5.5, not GPT-5.6, because the user's
installed Codex binary is still `codex-cli 0.142.5`. Official OpenAI help says
GPT-5.6 access in Codex requires Codex CLI **0.144.0+** and eligible
account/workspace availability; trying `-m gpt-5.6` on 0.142.5 with ChatGPT
auth produced:

```text
The 'gpt-5.6' model is not supported when using Codex with a ChatGPT account.
```

Do not set `dpetyolo` back to GPT-5.6 until `codex --version` reports at least
0.144.0 and the selector/model availability includes GPT-5.6.

Current working alias:

```text
alias dpetyolo='cd ~/dental-pe-tracker && git pull && codex --dangerously-bypass-approvals-and-sandbox -m gpt-5.5 -c model_reasoning_effort="xhigh"'
```

When the network is stable, run `codex update` or `brew upgrade --cask codex`,
then restart Codex and check `codex doctor`. Only then retry `gpt-5.6`.
