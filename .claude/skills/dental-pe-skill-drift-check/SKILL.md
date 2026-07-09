---
name: dental-pe-skill-drift-check
description: Run FIRST in any session that will rely on dental-pe-* skill numbers, and whenever auditing whether the skills have drifted from the live repo. Executes every volatile skill claim's recheck against the live DB and filesystem (read-only by construction) and reports PASS/DRIFT per claim.
---

# Skill Drift Check

The dental-pe-* skills carry dated, falsifiable numbers. This skill makes them machine-
auditable: `claims.json` lists every volatile claim, which skill states it, its recheck, and
what to do on drift. The runner opens the DB read-only (`mode=ro` URI) — it cannot write.

## Run

```bash
python3 .claude/skills/dental-pe-skill-drift-check/check_claims.py
```

Exit 0 = every claim holds. Exit 1 = drift; the table names each drifted claim.

## On drift

- **Number drift** (census grew, universe changed): update the named skill sections AND the
  `expected` value in `claims.json` in the SAME change, both date-stamped. Skills and manifest
  must never disagree.
- **Guarded-invariant drift** (detector floor, census floors, two-axis counts DROPPING): this
  is an incident, not doc debt. STOP, load `dental-pe-failure-archaeology`, diagnose before
  touching any doc. Never edit `expected` to silence a drift — re-basing a guarded number
  requires the full evidence standard in `dental-pe-validation-and-qa` §3.
- **`report_only` claims** (deals) have no expected value by design — they are volatile;
  query fresh every time.

## Maintenance

When a skill gains or loses a dated claim, update `claims.json` in the same commit. A claim
in a skill with no manifest entry is unaudited prose — the thing this skill exists to prevent.
