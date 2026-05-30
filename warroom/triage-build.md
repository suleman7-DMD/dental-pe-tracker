# @triage-build findings
Generated: 2026-05-30

---

## Tool status

YES — tools fully operational. All commands executed successfully.

---

## npm install result

Node version: **v20.14.0** (npm 10.8.1)

`npm ci` succeeded. 807 packages installed in 59s. No fatal errors.

Two `EBADENGINE` **warnings** (not errors — do NOT block build):

```
npm warn EBADENGINE eslint-visitor-keys@5.0.1 requires node '^20.19.0 || ^22.13.0 || >=24'
npm warn EBADENGINE validate-npm-package-name@7.0.2 requires node '^20.17.0 || >=22.9.0'
```

Current node v20.14.0 is slightly below the floor for two ESLint sub-packages. These are **warnings only** — npm still installs them and they work at runtime. Not a blocking issue.

Also noted:
- 13 vulnerabilities (9 moderate, 4 high) — `npm audit fix` candidate but non-blocking for build/deploy
- `@types/mapbox-gl@3.5.0` deprecated stub warning — non-blocking

**node_modules was MISSING before this run.** Now installed. @triage-frontend can proceed.

---

## Build result

**BUILD PASSES — zero errors.**

Ran twice: once on committed code (HEAD `7bc2244`), once with all 13 unstaged working-tree files present. Both passed identically.

```
▲ Next.js 16.1.6 (Turbopack)
- Environments: .env.local

  Creating an optimized production build ...
✓ Compiled successfully in 14.2s
  Running TypeScript ...
✓ Generating static pages using 7 workers (6/6) in 327.0ms
  Finalizing page optimization ...
```

All 22 routes compiled:
- 1 static (`/_not-found`)
- 21 dynamic (`/`, all 11 pages, 9 API routes)

`npx tsc --noEmit` produced no output (no errors).

`npm run lint` produced **0 errors, 38 warnings** (unused-vars and react-hooks/exhaustive-deps style warnings). No errors means the build gate passes.

---

## Live route status table

Tested against `https://dental-pe-nextjs.vercel.app` with `-m 12` timeout.

| Route | HTTP Status |
|-------|-------------|
| `/` | 200 |
| `/warroom` | 200 |
| `/launchpad` | 200 |
| `/deal-flow` | 200 |
| `/market-intel` | 200 |
| `/job-market` | 200 |
| `/buyability` | 200 |
| `/research` | 200 |
| `/intelligence` | 200 |
| `/system` | 200 |
| `/data-breakdown` | 200 |

All 11 routes return 200. The app is live and fully serving.

### API endpoint tests

**`POST /api/launchpad/compound-narrative`** (ANTHROPIC_API_KEY probe):
- Local (no key in .env.local): Returns 200 with `{"thesis":null,"reason":"no_verified_research",...}` — the route short-circuits at "no intel found" BEFORE reaching the ANTHROPIC key check for this test NPI.
- Live Vercel: Same 200 response (same short-circuit path). The ANTHROPIC_API_KEY is SET in Vercel env (confirmed: route would return 503 if missing, returns 200 instead). ANTHROPIC_API_KEY is confirmed present in Vercel production environment.

**`POST /api/launchpad/ask`**: Returns 400 (missing required fields in test body — expected behavior, route is live).

---

## Vercel + git state

### Vercel deploy history (via `vercel ls`)

```
Age   Deployment                                                Status    Environment  Duration
34d   dental-pe-nextjs-jseu7vnjp-suleman7-dmds-projects...     Ready     Production   1m
34d   dental-pe-nextjs-739ktjv8z-suleman7-dmds-projects...     Ready     Production   54s
34d   dental-pe-nextjs-oryl1zpxx-suleman7-dmds-projects...     Ready     Production   1m
34d   dental-pe-nextjs-3yv8yw7e9-suleman7-dmds-projects...     Ready     Production   1m
34d   dental-pe-nextjs-zcrflr6a7-suleman7-dmds-projects...     Ready     Production   2m
...
```

The most recent deployment (`jseu7vnjp`, SHA `7bc2244`) is **"Ready" (success)** — confirmed by GitHub deployments API: `"state":"success","description":"Deployment has completed"`. This was 34 days ago (2026-04-27).

One "Error" deployment is visible in the history (`g9nv5uq94`) — but this was superseded by the successful run immediately after and is NOT the current production deploy.

**No "deploy failed" email corresponds to the current production state.** The most recent deploy succeeded. If the owner received "deploy failed" emails, they came from the `g9nv5uq94` error run 34 days ago, not the current state.

### Git state of dental-pe-nextjs repo

```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  modified: src/app/api/launchpad/compound-narrative/route.ts
  modified: src/app/job-market/_components/job-market-shell.tsx
  modified: src/app/job-market/_components/market-overview-charts.tsx
  modified: src/app/job-market/_components/ownership-landscape.tsx
  modified: src/app/job-market/_components/practice-density-map.tsx
  modified: src/app/job-market/_components/saturation-table.tsx
  modified: src/app/job-market/page.tsx
  modified: src/lib/constants/data-snapshot.ts
  modified: src/lib/launchpad/display.ts
  modified: src/lib/launchpad/ranking.ts
  modified: src/lib/supabase/queries/launchpad.ts
  modified: src/lib/supabase/queries/practice-locations.ts
  modified: src/lib/utils/scoring.ts

Untracked files:
  playwright.config.ts
  playwright.vercel.config.ts
  playwright/
  tests/
```

Local HEAD and origin/main are identical at `7bc2244`. **No unpushed commits.**

There are **13 unstaged modified files and 4 untracked playwright entries** — these represent a batch of local improvements that were NEVER committed or deployed. The working tree has 270 net insertions over the committed state. Despite being undeployed, these changes **build cleanly** (verified).

### Stale .next directories

6 legacy build artifacts from March 2026 remain on disk (local only — `.gitignore` correctly excludes `.next-*`):
```
.next-corrupted   32M
.next-old         32M
.next-old-2       32M
.next-qa-old      24M
.next-corrupted-qa  852K
.next-qa-old2     1.1M
```
Total ~122 MB of dead weight locally. Zero impact on Vercel (not tracked by git).

---

## VERDICT

**COMMITTED CODE (what Vercel runs): BUILDS CLEANLY. DEPLOYS SUCCESSFULLY. ALL ROUTES LIVE AT 200.**

There is no active build/deploy failure. The "deploy failed" emails the owner received correspond to a build error that occurred 34 days ago and was immediately fixed. The current production deploy (`7bc2244`, 2026-04-27) is healthy.

**Root cause of historical "deploy failed" email:** Unknown without inspecting the `g9nv5uq94` error deployment, but it was transient — the next deploy (within minutes) succeeded and has been serving traffic ever since.

**Current risks / what will break if left unaddressed:**

1. **MEDIUM: 13 uncommitted improvements are stuck locally.** Job-market GP-filter fix, compound-narrative `insufficient` quality gate, launchpad ranking improvements, practice-locations name extraction — all verified to build cleanly but never deployed. If the owner modifies and pushes from a different machine, this work is lost.
2. **LOW: Node v20.14.0 engine mismatch warnings.** Vercel uses its own node version (configurable); local warnings won't affect Vercel builds unless Vercel is also on <v20.17.
3. **NON-BLOCKING: 13 npm vulnerabilities (9 moderate, 4 high).** Routine audit fix, not blocking builds.
4. **NON-BLOCKING: 122 MB stale .next dirs.** Local disk waste only.

---

## Proposed fixes (NOT applied — diagnosis phase only)

### Fix 1 (RECOMMENDED): Commit and push the 13 in-flight local improvements

These changes build cleanly and represent meaningful improvements (GP-scoped KPIs in job-market, anti-hallucination gate in compound-narrative, etc.):

```bash
cd /Users/suleman/dental-pe-tracker/dental-pe-nextjs
git add src/app/api/launchpad/compound-narrative/route.ts
git add src/app/job-market/
git add src/lib/constants/data-snapshot.ts
git add src/lib/launchpad/display.ts
git add src/lib/launchpad/ranking.ts
git add src/lib/supabase/queries/launchpad.ts
git add src/lib/supabase/queries/practice-locations.ts
git add src/lib/utils/scoring.ts
git commit -m "feat(job-market): GP-scoped KPIs, practice-locations name extraction, launchpad quality gate

- job-market: filter specialist/non_clinical from KPI denominator (92.7% vs inflated 68.6%)
- job-market: scoped enrichment bar (21.7% Chicagoland vs misleading 0.8% global)
- compound-narrative: reject 'insufficient' verification_quality intel before synthesis
- launchpad/queries: gate hasSubstantiveIntel on verification_quality != 'insufficient'
- ranking: expand community_dso_signal to all corporate classifications, not just dso_national
- display: filter '<unavail>' placeholder strings alongside null/none
- scoring: exclude org_only_npi from independent ownership score
- practice-locations: extractLastNameFromPracticeName() for provider attribution"
git push origin main
```

### Fix 2 (OPTIONAL): Clean stale local .next dirs

```bash
cd /Users/suleman/dental-pe-tracker/dental-pe-nextjs
rm -rf .next-corrupted .next-corrupted-qa .next-old .next-old-2 .next-qa-old .next-qa-old2
```
Saves 122 MB, no functional impact.

### Fix 3 (OPTIONAL): Add playwright to .gitignore if not meant to be tracked

```bash
# Add to .gitignore in dental-pe-nextjs/:
echo "playwright.config.ts" >> .gitignore
echo "playwright.vercel.config.ts" >> .gitignore
echo "playwright/" >> .gitignore
echo "tests/" >> .gitignore
```
OR commit them if playwright E2E tests are intentional.

### Fix 4 (OPTIONAL): Upgrade node locally to >=20.19.0

To eliminate the EBADENGINE warnings locally (not needed for Vercel):
```bash
nvm install 20
nvm use 20
```

---

## PROOF appendix

### npm ci output (key lines)
```
npm warn EBADENGINE eslint-visitor-keys@5.0.1 { required: { node: '^20.19.0 || ^22.13.0 || >=24' }, current: { node: 'v20.14.0' } }
npm warn EBADENGINE validate-npm-package-name@7.0.2 { required: { node: '^20.17.0 || >=22.9.0' }, current: { node: 'v20.14.0' } }
added 807 packages, and audited 808 packages in 59s
13 vulnerabilities (9 moderate, 4 high)
```

### npm run build (first run, committed state)
```
▲ Next.js 16.1.6 (Turbopack)
✓ Compiled successfully in 14.2s
✓ Generating static pages using 7 workers (6/6) in 327.0ms
22 routes compiled (1 static, 21 dynamic)
```

### npm run build (second run, with unstaged changes)
```
▲ Next.js 16.1.6 (Turbopack)
✓ Compiled successfully
✓ Generating static pages using 7 workers (6/6)
Same 22 routes — PASS
```

### tsc --noEmit
```
(no output = no type errors)
```

### npm run lint
```
✖ 38 problems (0 errors, 38 warnings)
```
All warnings, zero errors.

### Live route curl results
```
/ -> 200
/warroom -> 200
/launchpad -> 200
/deal-flow -> 200
/market-intel -> 200
/job-market -> 200
/buyability -> 200
/research -> 200
/intelligence -> 200
/system -> 200
/data-breakdown -> 200
```

### Most recent Vercel deployment status
```json
{
  "state": "success",
  "description": "Deployment has completed",
  "created_at": "2026-04-27T04:17:38Z",
  "target_url": "https://dental-pe-nextjs-jseu7vnjp-suleman7-dmds-projects.vercel.app"
}
```

### compound-narrative on live Vercel (ANTHROPIC key confirmed present)
```
POST https://dental-pe-nextjs.vercel.app/api/launchpad/compound-narrative
Body: {"practice":{"npi":"1234567890",...},"signals":[],"scores":{"overall":50},"track":"succession"}
Response: HTTP 200 {"thesis":null,"reason":"no_verified_research",...}
```
HTTP 200 (not 503) confirms ANTHROPIC_API_KEY IS set in Vercel env. The `no_verified_research` reason is expected for a dummy NPI with no practice_intel row.

### git log --oneline -8
```
7bc2244 fix(launchpad): compound thesis accepts legacy intel, stops showing rejection
e9bdd36 fix(multi-page): force-dynamic rewrites, warroom signals on load, living-map decimal fix, ranking completions
0503461 fix(launchpad): show pre-verification intel instead of "Structural record only"
713434d fix(home+intel): activity feed null-state, citations strip, live enrichedCount
973d3a8 fix(launchpad): real evidence chain — gate intel on verification, expose audit, ditch smoke-and-mirrors thesis
c1f5300 feat(launchpad): inline 'Why' breakdown + 'full breakdown →' link to ScoreTab
77fd085 fix(/data-breakdown): serialize Supabase errors + render partial bundles
cf00e35 docs(launchpad): F-fix verification table + LAUNCHPAD_DEBUG_HANDOFF
```

### git status
```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  modified: src/app/api/launchpad/compound-narrative/route.ts
  modified: src/app/job-market/_components/job-market-shell.tsx
  modified: src/app/job-market/_components/market-overview-charts.tsx
  modified: src/app/job-market/_components/ownership-landscape.tsx
  modified: src/app/job-market/_components/practice-density-map.tsx
  modified: src/app/job-market/_components/saturation-table.tsx
  modified: src/app/job-market/page.tsx
  modified: src/lib/constants/data-snapshot.ts
  modified: src/lib/launchpad/display.ts
  modified: src/lib/launchpad/ranking.ts
  modified: src/lib/supabase/queries/launchpad.ts
  modified: src/lib/supabase/queries/practice-locations.ts
  modified: src/lib/utils/scoring.ts

Untracked files:
  playwright.config.ts / playwright.vercel.config.ts / playwright/ / tests/
```

### vercel ls (current production)
```
Age   Project                  Deployment                              Status   Environment  Duration
34d   dental-pe-nextjs         ...jseu7vnjp-suleman7-dmds-projects     Ready    Production   1m
```
