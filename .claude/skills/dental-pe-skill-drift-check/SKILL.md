---
name: dental-pe-skill-drift-check
description: Run FIRST in any session that will rely on dental-pe-* skill numbers, and whenever auditing whether the skills have drifted from the live repo. Executes every volatile skill claim's recheck against the live DB and filesystem (read-only by construction) and reports PASS/DRIFT per claim.
---

# Skill Drift Check

The dental-pe-* skills carry dated, falsifiable numbers. This skill makes them machine-
auditable: `claims.json` lists every volatile claim, which skill states it, its recheck, and
what to do on drift. The runner opens the DB read-only (`mode=ro` URI) and only reads/parses
files (stdlib `ast` for ORM introspection — it never imports project code) — it cannot write.

## Run

```bash
python3 .claude/skills/dental-pe-skill-drift-check/check_claims.py          # full (local)
python3 .claude/skills/dental-pe-skill-drift-check/check_claims.py --no-db  # CI / no DB
```

Exit 0 = every checked claim holds. Exit 1 = drift; the table names each drifted claim.

## Claim classes

Every claim carries a `class` that tells you how to react:

- **floor** — guarded safety minimum (detector floors, ORM census-column mapping, append-only
  LEDGER line count, result-file ground truth, frontend truth-contract exports/adoption).
  Dropping = INCIDENT: stop, load `dental-pe-failure-archaeology`, diagnose before touching
  any doc. Never edit `expected` to silence it — re-basing a guarded number requires the full
  evidence standard in `dental-pe-validation-and-qa` §3.
- **snapshot** — dated state (tier tallies, universe denominators, the P1′ queue
  decomposition, triage reason tallies). Drift means the skill text needs a dated refresh:
  update the named skill sections AND the manifest value in the SAME change, both
  date-stamped. Skills and manifest must never disagree.
- **report** — volatile by declaration (deals). Printed, never judged; query fresh every time.

## Claim kinds

`sql` (scalar query, ro), `glob` (file count), `grep` (regex count in one file), `grep_dir`
(count of files under a dir matching a regex — e.g. how many frontend files import
`ownership-truth`), `lines` (line count), `json_len` / `json_tally` (triage-file row count and
per-`_triage_reason` tallies), `derived` (arithmetic over other claims' actuals — e.g.
91 holds = 52+30+9, residual 5, and 1,259 = il_universe − census_tiered), `queue_recon`
(re-derives the whole P1′ queue decomposition from scratch using the canonical predicate:
`pl.state='IL'`, GP-eligible entity classes, non-residential — NOT a watched_zips join, which
overcounts by one), `orm_columns` (AST-verifies the census columns are assigned on the named
ORM classes in `scrapers/database.py`, the strip-bug guard).

## CI mode (`--no-db`) and `local_only`

The SQLite DB and the nested `dental-pe-nextjs` repo exist only on the pipeline Mac — neither
is in git. So CI runs `--no-db`: DB-dependent claims (and derived claims whose inputs were
skipped) SKIP with a printed reason, and `local_only` claims auto-SKIP when their target path
is absent. A missing path on any claim NOT marked `local_only` is DRIFT. **A SKIP is not a
PASS** — the CI run covers file/AST/tally claims only (~16 of 45); full coverage is the local
run. The workflow lives at `.github/workflows/skill-drift.yml`.

## Maintenance

When a skill gains or loses a dated claim, update `claims.json` in the same commit. A claim
in a skill with no manifest entry is unaudited prose — the thing this skill exists to prevent.
`derived` claims must appear after the claims they reference. When adding a triage reason,
add its `json_tally` claim AND update the `triage_residual` derivation.
