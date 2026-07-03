# 🔒 HANDOFF — RESET + CONSOLIDATION GATE OWNER (fresh session) — 2026-06-21

**You are inheriting the Reset + Consolidation Gate Owner role.** Mandate (user, verbatim):
> "Make it boring and strict: reset, taxonomy addendum, manifest, validate-only. No agents, no new research."

You are a **merger/validator/gatekeeper only**. No agent fleets, no new evidence hunting, no web search
for owners, no frontend edits, no `entity_classification`/`ownership_status` changes, no `practices`
deletes. `consolidate_census.py` is allowed in **`--validate-only` mode ONLY**. IL/Chicagoland only —
Boston/MA is PARKED.

---

## 1. CURRENT CANONICAL STATE — RE-QA #5 = PASS

The Wave-3 manifest has been through RE-QA #4 (MUST-FIX A/B/C) → fixes applied → **RE-QA #5 PASS**.

- **Gate state: CLEAR.** QA verdict (`ownership_manifest_QA_wave3_reqa5_20260621.json`):
  > "PASS — all RE-QA #4 MUST-FIX applied; consolidation gate is clear pending the user's explicit
  > 'consolidate approved manifest'."
- **No outstanding QA MUST-FIX.** All three checklist items (A/C demotions, B explicit SHAFI_REEM
  release, ddb update) returned **PASS**.
- **Consolidation remains FROZEN.** `consolidate_authorization.status = "NOT AUTHORIZED"` — `--allow-db-write`
  stays off until the user explicitly says **"consolidate approved manifest."**
- Validate-only on the 310-row file passes with zero DB writes; sidecars and held networks intact.

---

## 2. CANONICAL FILES (read these first)

| Role | Path |
|------|------|
| **Living manifest** (7 buckets + all sidecars + decisions) | `data/dso_research/consolidation_candidate_manifest_20260621.json` |
| **Validator-native ready set** (exactly what `--allow-db-write` would consume) | `data/dso_research/_ready_to_validate_wave3_fixed_20260621.json` (310 rows) |
| **Latest QA verdict** (RE-QA #5, PASS) | `data/dso_research/ownership_manifest_QA_wave3_reqa5_20260621.json` |
| Canonical current-ready mirror (also 310) | `data/dso_research/_ready_to_validate_wave2_20260621.json` |
| Taxonomy authority (DSO=STRUCTURE rule) | `data/dso_research/ownership_taxonomy_DSO_structure_gate_review_20260621.json` |
| Lane log (append-only) | `data/dso_research/_active_lane_reset_consolidation_gate_20260621.md` |
| Session audit trail | `data/dso_research/RESEARCH_HOME/SESSION_LOG.md` (Phase 7g = RE-QA #4 fixes) |
| Focused re-check request handed to QA | `data/dso_research/_QA_REVIEW_REQUEST_gate_manifest_20260621.md` |

> Prior-wave ready files (`_ready_to_validate_wave3_20260621.json` @315, `..._wave2..._merged...` @123/210,
> `..._normalized...` @65) are kept **for audit only** — do NOT consolidate from them. The 310-row
> `_ready_to_validate_wave3_fixed_20260621.json` is the only consolidation-eligible file.

---

## 3. COUNTS (core buckets mutually exclusive — 0 collisions asserted)

| Bucket | Count |
|--------|------:|
| **ready_to_validate** | **310** |
| needs_more_evidence | 167 |
| conflicts | 74 |
| rejected | 7 |
| evidence_gap_backfill_queue | 87 |
| taxonomy_revised | 14 (overlay annotation, not a core bucket) |
| **core-universe distinct locations** | **558** |
| core-bucket collisions | **0** |

Reconciliation: 310 ready + 167 needs_more + 74 conflicts + 7 rejected = **558** distinct. ✓

### Tier mix (ready 310)
| Tier | Count |
|------|------:|
| dentist_multi (T3) | 148 |
| branded_dso (T5) | 94 |
| true_independent (T1) | 30 |
| stealth_dso (T4) | 21 |
| institutional (T6) | 10 |
| single_loc_group (T2) | 7 |

### Evidence-basis mix (ready 310)
| Basis | Count |
|-------|------:|
| name_chain | 165 |
| web_verified | 81 |
| intel_dossier | 25 |
| locator | 19 |
| ein_cluster | 10 |
| structural | 7 |
| ao_cluster | 3 |

> **Headline discipline (informational, pre-consolidation only):** Consolidated = T2+T3+T4+T5 = **270**;
> DSO/PE = T4+T5 = **115**. These are candidate-set tallies. The REAL headline % is computed FROM the
> census LEDGER with coverage at consolidation time — **never** anchored to ADA 14.6% or the legacy 5%
> detector floor.

---

## 4. THE THREE FIXES APPLIED (RE-QA #4 MUST-FIX → confirmed by RE-QA #5)

### Fix A — 4 operating-status-risk rows DEMOTED ready → needs_more_evidence
`f6c6290c16d20224` (PINEWOOD DENTAL, PC / Orland Park 60467),
`822d3012aedf32b9` (OPTIMAL DENTAL ASSOCIATES, LLC / Tinley Park 60477),
`77357c36224272c8` (DENTAL DESIGN GROUP, INC / Naperville 60563),
`7d1d789828351ecf` (GENTLE DENTAL CARE P.C. / Chicago 60651).
- Each keeps full original row under `preserved_ready_row`, `backfill_lane="operating_status_unverified"`,
  network_id retained. **Why at the gate, not the validator:** these self-flag candidate/closed/operating-
  status-unverified, and `--validate-only` checks only schema + DB-state — it **cannot** catch active-door
  status. Held pending a live-website / current-locator / phone-active corroborator.

### Fix B — ao:SHAFI_REEM EXPLICITLY RELEASED as dentist_multi (all 3 stay in ready)
`ba663f30996016ce` + `fc658bf62642d908` corrected **branded_dso → dentist_multi**;
`6da55130228a9c54` already dentist_multi (reach3 QA regate).
- Recorded at `ao_network_release_decisions.decisions["ao:SHAFI_REEM"]` (evidence_quality=verified,
  decision=release_eligible, rows 3/3, tier=dentist_multi, pe_backed=false, tier_corrections logged,
  `covered_by_prior_release="ao:SHAFI_SOHAIL"`).
- **Rationale:** covered by the prior VERIFIED `ao:SHAFI_SOHAIL`/Two Rivers Dental release (also
  dentist_multi, pe_backed=false; whose stale_closed_notes already name Reem Shafi/Two Rivers) + the
  reach3 QA regate. Tier rests on **absence of any MSO/management-company/platform structure
  (DSO=STRUCTURE)** + prior-network consistency — **explicitly NOT a pe_backed=false downgrade.**

### Fix C — duplicate-door leak DEMOTED ready → needs_more_evidence
`ff41419130267bd9` (Peters, Erika / 2340 N Clybourn Ave / 773-528-2205; was ready dentist_multi via
Fleet B ein-015, EIN 362686478).
- Same physical door as `f94fb29cc7d444cd` (CHICAGO DENTAL PROFESSIONALS INC, prior true_independent, in
  NO live bucket) — a door cannot carry both consolidated and independent.
- Demoted with `preserved_ready_row`, `backfill_lane="duplicate_door_tier_conflict"`;
  `buckets.duplicate_denominator_blocked.currently_in_candidate_set` updated from stale `[]` to the
  leak/fix record; pair added to `duplicate_denominator_blocked.pairs` (now the 9th pair).

**Net count effect:** ready 315 → **310** (−4 Fix A, −1 Fix C; Fix B kept all 3 in ready, moving 2 from
branded_dso to dentist_multi). needs_more_evidence 162 → 167.

---

## 5. RESET INVARIANT (must remain TRUE at all times — re-verified this session)

| Invariant | Required | Current |
|-----------|----------|---------|
| `--allow-db-write` ever run | NO | **NO** |
| `practice_locations.ownership_tier` non-null | 0 | **0** |
| `practices.ownership_tier` non-null | 0 | **0** |
| `RESEARCH_HOME/LEDGER.jsonl` lines | 1 (header only) | **1** |
| `PROGRESS.json` undetermined_unreviewed | 4439 | **4439** |
| `PROGRESS.json` tier_tally (non-undetermined) | all zero | **all zero** |

If ANY of these is non-zero/changed, a write leaked — STOP and investigate before any further action.
Reversible backups exist: `data/dental_pe_tracker.db.pre_reset_bak_20260621`,
`RESEARCH_HOME/LEDGER_wave1_candidate_quarantine_20260621.jsonl`,
`RESEARCH_HOME/PROGRESS_wave1_candidate_quarantine_20260621.json`,
`data/dso_research/wave1_active_ownership_export_20260621.json`.

**Re-verify command:**
```bash
python3 -c "import sqlite3,json; c=sqlite3.connect('data/dental_pe_tracker.db'); \
print('PL', c.execute('SELECT COUNT(*) FROM practice_locations WHERE ownership_tier IS NOT NULL').fetchone()[0]); \
print('P', c.execute('SELECT COUNT(*) FROM practices WHERE ownership_tier IS NOT NULL').fetchone()[0]); \
print('LEDGER', sum(1 for _ in open('data/dso_research/RESEARCH_HOME/LEDGER.jsonl'))); \
print('PROGRESS', json.load(open('data/dso_research/RESEARCH_HOME/PROGRESS.json'))['tier_tally']['undetermined_unreviewed'])"
```

**Validate-only command (safe, no writes):**
```bash
python3 scrapers/consolidate_census.py data/dso_research/_ready_to_validate_wave3_fixed_20260621.json \
  --session gate_owner_handoff_20260621 --validate-only
# expect: "Loaded 310 classification rows … Validation OK … no DB/ledger/progress writes."
```

---

## 6. WHAT REMAINS FROZEN / HELD

- **CONSOLIDATION IS FROZEN.** Do NOT run `consolidate_census.py --allow-db-write` until the user types
  the exact trigger: **"consolidate approved manifest."** QA `consolidate_authorization = NOT AUTHORIZED`.
- **PROTECTED NETWORKS — Sweis + Ramaha** stay `protected_network_hold=true` in needs_more_evidence until
  an EXPLICIT per-network release. Network evidence_quality = partial, 0 verified rows, documented
  closed/vacated-shell false-positive caveats. **Do NOT auto-release on mere new evidence.**
- **Webster / Berwyn** rows (`917453ec`, `264b213a`, `89d78c91`, `3bc304a`, `12975f69`) stay in the **74
  conflicts** pending whole-network adjudication (Webster Dental Management MSO note attached, NOT
  auto-promoted).
- **Duplicate-door hazard:** 9 documented same-door pairs in `duplicate_denominator_blocked`. Any future
  wave must collapse the dup and resolve to ONE tier before consolidating those addresses.
- **Intelligence preserved (do not flatten):** sidecars `ao_network_intelligence` (wave1 6 nets +
  wave2_reach4 14 + wave3_reach3 51), `fleet_b_lane1B` (320 rows), `fleet_b_wave3` (720 rows; **694
  needs_verification preserved as hidden-local-consolidator LEADS**). AO reach = discovery SIGNAL, never
  proof — but AO clusters are high-value leads and must be kept.

---

## 7. EXACT NEXT CHOICES FOR THE USER

The gate is clear. The user picks ONE:

**Option (a) — Consolidate the 310 now.**
On the user's explicit "consolidate approved manifest," run:
```bash
python3 scrapers/consolidate_census.py data/dso_research/_ready_to_validate_wave3_fixed_20260621.json \
  --session <session_name> --allow-db-write
```
This writes the 6 ownership-axis columns to `practice_locations` + underlying `practices`, appends to
`LEDGER.jsonl`, recomputes `PROGRESS.json`. After: re-verify counts, update lane log + SESSION_LOG.
(Frontend/Supabase sync is a SEPARATE later decision — not part of this consolidation.)

**Option (b) — Continue evidence work first, THEN consolidate.**
Files-only, no DB writes. Highest-leverage remaining work:
- Resolve the **74 conflicts** (incl. Webster/Berwyn whole-network adjudication).
- Work the **87 evidence_gap_backfill_queue** rows (lanes: AO_network, locator_exact, practice_intel,
  operating_status_unverified, duplicate_door_tier_conflict).
- Mine the **694 fleet_b_wave3 needs_verification leads** for hidden local consolidators.
- Consider explicit release of **Sweis/Ramaha** if (and only if) verified documentary MSO/structure
  evidence + an explicit per-network release is warranted.
- Re-validate → request a fresh QA pass → then Option (a).

In BOTH cases the gate owner does NOT gather new evidence itself, does NOT run agent fleets, and runs
`--allow-db-write` ONLY on the explicit user trigger.

---

*Authored 2026-06-21 by the outgoing Gate Owner (Opus 4.8, autonomous). No merges, research, or DB writes
were performed to produce this handoff — read-only state capture only.*
