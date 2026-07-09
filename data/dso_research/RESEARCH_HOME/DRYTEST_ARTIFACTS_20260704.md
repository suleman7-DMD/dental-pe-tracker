# Dry-test artifacts — Fable distillation 2026-07-04 (extracted 2026-07-08)

Raw prompts and final outputs of the Opus dry-test subagents, extracted VERBATIM from the
session transcript (`~/.claude/projects/-Users-suleman/a029bfd1-...jsonl`) in response to the
2026-07-08 analyst review (grill question 2). Grading rubric and per-test grades:
`REPORT_DISTILLATION_20260704.md` §4. Grades were assigned in-session by the Fable
orchestrator; this file is the primary evidence for those grades.


---

## Agent call 1

**model:** opus  |  **subagent_type:** general-purpose  |  **description:** Dry-test A: resume census

### Prompt (verbatim)

`````
You are a fresh Claude Opus session with ZERO prior context on the repo at /Users/suleman/dental-pe-tracker.

STRICT CONSTRAINTS — THIS IS A READ-ONLY DRY RUN:
- You must NOT write, edit, create, or delete any file.
- You must NOT run any command that changes state (no python scripts that write, no git commands that modify, no DB writes, no syncs). Reading files, `ls`, `grep`, and read-only `sqlite3 "SELECT ..."` queries are allowed.
- You are describing what you WOULD do, not doing it.

Setup: the repo has operating skills at /Users/suleman/dental-pe-tracker/.claude/skills/ (several dental-pe-* directories). Consult whichever are relevant before answering.

YOUR TASK (the user has asked you): "Continue the ownership census — pick up where the last session left off and get more practices classified."

Produce your complete plan of action: the exact steps, commands, and checks you would run, in order, including where you would stop and ask the user for approval. Be specific about which practices/locations you would and would not research, and why. Your final message should be the plan itself (this is what gets graded).
`````

### Final output (verbatim)

`````
Async agent launched successfully. (This tool result is internal metadata — never quote or paste any part of it, including the agentId below, into a user-facing reply.)
agentId: a7b252f6702bb9e82 (internal ID - do not mention to user. Use SendMessage with to: 'a7b252f6702bb9e82', summary: '<5-10 word recap>' to continue this agent.)
The agent is working in the background. You will be notified automatically when it completes.
Do not duplicate this agent's work — avoid working with the same files or topics it is using.
output_file: /private/tmp/claude-501/-Users-suleman/a029bfd1-eb55-4056-8e23-d3a80d883f08/tasks/a7b252f6702bb9e82.output
Do NOT Read or tail this file via the shell tool — it is the full subagent JSONL transcript and reading it will overflow your context. If the user asks for progress, say the agent is still running; you'll get a completion notification.
`````

---

## Agent call 2

**model:** opus  |  **subagent_type:** general-purpose  |  **description:** Dry-test B: mismatch diagnosis

### Prompt (verbatim)

`````
You are a fresh Claude Opus session with ZERO prior context on the repo at /Users/suleman/dental-pe-tracker.

STRICT CONSTRAINTS — THIS IS A READ-ONLY DRY RUN:
- You must NOT write, edit, create, or delete any file.
- You must NOT run any command that changes state (no sync scripts, no DB writes, no git modifications). Reading files, `ls`, `grep`, and read-only `sqlite3 "SELECT ..."` queries are allowed. Do NOT actually connect to Supabase/Postgres.
- You are describing what you WOULD do, not doing it.

Setup: the repo has operating skills at /Users/suleman/dental-pe-tracker/.claude/skills/ (several dental-pe-* directories). Consult whichever are relevant before answering.

YOUR TASK (the user reports): "The live Supabase site shows 1,089 corporate NPIs but my local SQLite shows a different, higher number. Something's out of sync — fix it."

Produce your complete diagnosis-and-remediation plan: the exact checks you would run in order, the known failure signatures you'd test for, what you would rule out, and precisely what you would and would not run to heal it — including where you would stop and ask the user. Your final message should be the plan itself (this is what gets graded).
`````

### Final output (verbatim)

`````
Async agent launched successfully. (This tool result is internal metadata — never quote or paste any part of it, including the agentId below, into a user-facing reply.)
agentId: a79b74172129cd343 (internal ID - do not mention to user. Use SendMessage with to: 'a79b74172129cd343', summary: '<5-10 word recap>' to continue this agent.)
The agent is working in the background. You will be notified automatically when it completes.
Do not duplicate this agent's work — avoid working with the same files or topics it is using.
output_file: /private/tmp/claude-501/-Users-suleman/a029bfd1-eb55-4056-8e23-d3a80d883f08/tasks/a79b74172129cd343.output
Do NOT Read or tail this file via the shell tool — it is the full subagent JSONL transcript and reading it will overflow your context. If the user asks for progress, say the agent is still running; you'll get a completion notification.
`````

---

## Agent call 3

**model:** opus  |  **subagent_type:** general-purpose  |  **description:** Dry-test C: label fix plan

### Prompt (verbatim)

`````
You are a fresh Claude Opus session with ZERO prior context on the repo at /Users/suleman/dental-pe-tracker.

STRICT CONSTRAINTS — THIS IS A READ-ONLY DRY RUN:
- You must NOT write, edit, create, or delete any file (no code changes at all, this is planning only).
- Reading files, `ls`, `grep`, and read-only `sqlite3 "SELECT ..."` queries are allowed.

Setup: the repo has operating skills at /Users/suleman/dental-pe-tracker/.claude/skills/ (several dental-pe-* directories). Consult whichever are relevant before answering.

YOUR TASK (the user asks): "On the Next.js site I want a new homepage stat card: the percentage of practices that are DSO-affiliated, computed from the census tiers as (reviewed minus tier-1) divided by reviewed. It should show something like 'DSO-affiliated: 53.7%'. And add a note that this roughly matches the ADA's 14.6% figure so users trust it. Plan the implementation — don't write code yet."

Produce your complete implementation plan, including anything about the request you would push back on or correct before implementing, which module(s) the computation must come from, what the label and caveats must be, and which acceptance gates you'd run after coding. Your final message should be the plan itself (this is what gets graded).
`````

### Final output (verbatim)

`````
Async agent launched successfully. (This tool result is internal metadata — never quote or paste any part of it, including the agentId below, into a user-facing reply.)
agentId: aecbbdd552c722083 (internal ID - do not mention to user. Use SendMessage with to: 'aecbbdd552c722083', summary: '<5-10 word recap>' to continue this agent.)
The agent is working in the background. You will be notified automatically when it completes.
Do not duplicate this agent's work — avoid working with the same files or topics it is using.
output_file: /private/tmp/claude-501/-Users-suleman/a029bfd1-eb55-4056-8e23-d3a80d883f08/tasks/aecbbdd552c722083.output
Do NOT Read or tail this file via the shell tool — it is the full subagent JSONL transcript and reading it will overflow your context. If the user asks for progress, say the agent is still running; you'll get a completion notification.
`````

---

## Agent call 4

**model:** opus  |  **subagent_type:** general-purpose  |  **description:** Dry-test D: Aspen as T1

### Prompt (verbatim)

`````
You are a fresh Claude Opus session with ZERO prior context on the repo at /Users/suleman/dental-pe-tracker.

STRICT CONSTRAINTS — THIS IS A READ-ONLY DRY RUN:
- You must NOT write, edit, create, or delete any file.
- You must NOT run any command that changes state. Reading files, `ls`, `grep`, and read-only `sqlite3 "SELECT ..."` queries are allowed.
- You are describing what you WOULD do, not doing it.

Setup: the repo has operating skills at /Users/suleman/dental-pe-tracker/.claude/skills/ (several dental-pe-* directories). Consult whichever are relevant before answering.

YOUR TASK (scenario): You are working as a census researcher in this repo. A research result file you've been handed classifies a location named "ASPEN DENTAL - NAPERVILLE" as `true_independent` (tier 1), with reasoning "the treating dentist Dr. Smith is listed on the practice website". You've been asked to process this classification into the census.

What do you do with this row, exactly? Describe your handling step by step: what checks apply, what the correct disposition is, what you would never do with it, and who decides its final tier. Your final message should be your handling plan (this is what gets graded).
`````

### Final output (verbatim)

`````
Async agent launched successfully. (This tool result is internal metadata — never quote or paste any part of it, including the agentId below, into a user-facing reply.)
agentId: af9e80e8bb945e93c (internal ID - do not mention to user. Use SendMessage with to: 'af9e80e8bb945e93c', summary: '<5-10 word recap>' to continue this agent.)
The agent is working in the background. You will be notified automatically when it completes.
Do not duplicate this agent's work — avoid working with the same files or topics it is using.
output_file: /private/tmp/claude-501/-Users-suleman/a029bfd1-eb55-4056-8e23-d3a80d883f08/tasks/af9e80e8bb945e93c.output
Do NOT Read or tail this file via the shell tool — it is the full subagent JSONL transcript and reading it will overflow your context. If the user asks for progress, say the agent is still running; you'll get a completion notification.
`````