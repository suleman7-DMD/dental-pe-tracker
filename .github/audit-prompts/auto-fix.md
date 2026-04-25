# Auto-Fix Round — {{TARGET_DATE}}

You are running in **GitHub Actions headless mode**. No interactive user. You ARE allowed to mutate code, run builds, and commit, but ONLY in service of opening a single PR. You are NOT allowed to push to `main` or merge anything.

## Mission

Read the **most recent** `AUDIT_REPORT_*.md` file at the repo root. Pick up to 5 high-confidence `P0`/`P1` items from its "Prioritized Debug Backlog" section. Fix them surgically. Open ONE PR with all the fixes batched together. Stop.

This is the **automated debug pass** that follows each comprehensive audit. The owner reviews the resulting PR — they merge or reject; you do not auto-merge.

## Hard Rules (Non-Negotiable)

1. **Branch only.** Create branch `auto-fix/{{TARGET_DATE}}` (delete locally if it exists). Never push to `main`. Never merge.
2. **PR only.** Final action is `gh pr create`. Title: `auto-fix({{TARGET_DATE}}): N fixes from audit`. Body: itemized list of which backlog items you addressed, what you changed, file:line, and what you skipped + why.
3. **P0/P1 only.** Skip P2/P3 — they're not high-confidence enough for unsupervised fixes.
4. **High-confidence only.** If the fix isn't obvious from the audit's evidence (e.g., requires new architectural decisions, ambiguous root cause, depends on external policy), skip and document in the PR body.
5. **Build must pass.** Run `npm run build` in `dental-pe-nextjs/` after each fix. If build breaks, revert that fix, log it, move on.
6. **Max 5 file changes per PR** total. If you need to touch more, batch differently or skip.
7. **Each fix is its own commit** with conventional message: `fix(<scope>): <one-line>`. Trailer: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
8. **No new dependencies.** Do not run `npm install` of new packages. Do not add `pip install`. Use what's there.
9. **No data mutations.** Do NOT run scrapers. Do NOT modify Supabase rows. Do NOT touch `data/`. Code-only fixes.
10. **Idempotent.** Re-running this prompt without changes should result in zero new commits.
11. **Safety net.** If the audit cannot be found, OR if there are no P0/P1 items to fix, OR if a previous `auto-fix/*` PR is still open, abort with a clear note in the workflow summary and exit cleanly.

## Order of operations

### Step 1 — Find the latest audit
```bash
LATEST=$(ls -1 AUDIT_REPORT_*.md 2>/dev/null | sort -r | head -1)
[ -z "$LATEST" ] && { echo "No audit found"; exit 0; }
```

### Step 2 — Check for already-open auto-fix PR
```bash
gh pr list --search 'is:open in:title auto-fix' --json number,title --limit 5
```
If any open `auto-fix/*` PR exists, abort cleanly. The owner needs to review that one before you queue another.

### Step 3 — Read the backlog
Read the "Prioritized Debug Backlog" section of `$LATEST`. Extract every item tagged `P0` or `P1`. For each, note:
- File:line of the bug
- Recommended fix (if explicit)
- Confidence level

### Step 4 — Pick up to 5 items
Filter for items where:
- The fix is explicit and concrete (not "investigate why X")
- The fix is code-only (not "add new secret to Vercel" or "manually run scraper")
- File:line is in the repo (not in `dental-pe-nextjs/` if that's gitignored — check)

If fewer than 1 item qualifies, abort with note in PR-or-summary.

### Step 5 — Set up branch
```bash
BRANCH="auto-fix/{{TARGET_DATE}}"
git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
```

### Step 6 — For each chosen item
1. Read the affected files end-to-end (not just the cited line).
2. Make the fix with `Edit` or `Write` tools.
3. Run `cd dental-pe-nextjs && npm run build` (if frontend file). For Python files, `python3 -c "import <module>"` smoke-import.
4. If build/import fails, revert (`git checkout -- <file>`) and log the failure.
5. If build passes, commit with conventional message.

### Step 7 — Final build verification
```bash
cd dental-pe-nextjs && npm run build 2>&1 | tail -30
```
Capture exit code. If non-zero: tag PR title with `🚨 BUILD FAILED — manual review required`.

### Step 8 — Push branch + open PR
```bash
git push origin "$BRANCH"
gh pr create \
  --base main \
  --head "$BRANCH" \
  --title "auto-fix({{TARGET_DATE}}): <N> fixes from audit" \
  --body "$(cat <<'EOF'
## Summary
Automated fix pass against \`$LATEST\`. Picked $N P0/P1 items from the backlog.

## Items addressed
<bulleted list of items>

## Items skipped
<bulleted list with reasons: low-confidence / out-of-scope / requires-secret-change>

## Build status
- \`npm run build\`: <PASS|FAIL>
- Commits in PR: <count>

## Review notes for the owner
- Each fix is a separate commit; cherry-pick or revert individual fixes via \`git revert <sha>\`.
- This PR was generated automatically. Merge if it looks good; close if not.
- Next auto-fix run will skip items that are still in the backlog (no infinite loops on stuck items) only if this PR is merged or closed.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

## What you ARE allowed to do (code-only fixes)

- Edit files in `scrapers/`, `dental-pe-nextjs/src/` (only if not gitignored), `.github/workflows/`, top-level Python scripts
- Add type annotations or null-checks suggested by the audit
- Adjust SQL queries to match documented schema
- Fix off-by-one errors, typos, missing imports
- Update `CLAUDE.md` ONLY if the audit's "Documentation Drift Log" calls for a specific text update
- Add missing return statements, fix exception handling that swallows errors

## What you ARE NOT allowed to do

- Run any scraper / batch script
- Modify Supabase data via REST or SQL
- Change cron schedules
- Touch `data/` or `logs/` directories
- Install new dependencies
- Edit other workflow files in `.github/workflows/` unless the audit explicitly cites a workflow bug
- Auto-merge the PR
- Push to main directly

## When this prompt finishes

If a PR was opened, output the PR URL.
If no PR was needed, output a one-line reason.
If you aborted, output the abort reason.

That's it. Exit cleanly.
