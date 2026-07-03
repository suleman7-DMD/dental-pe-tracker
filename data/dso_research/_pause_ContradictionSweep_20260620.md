# Contradiction Sweep Agent — Pause Checkpoint (2026-06-20)

**Status: COMPLETE — full report already sent to team-lead via SendMessage.**

---

## 1. What Has Been Completed

The entire charter is done. All three deliverables were produced and transmitted to the team lead:

1. **Contradiction / Staleness Ledger** — every doc-vs-DB discrepancy found, each spot-checked with sqlite3
2. **Data Asset Inventory** — every ownership-relevant table, column, evidence JSON, and scratch .txt file catalogued with coverage numbers
3. **Blind Spots / What's Being Left Out** — opinionated analysis of over- and under-investigated areas

The full report was sent via `SendMessage` to `team-lead` in the previous turn.

---

## 2. Key Findings (summary)

### Ground Truth (DB-verified)
- Floor: **268/4,801 = 5.58%** (IL: 249/4,439 = 5.61%; MA: 19/362 = 5.25%)
- NPI corporate: **1,152** (680 dso_regional + 472 dso_national)
- Location corporate: **268** (82 dso_regional + 186 dso_national)
- Total practice_locations: 5,657 (stable)
- da_unverified: 179 (stable)

### Staleness Ledger (key items)
- Root `CLAUDE.md`: ~1 week stale — shows 261/4,811 = 5.43% (pre-2026-06-19 promotions). All NPI and location classification breakdowns off. Missing `duplicate_location` class (5 rows at both levels).
- `scrapers/CLAUDE.md`: ~3 months stale — shows 5.27% floor, 2,861 deals, 8-page Next.js app. Treat as obsolete.
- `CHICAGOLAND_FLOOR_PLAN_2026-06-20.md`: matches DB exactly — this is the authoritative current-state doc.
- `flip_queue_b_union.json`: CLAUDE.md says 315 candidates (17/15/283); actual file has **1,264 candidates** (21/89/1,154). Floor projection in JSON still references stale 5.27%/4,608 denominator.
- One 1-row discrepancy: ZIP 60045 has location 951701941a7097e5 (MIKE MIN W KANG, state=CA) in zip=60045. zip_scores = 12, direct practice_locations count = 13. Not material to floor.

### Data Asset Inventory highlights
- `practices`: 11,693 watched IL NPI rows. `mailing_address` 95.6% populated; `da_officers` 55.9%; `authorized_official_last_name` 29.2%.
- `practice_intel`: 3,370 rows, all IL. 2,069 unique GP locations have intel coverage (~46%).
- **CRITICAL**: 289 independently-classified IL practices have practice_intel flagging a named DSO or "NOT a solo/independent." 1,062 have "acqui" in their assessment. None of this feeds back into entity_classification.
- Scratch .txt files: at-risk untracked Tranche A2 research (Gryphon, Shore, JLL, Calera, EIN 731689410 cluster, Evenly). Gryphon EIN 125555555 is a placeholder like Evenly's 000000000 — needs same audit before promoting.

### Top Blind Spots
1. `practice_intel` as classification signal — highest-leverage free action available
2. `mailing_address` clustering (95.6% coverage, unmined systematically)
3. `authorized_official_last_name` clustering (3,409 rows, direct multi-location owner signal)
4. T2 (dentist-owned multi-location) not representable in current schema
5. `practice_signals.stealth_dso` flag — not audited, potentially high-value triage layer

---

## 3. Remaining TODO

**Nothing.** The charter is fully executed. The report is in the team-lead's inbox.

On GREEN LIGHT, no further work is needed from this agent unless the team-lead requests a follow-up drill-down (e.g., pulling the 289 practice_intel mismatch rows into a structured list, or running the mailing-address cluster query).
