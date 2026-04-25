# Launchpad Phase 3 — Resume Checkpoint (2026-04-24)

**Status:** Wave 1 + Wave 2 partial complete. Wave 2 UI agents + Wave 3 QA + verification still pending.
**Live URL:** https://dental-pe-nextjs.vercel.app/launchpad
**Build verified:** ❌ NO — `npm run build` not yet run on Phase 3 changes.

## What's saved (committed, not pushed)

### Parent repo (`dental-pe-tracker`)
- `8b68777` wip(launchpad-phase3): backend intel layer for job-hunt mode
  - `scrapers/research_engine.py` — JOB_HUNT prompts + `research_practice_jobhunt()` + `build_batch_requests_jobhunt()`
  - `scrapers/database.py` — 7 new PracticeIntel columns
  - `scrapers/intel_database.py` — `store_practice_intel()` updated
  - `scrapers/migrations/2026_04_24_launchpad_jobhunt_columns.sql` — Postgres DDL (apply manually to Supabase)

### Next.js subrepo (`dental-pe-nextjs`)
- `d2d61d2` wip(launchpad-phase3): 6 AI API routes + signal-firing audit fixes
  - **Note:** This commit also accidentally bundled in-flight Warroom cleanup files (-786 lines in warroom). The Launchpad changes are clean; the Warroom changes were sitting in working tree from a prior session and got swept up. Disentangle later if needed via `git revert` + cherry-pick.
  - **6 new API routes** (all Node runtime, force-dynamic, raw HTTP fetch to Anthropic):
    - `/api/launchpad/ask` (Haiku 4.5) — free-form NL Q&A
    - `/api/launchpad/compound-narrative` (Haiku) — 2-3 sentence thesis
    - `/api/launchpad/interview-prep` (Haiku) — 10 signal-calibrated questions
    - `/api/launchpad/zip-mood` (Haiku) — 2-sentence ZIP vibe
    - `/api/launchpad/smart-briefing` (Sonnet 4.6) — side-by-side comparison
    - `/api/launchpad/contract-parse` (Haiku, 5/hr rate limit) — contract trap extraction
  - **Shared types:** `src/lib/launchpad/ai-types.ts`
  - **Signal-firing audit fixes:** `queries/launchpad.ts` (SQL %ownership%→%acquisition%), `ranking.ts` (3 logic fixes), `signals.ts` (weight + SIGNALS_REQUIRING_INTEL export)
  - **Component cleanup:** `red-flag-patterns.tsx` (heatmap removed, 293→172 lines)

## What's pending (NOT done)

### Wave 2 — 3 UI/structural agents to launch in parallel

#### `@ui-frontend-1` — Practice Dossier AI integration
**Owns:** `practice-dossier.tsx`, `launchpad-kpi-strip.tsx`
**Creates:**
- `_components/ask-intel-drawer.tsx` — wraps `/api/launchpad/ask` in a drawer triggered from dossier header
- `_components/interview-prep-ai.tsx` — replaces static Interview Prep tab; calls `/api/launchpad/interview-prep`
- `_components/contract-parser.tsx` — new tab (or modal); calls `/api/launchpad/contract-parse` with textarea input
**Modifies:**
- `practice-dossier.tsx` — header gets "Ask Intel" trigger; Interview Prep tab swap; new Contract Parser tab
- `launchpad-kpi-strip.tsx` — replace comp-range KPI with intel-coverage KPI (% of practices with `practice_intel` row)

#### `@ui-frontend-2` — Track list, ZIP dossier, shell wiring
**Owns:** `track-list-card.tsx`, `zip-dossier-drawer.tsx`, `launchpad-shell.tsx`
**Creates:**
- `_components/smart-briefing-builder.tsx` — multi-select picker triggered from pinboard area; calls `/api/launchpad/smart-briefing`
- `_components/zip-mood-badge.tsx` — small badge calling `/api/launchpad/zip-mood`, rendered in ZIP dossier header
- `_components/compound-thesis.tsx` (or inline in card) — calls `/api/launchpad/compound-narrative`, rendered inline on each track-list card
**Modifies:**
- `track-list-card.tsx` — embed compound thesis (lazy/expandable)
- `zip-dossier-drawer.tsx` — add ZipMoodBadge to header
- `launchpad-shell.tsx` — add SmartBriefingBuilder trigger near pinboard; **remove `SavedSearchesMenu` import + its render block** (lines 21, 156-172)
**Deletes:**
- `_components/saved-searches-menu.tsx`
- `src/lib/hooks/use-launchpad-saved-searches.ts` (also remove from `use-launchpad-state.ts` deps)

#### `@structural` — Map lenses, DSO tier extraction, Boston presets
**Owns:** `living-map.tsx`, `scope.ts`, `living-locations.ts` (in constants)
**Creates:**
- `_components/dso-tier-card.tsx` — extract DSO tier display logic from `practice-dossier.tsx` into reusable card
**Modifies:**
- `living-map.tsx` — default to ZIP view (not practices), add Mentor Density + DSO Avoid lenses (alongside existing lens toggle), add data-quality warning banner when `metrics_confidence === 'low'` for selected ZIP
- `src/lib/launchpad/scope.ts` — add 4 Boston Metro presets (Boston Core, Cambridge/Somerville, North Shore, South Shore) with their 21 ZIPs
- `src/lib/constants/living-locations.ts` — add Boston Metro 21 ZIP definitions

### Wave 3 — `@qa-guardian`
- Read all Wave 2 diffs
- Run `npm run build` in `dental-pe-nextjs/` — expect TypeScript clean
- Verify `SIGNALS_REQUIRING_INTEL` import resolves
- Verify all 6 API routes have matching client-side fetchers
- Verify removed files have no dangling imports
- Open dev server, click through Launchpad — verify no console errors, no missing components

### After Wave 3
1. Update `dental-pe-nextjs/CLAUDE.md` "Launchpad Ship Log" with Phase 3 section
2. Squash WIP commits if desired (or leave as audit trail)
3. Push to `main` → Vercel auto-deploys
4. **User actions required after deploy:**
   - Add `ANTHROPIC_API_KEY` to Vercel env vars (production + preview)
   - Apply `scrapers/migrations/2026_04_24_launchpad_jobhunt_columns.sql` to Supabase Postgres via SQL editor
   - Authorize $30 seeding run: `python3 scrapers/weekly_research.py --budget 30 --jobhunt`

## Critical context the next session needs

### Cost reality (verified, replaces CLAUDE.md estimates)
- Haiku per ZIP: ~$0.024 (NOT $0.04-0.06)
- Haiku per practice: ~$0.011 (NOT $0.08-0.12)
- $30 budget → ~2,000 practice deep dives, NOT 300

### Data quality gotcha
- Only 32 of 290 `zip_qualitative_intel` rows are real (cost_usd > 0). 258 are synthetic placeholders.
- Only 23 of 401k practices have real `practice_intel`.
- The "intel coverage KPI" (replacing comp-range) should reflect this honestly: small denominator, big growth potential.

### Anthropic integration pattern (do not regress)
- Raw HTTP `fetch` (no `@anthropic-ai/sdk`) — matches existing `narrative/route.ts`
- `export const runtime = 'nodejs'` + `export const dynamic = 'force-dynamic'`
- 503 (not 500) when `ANTHROPIC_API_KEY` missing
- Rate limiting via in-memory `Map<string, number[]>` keyed by `x-forwarded-for`
- All `JSON.parse` on Claude response wrapped in try/catch, return 502 on parse fail

### File ownership map (prevents merge conflicts)
| File | Owner |
|------|-------|
| `practice-dossier.tsx` | @ui-frontend-1 |
| `launchpad-kpi-strip.tsx` | @ui-frontend-1 |
| `track-list-card.tsx` | @ui-frontend-2 |
| `zip-dossier-drawer.tsx` | @ui-frontend-2 |
| `launchpad-shell.tsx` | @ui-frontend-2 |
| `living-map.tsx` | @structural |
| `scope.ts` | @structural |
| `living-locations.ts` | @structural |

## How to resume

1. `cat /Users/suleman/dental-pe-tracker/PHASE3_RESUME.md` — read this file
2. `git -C /Users/suleman/dental-pe-tracker log --oneline -5` — confirm `8b68777` is HEAD
3. `git -C /Users/suleman/dental-pe-tracker/dental-pe-nextjs log --oneline -5` — confirm `d2d61d2` is HEAD
4. Verify nothing is uncommitted: `git status` in both repos
5. Launch the 3 Wave 2 agents in **one message with parallel Agent tool calls** — see prompts in this doc
6. After all 3 return, launch @qa-guardian
7. Run `npm run build` and `npm run dev` for browser verification
8. Update CLAUDE.md, push to main
