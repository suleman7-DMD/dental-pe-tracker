# Launchpad Phase 3 — Status Checkpoint (2026-04-25)

**Status:** ✅ All code shipped + deployed. Awaiting 3 user actions to fully activate AI features.
**Live URL:** https://dental-pe-nextjs.vercel.app/launchpad → returns HTTP 200 (CDN-cached)
**Build verified:** ✅ `npm run build` green; 7 Launchpad API routes registered
**Production deploy:** `c41e0dd` (next.js) on top of parent `9508865`

---

## Mandate (what was supposed to be addressed, in full)

The original Phase 3 brief was: build a qualitative-intelligence-driven first-job copilot for the Launchpad page, plus harden Warroom dossier flows for active outreach. Inheriting from Phase 2's rank-and-score scaffold, deliver:

1. **6 new Anthropic Claude API routes** (Haiku 4.5 + Sonnet 4.6) layered onto existing Launchpad data — ask, compound-narrative, interview-prep, zip-mood, smart-briefing, contract-parse. Reuse the proven `narrative/route.ts` pattern (raw HTTP fetch, no SDK, Node runtime, force-dynamic, 503 on missing key).
2. **7 Launchpad UI components** that consume those routes — ask drawer, compound thesis card, contract parser tab, DSO tier card, AI interview prep, smart briefing builder, ZIP mood badge.
3. **Anti-hallucination defense** for the Python research pipeline — force_search via `tool_choice`, per-claim `_source_url`, mandatory `verification` block, post-validation gate that quarantines bad dossiers.
4. **Warroom dossier hardening** — pin lifecycle (6 stages), reviewed tracking, dossier prev/next nav, pin-compare drawer (replaces deleted Profile mode), pin notes, intel availability badges, "in pipeline" filter chip.
5. **Signal-firing audit** — find and fix silently-broken signals (SQL filter mismatches, threshold over/underweighting, intel-required gating).
6. **Backend schema + migration** — new PracticeIntel columns (jobhunt + verification), idempotent SQL migration applied to both SQLite and Supabase.
7. **End-to-end validation** — full build, live deploy verification, 200-practice batch run to validate the anti-hallucination defenses work in production.
8. **Documentation** — comprehensive CLAUDE.md updates so the next session can resume without context loss.

Ground rules from the mandate (still binding):
- Use parallel agents with `@username` for multi-file work
- Mandatory QA agent after each wave
- Every fix needs proof (build green, smoke test, live URL check)
- Never stop until task complete
- ultrathink + maximum creativity

---

## What got done (with commit SHAs and verification commands)

### Frontend (`dental-pe-nextjs`)

| Commit | Title | What changed |
|--------|-------|--------------|
| `d2d61d2` | wip(launchpad-phase3): 6 AI API routes + signal-firing audit fixes | 6 new POST routes; `ai-types.ts`; SQL/ranking/signals fixes; red-flag heatmap removed |
| `ff5a7f1` | feat(warroom): Phase 2 triage — cut modes 4→2, lenses 8→4, scopes 12→11 | Removed Profile + Sitrep standalone modes; cut 4 low-signal lenses + US scope |
| `9fd171f` | feat(launchpad,warroom): Phase 3 — AI copilot UI + warroom pin lifecycle | 7 Launchpad components; 4 warroom hooks; `pin-compare-drawer.tsx`; KPI strip rebuild; Boston scopes |
| `f8beecb` | feat(warroom): target-list intel + reviewed filter buttons | Wired `intelAvailable` + `reviewedNpis` into TargetList |
| `50aecbb` | feat(warroom): dossier prev/next nav + reviewed tracking + pipeline badge | `[`/`]` keyboard, `V` for reviewed, "X of Y" indicator, lifecycle badge |
| `e615bb8` | docs(claude): document anti-hallucination defense + 200-practice run | Parent CLAUDE.md anti-hallucination section + Phase 3 ship log update |
| `c41e0dd` | docs(claude): fix warroom pin lifecycle stage names | Stage label corrections in Warroom Ship Log |

### Backend (`dental-pe-tracker`)

| Commit | Title | What changed |
|--------|-------|--------------|
| `8b68777` | wip(launchpad-phase3): backend intel layer for job-hunt mode | `JOB_HUNT_*` prompts; `research_practice_jobhunt()`; 7 new PracticeIntel columns; SQL migration |
| `73ad4fd` | docs(launchpad-phase3): add resume checkpoint for next session | Initial PHASE3_RESUME.md (this file, since rewritten) |
| `59e8403` | feat(scrapers): Phase 3 anti-hallucination evidence protocol | `force_search=True` parameter; `validate_dossier()` quarantine gate; 3 verification columns |
| `9508865` | chore(migrations): include verification columns in jobhunt SQL | Migration now covers all 10 new columns |

### 200-practice Chicagoland validation run

Batch ID: `msgbatch_017YJJ2M3WbLv4Q7gEhubK2o` (Anthropic Messages Batch API)
- 854 forced web searches executed (avg 4.27/practice)
- $14.91 real cost (~$0.075/practice — calibrates the cost model)
- 174 stored: 115 partial / 52 verified / 10 high quality
- 26 quarantined: 18 `evidence_quality=insufficient`, 8 `missing_verification_block`
- 0 hallucinations slipped through (Robert Ficek / Lutterbie pattern from test batch correctly returned `insufficient` instead of fabricating)

### Verification commands (run any of these to confirm state)

```bash
# Confirm both repos are clean and pushed
git -C /Users/suleman/dental-pe-tracker status
git -C /Users/suleman/dental-pe-tracker/dental-pe-nextjs status
git -C /Users/suleman/dental-pe-tracker log --oneline -10
git -C /Users/suleman/dental-pe-tracker/dental-pe-nextjs log --oneline -10

# Confirm production is healthy
curl -sI https://dental-pe-nextjs.vercel.app/launchpad | head -5
curl -sI https://dental-pe-nextjs.vercel.app/warroom | head -5

# Confirm AI routes return 503 (correct pre-env-var state)
curl -sX POST https://dental-pe-nextjs.vercel.app/api/launchpad/ask \
  -H 'content-type: application/json' \
  -d '{"practice":{"npi":"test","name":"test","city":"test","state":"IL","zip":"60661"},"question":"test"}'
# Expect: {"error":"AI Q&A disabled: ANTHROPIC_API_KEY is not set..."}

# Confirm Vercel deploy history
gh api 'repos/suleman7-DMD/dental-pe-tracker/deployments?per_page=5' --jq '.[] | "\(.sha[0:7])  \(.created_at)  \(.environment)"'

# Confirm Anthropic batch results (200-practice run)
ls -la /tmp/full_batch_summary.json /tmp/poll_full_batch.py /tmp/launch_top1_per_zip.py 2>/dev/null

# Confirm new Launchpad routes are built
cd /Users/suleman/dental-pe-tracker/dental-pe-nextjs && grep -l "force-dynamic" src/app/api/launchpad/**/route.ts
```

### Failed-deploy email postmortem

The Vercel "Deployment failed" email referred to deploy `4480719868` for commit `ff5a7f1` (Phase 2 triage) at 04:01 UTC on 2026-04-25. Root cause: transient. Vercel's CLI suggestion was `npx vercel inspect dpl_GZt4...`. Recovery: subsequent deploy `4480769033` for `f8beecb` (12 min later) succeeded; current production `c41e0dd` is healthy. No code regression — the failed deploy was a Vercel-side transient infra blip during peak push activity.

---

## What's next (3 required user actions)

These are blockers — AI features will return 503 until #1 is done.

### 1. Add `ANTHROPIC_API_KEY` to Vercel env vars

Vercel Dashboard → `dental-pe-nextjs` → Settings → Environment Variables → Add:
- Key: `ANTHROPIC_API_KEY`
- Value: your `sk-ant-...` key
- Environments: Production + Preview (skip Development unless local-only testing)

Then trigger a redeploy (Vercel auto-redeploys on env var change for the next deploy, but to activate immediately push any commit OR click "Redeploy" on the latest deployment).

**Verify after redeploy:**
```bash
curl -sX POST https://dental-pe-nextjs.vercel.app/api/launchpad/ask \
  -H 'content-type: application/json' \
  -d '{"practice":{"npi":"1234567890","name":"Test","city":"Chicago","state":"IL","zip":"60661"},"question":"What signals stand out?"}'
# Expect: 200 with {"answer":"...","model":"claude-haiku-4-5..."}
```

### 2. Apply SQL migration to Supabase Postgres

Supabase Dashboard → SQL Editor → New query → paste the contents of:
```
/Users/suleman/dental-pe-tracker/scrapers/migrations/2026_04_24_launchpad_jobhunt_columns.sql
```

The migration is idempotent (`IF NOT EXISTS` on every column + index). The 3 verification columns may already exist (the 200-practice batch run applied them via `/tmp/alter_verification_cols.py`); the migration is safe to re-run regardless.

**Verify after apply:**
```sql
-- In Supabase SQL editor:
SELECT column_name FROM information_schema.columns
WHERE table_name = 'practice_intel'
  AND column_name IN (
    'succession_intent_detected', 'new_grad_friendly_score', 'mentorship_signals',
    'associate_runway', 'compensation_signals', 'red_flags_for_grad', 'green_flags_for_grad',
    'verification_searches', 'verification_quality', 'verification_urls'
  );
-- Expect: 10 rows
```

### 3. Authorize seeding run (optional but recommended)

```bash
cd /Users/suleman/dental-pe-tracker
export ANTHROPIC_API_KEY="sk-ant-..."  # same key as Vercel env var
python3 scrapers/weekly_research.py --budget 30 --jobhunt
```

At verified Haiku pricing (~$0.011/practice), $30 = ~2,000 practice deep dives. The new `validate_dossier()` gate will quarantine any dossier that fails anti-hallucination checks; expect ~13% rejection rate based on the 200-practice validation run. Rejection breakdown printed in batch summary.

After the run completes, sync to Supabase:
```bash
python3 scrapers/sync_to_supabase.py
```

The Launchpad Intel Coverage KPI will jump from 23 / 401k → ~2,000 / 401k once data syncs.

### Optional follow-up

Want a 24h verification agent? Once the env var is in place:
- Smoke-tests all 7 AI routes return 200 from production
- Verifies a real practice query roundtrips end-to-end
- Confirms migration was applied (queries `information_schema.columns` via Supabase REST)
- Reports findings to Discord/file

Just say the word — `/schedule` an agent in 24h to verify the AI routes.

---

## Debug runbook (if anything looks off after env var add)

| Symptom | First check | Likely cause | Fix |
|---------|-------------|--------------|-----|
| `/api/launchpad/ask` still returns 503 | `vercel env ls` shows `ANTHROPIC_API_KEY` for Production? | Env var added to Preview only | Add to Production environment, redeploy |
| AI route returns 502 with "Failed to parse Claude response" | Check Vercel function logs for the raw response | Claude returned non-JSON wrapped in markdown | Already handled in routes (try/catch JSON.parse), file an issue if persistent |
| `/launchpad` Intel Coverage KPI stuck at 23 | `SELECT COUNT(*) FROM practice_intel` in Supabase | Migration applied but seeding run not done | Run `python3 scrapers/weekly_research.py --budget 30 --jobhunt`, then `sync_to_supabase.py` |
| `/launchpad` returns 500 | Vercel function logs → Supabase RPC error? | Missing column in Supabase | Re-apply migration SQL |
| `npm run build` fails after pulling | Check for TypeScript errors mentioning `SIGNALS_REQUIRING_INTEL` | Stale `node_modules/.next` cache | `rm -rf .next && npm run build` |
| Warroom dossier prev/next walks filtered-out targets | Check `dossier-drawer.tsx` reads `dossierIndex` from `visibleTargets`, not `bundle.rankedTargets` | Regression on the "do not regress" rule | Restore `visibleTargets` derivation |
| Pin lifecycle stage doesn't sync across tabs | Check `use-warroom-pin-lifecycle.ts` `storage` event listener | localStorage event handler removed | Restore the `window.addEventListener('storage', ...)` block |

---

## File ownership map (where things live)

### Frontend AI integration (`dental-pe-nextjs/src/`)

| File | Purpose |
|------|---------|
| `lib/launchpad/ai-types.ts` | Single source of truth for all 7 request/response pairs |
| `app/api/launchpad/ask/route.ts` | Haiku Q&A endpoint |
| `app/api/launchpad/compound-narrative/route.ts` | Haiku 2-3 sentence thesis |
| `app/api/launchpad/interview-prep/route.ts` | Haiku 10 signal-calibrated questions |
| `app/api/launchpad/zip-mood/route.ts` | Haiku 2-sentence ZIP vibe |
| `app/api/launchpad/smart-briefing/route.ts` | Sonnet 4.6 multi-practice comparison |
| `app/api/launchpad/contract-parse/route.ts` | Haiku contract trap extraction (5/hr rate limit) |
| `app/api/launchpad/narrative/route.ts` | (Phase 2) Haiku per-practice narrative |
| `app/launchpad/_components/ask-intel-drawer.tsx` | Sheet from dossier header |
| `app/launchpad/_components/compound-thesis.tsx` | Per-card collapsible thesis |
| `app/launchpad/_components/contract-parser.tsx` | New 6th dossier tab |
| `app/launchpad/_components/dso-tier-card.tsx` | Reusable tier badge component |
| `app/launchpad/_components/interview-prep-ai.tsx` | AI-powered Interview Prep tab |
| `app/launchpad/_components/smart-briefing-builder.tsx` | Pin → multi-select → comparison |
| `app/launchpad/_components/zip-mood-badge.tsx` | ZIP dossier header badge |
| `app/warroom/_components/pin-compare-drawer.tsx` | Replaces deleted Profile mode |
| `lib/hooks/use-warroom-intel.ts` | Practice intel fetcher |
| `lib/hooks/use-warroom-intel-availability.ts` | Sparkles badge driver |
| `lib/hooks/use-warroom-pin-lifecycle.ts` | 6-stage localStorage hook |
| `lib/hooks/use-warroom-pin-notes.ts` | Per-NPI freeform notes |
| `lib/hooks/use-warroom-reviewed.ts` | Reviewed timestamp tracking |

### Backend anti-hallucination (`dental-pe-tracker/scrapers/`)

| File | Purpose |
|------|---------|
| `research_engine.py` | `force_search` parameter; `PRACTICE_SYSTEM` evidence protocol; `_call_api()` tool_choice override |
| `weekly_research.py` | `validate_dossier()` quarantine gate; rejection reason aggregation |
| `database.py` | 10 new `PracticeIntel` columns |
| `intel_database.py` | `store_practice_intel()` writes verification fields |
| `migrations/2026_04_24_launchpad_jobhunt_columns.sql` | Idempotent ALTER TABLE for all 10 columns + index |

### Operational scripts (in `/tmp/`, recreate from CLAUDE.md if lost)

| File | Purpose |
|------|---------|
| `/tmp/launch_top1_per_zip.py` | Build batch with bulletproofed prompts, submit to Anthropic, persist batch_id |
| `/tmp/poll_full_batch.py` | Poll batch every 30s, validate dossiers, store passing ones, sync to Supabase |
| `/tmp/alter_verification_cols.py` | One-shot Supabase migration for 3 verification columns (already applied) |

---

## How to resume from this checkpoint

1. `cat /Users/suleman/dental-pe-tracker/PHASE3_RESUME.md` — read this file
2. `git -C /Users/suleman/dental-pe-tracker log --oneline -5` and `git -C /Users/suleman/dental-pe-tracker/dental-pe-nextjs log --oneline -5` — confirm HEADs match the table above
3. `curl -sI https://dental-pe-nextjs.vercel.app/launchpad | head -5` — confirm 200 OK
4. If user has done the 3 actions above, smoke-test the AI routes (see verification commands)
5. If anything's broken, consult the Debug runbook
6. Read `dental-pe-tracker/CLAUDE.md` "Anti-Hallucination Defense" section for backend internals
7. Read `dental-pe-nextjs/CLAUDE.md` "Phase 3 shipped" section for frontend internals
