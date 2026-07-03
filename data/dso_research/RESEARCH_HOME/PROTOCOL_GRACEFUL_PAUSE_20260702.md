# GRACEFUL PAUSE / RESUME PROTOCOL — usage-window management for agent fleets

> Written 2026-07-02 after the first rate-limit death + session restart burned ~30% of a fresh
> usage window on recovery overhead. This protocol makes pause/resume cost ~2-3% instead.
> Applies to ANY session running Workflow fleets on this project. PM = the Fable session.

## Why the ungraceful path is expensive (measured this session)

1. **In-flight agents die with zero output.** Each workflow runs ~6 agents concurrently; a Sonnet
   research agent is ~40-80k tokens, an Opus verifier ~60k. Hitting the wall mid-run wastes all
   of it — first flight lost ALL 25 verify agents' work this way and it had to be re-run.
2. **Session death → compaction → restart.** The restarted session re-reads the full summary +
   CLAUDE.md + runbooks uncached, re-adopts workflows, and re-verifies disk state. That overhead
   is what consumed the visible chunk of the window on 2026-07-02.
3. **Verify verdicts live only in journals/return payloads** (research results go to disk, but
   inline verdicts don't). A dead workflow means Opus re-runs unless journals are hand-harvested.

## THE PROTOCOL

### User side (two words, that's it)

- **"pause"** (say it at ~20% window remaining — leave headroom for the pause itself)
- **"resume"** (after the window resets)

### PM side on "pause" (≤5 tool calls, ~1-2 minutes)

1. `TaskStop` every running workflow task (IDs in the monitoring task + runbook §6a table).
   Completed `agent()` calls are already journaled/cached — stopping loses ONLY the ~6 in-flight
   agents per workflow, the unavoidable minimum.
2. One `Bash`: count `result_unit_*.json` on disk, list still-missing unit numbers.
3. Append a 5-line PAUSE SNAPSHOT to `MASTER_RESUME_LANE_A_FLEET_20260702.md` (timestamp, disk
   count, missing units, run IDs to resume, verdicts-file state). `git commit`.
4. Reply "PAUSED" with the snapshot. Then **no further tool calls** — the session idles alive.
   No ScheduleWakeup, no polling. An idle session costs nothing.

### PM side on "resume" (≤4 tool calls)

1. One `Bash`: re-count disk (ground truth may have grown — agents sometimes finish writes
   during the stop).
2. `Workflow({scriptPath, resumeFromRunId: <same run ID>, args: <same args>})` per fleet leg.
   Cached agents replay instantly and free; only lost in-flight + never-started agents run.
   This cross-session/same-session resume pattern is PROVEN (runbook §6a, commit ada1618).
3. Update the monitoring task with new task IDs. Continue.

### Hard rules (both sides)

- **Never let the window expire with workflows running** if the user is present to say "pause".
  Let-it-ride is only for when the user is AFK (completed units still persist; §4D applies).
- **Never launch a new wave below ~30% window remaining.** Finish-what's-running only.
- **The PM session must NOT be restarted/cleared while fleets run** — an idle-paused session
  resumes for pennies; a restarted one pays full context reload. If a restart happens anyway,
  §6a's same-run-ID resume still recovers everything but costs more.
- PM monitoring is passive: workflows auto-notify on completion. No status polling between
  notifications; every "let me check progress" Bash call is optional and should be batched.

## Structural fixes for FUTURE waves (do not touch in-flight workflows)

1. **Verify agents write verdicts to disk.** Add to the v2 script's verify prompt: "Also Write
   your verdicts to `_lane_a_20260702/_verdicts_unit_<NNN>.json`". Then verify work survives any
   death as a file-read — no Opus re-runs, no journal archaeology. (Agents have fs access;
   workflow scripts don't.) Apply when building the waves-1+2 intel-backfill script.
2. **Chunk waves ≤20 units** so any single unresumable workflow ("adopt scriptPath rejected" is
   possible on restart) has a small blast radius.
3. **Snapshot run IDs + args into the runbook AT LAUNCH TIME, same turn** (already practiced —
   keep doing it; it is what made §6a recovery possible).

## Cost accounting reference

- Fleet subagents (Sonnet research + Opus verify) are the dominant window consumers — that is
  the real work, not overhead. Overhead to minimize = duplicated agent runs + context reloads.
- Verdict recovery of 25 units cost ~1.57M subagent tokens. Avoid ever needing it again
  (structural fix #1).
