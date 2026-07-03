# Resume Pointer - Codex + 4-Claude-Session Ownership Census

**Current PM review entry point, updated 2026-07-02:**

`data/dso_research/RESEARCH_HOME/PROJECT_MANAGER_HANDOFF_20260702.md`

Read that file first. It is the current cleaned handoff for a project manager/coder reviewing the work.
It supersedes the older role-specific START_HERE files where status or hashes conflict. In particular:

- Fleet B ranks 51-100 are complete, but still need Gate normalization and fresh QA.
- The June 22 md5 `0dec26135bb4d6ee490dc16cfe892ca6` is historical. Current local DB md5 observed 2026-07-02 is `e2a89a02900d0366fad6d9ee06d23422`.
- The census freeze still holds: `ownership_tier` 0/0, LEDGER 1 line, PROGRESS 0 reviewed / 4,439 undetermined.
- Correct validate-only syntax is:
  `python3 scrapers/consolidate_census.py data/dso_research/_ready_to_validate_wave3_fixed_20260621.json --session NAME --validate-only`

If you (a fresh Claude session) were told something like:

> *"Previously I was working with **Codex orchestration + 4 Claude sessions** on my dental PE app to
> **hand-verify the ownership of each of the ~4,400 Chicagoland practices**. Can you find the memory /
> context / reference files for that?"*

The historical memory lives in the `RESEARCH_HOME/` folder - per-seat START_HERE
files (each seat left its own; they reconcile). Glob them all:
`ls data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_*.md`

```
data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_ORCHESTRATION.md     ← Gate Owner: shared cross-role INDEX (start here for the canonical overview)
data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_OWNERSHIP_CENSUS.md  ← Main AO: deepest record of the Main-AO seat
data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_FLEET_B.md           ← Fleet B: Phase-C work log + exact resume command (claude --resume <id>)
```

After the PM handoff, open these for the audit trail. Together they document: the 4 session roles (Main AO, Gate Owner, QA, Fleet B) + Codex
the architect + the user as relay; everything each session has done; the file-based coordination protocol;
the historical frozen invariants at shutdown; the Wave-4 state; and exactly how to re-open all four sessions to pick up
where work left off. **The freeze lifts only when the user types `consolidate approved manifest` to the
Gate Owner seat.**

```bash
cat data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_ORCHESTRATION.md      # canonical overview
cat data/dso_research/RESEARCH_HOME/START_HERE_CODEX_4SESSION_OWNERSHIP_CENSUS.md   # Main AO deep memory
ls -t data/dso_research/_wave4_20260621/_WAVE4_INTAKE_REGISTER_*.md                 # freshest status log
```

*(Pointer created 2026-06-22 by the Main AO session. Do not start mutating anything — read the master
file's §3 "hard locks" before any action.)*
