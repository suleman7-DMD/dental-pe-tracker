# CENSUS RESUME - START HERE

**If you are resuming the Codex-orchestrated, 4-Claude-session, hand-verified ownership census of the
~4,439 Chicagoland (Illinois-only) dental practices, start with the current PM handoff:**

**`data/dso_research/RESEARCH_HOME/PROJECT_MANAGER_HANDOFF_20260702.md`**

That file supersedes this pointer for current review. It fixes the documentation drift found after shutdown:
- Fleet B ranks 51-100 are complete but not Gate-normalized or QA-accepted.
- The old June 22 DB md5 (`0dec26135bb4d6ee490dc16cfe892ca6`) is historical; the current local DB md5 observed on 2026-07-02 is `e2a89a02900d0366fad6d9ee06d23422`.
- The census-specific freeze is still intact: `ownership_tier` 0/0, LEDGER 1 line, PROGRESS 0 reviewed / 4,439 undetermined.
- The correct validate-only syntax is:
  `python3 scrapers/consolidate_census.py data/dso_research/_ready_to_validate_wave3_fixed_20260621.json --session NAME --validate-only`

Then read the historical master context file:

**`data/dso_research/RESEARCH_HOME/00_MULTI_SESSION_CENSUS_MASTER_CONTEXT.md`**

That file explains:
- the goal (hand-verify ownership tier of every IL GP location; replace the unreliable ~5.x% detector floor),
- the orchestration model (Codex = architect; 4 Claude sessions = **Gate Owner / Main AO / Fleet B / QA**;
  the human relays Codex's prompts; sessions coordinate via files, not chat),
- the locked 6-tier model + acceptance bar + protected networks,
- the frozen state at the time those sessions shut down,
- what each session has produced so far (Wave 4: initial partition, Lane 2, LABINOV addendum, Fleet B 51-100),
- and **boot prompts to relaunch each of the four sessions** exactly where they left off.

Census heartbeat / source of truth for "reviewed vs remaining":
`data/dso_research/RESEARCH_HOME/PROGRESS.json`

Sibling per-session role docs (each session wrote its own): look for `SESSION_*_MASTER_CONTEXT.md` /
`*_ROLE_*.md` in `data/dso_research/RESEARCH_HOME/` and `data/dso_research/`.

_Authored at shutdown 2026-06-22 by the QA session (1 of 4); updated 2026-07-02 by Codex to point first to the PM handoff._
