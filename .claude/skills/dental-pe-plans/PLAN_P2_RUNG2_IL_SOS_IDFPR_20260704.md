# P2 — Hidden-Corporate Escalation, Rung 2: IL SoS + IDFPR (authored 2026-07-04)

**Goal:** surface MSO-hidden corporate practices sitting inside the census's T1/T2/T3 rows,
using Illinois Secretary of State business-entity records and IDFPR license data. Output is a
SUSPECTS file with evidence — **never a tier change**. Suspects feed the census triage/holds
machinery (P1′ Tracks), where the normal gates decide.

**Source of truth:** `RESEARCH_HOME/PLAN_HIDDEN_CORPORATE_ESCALATION_20260703.md` (threat
model + full signal catalog). This artifact is its Rung-2 execution wrapper.

**Why this exists:** the IL Dental Practice Act forces corporate ownership to hide behind
dentist-named PCs managed via MSAs — so a practice can be genuinely dentist-OWNED on paper
while corporate-CONTROLLED in fact. AO/EIN mismatch alone is NOT proof (ruling R6: structure
≠ control); Rung 2 adds state-registry signals that name/EIN matching can't see.

**Write-set:** a new scraper under `scrapers/` (read-only against state sites), dated output
files under `data/dso_research/`. NO tier writes, NO Supabase writes, NO detector
(`entity_classification`) writes.

---

## Phase 0 — Preflight + Rung 1 precondition

Rung 2 prioritizes suspects from Rung 1 (the free in-hand sweep: S1 AO-mismatch, S2
EIN-parent clustering, S3 mailing divergence, S4 shared phone, S5 Data-Axle legal-name).

```bash
ls data/dso_research/_hidden_corp_suspects_rung1.json
```

**As of 2026-07-04 this file does NOT exist — Rung 1 has not run.** If still absent, execute
Rung 1 first per the source plan (deterministic, existing-data-only, cheap): write
`scrapers/detect_hidden_corp_rung1.py` emitting
`data/dso_research/_hidden_corp_suspects_rung1.json` with per-suspect signal list and scores.
Verification: suspect count printed; spot-check 5 rows against the DB. **Trap:** treating any
single Rung-1 signal as sufficient — they are prioritization, not proof.

## Phase 1 — Rung 2 scraper (IL SoS + IDFPR)

Build `scrapers/hidden_corp_rung2_il_sos.py` collecting, for each Rung-1 suspect's legal
entity (and its address-mates):

- **S6 — registered-agent fingerprint:** agent is a corporate-services firm or a known
  MSO/DSO law firm rather than the dentist.
- **S7 — non-dentist managers/officers:** LLC managers or corp officers who hold no IDFPR
  dental license.
- **S8 — shared agent/address across many dental entities:** one agent or office address
  fronting ≥3 distinct dental PCs/LLCs in different ZIPs.
- **S9 — entity churn:** recent amendments/conversions/mergers around known acquisition dates
  (cross-reference `deals` for context only — deal rows are never location-level proof).

Rules of engagement: public pages only, polite rate limits with backoff, cache raw responses
under `data/dso_research/raw_sos/` so reruns don't re-hit the state sites, no CAPTCHA/auth
circumvention — if the portal blocks automated access, STOP and present the manual-lookup
list to the user instead.

**Verification:** for 5 hand-picked suspects, paste the raw SoS/IDFPR record next to the
extracted fields — extraction must match source. **Trap:** fuzzy name matching pulling in the
wrong entity (dentist names collide; match on address + exact entity name, log ambiguities as
`ambiguous`, never guess).

## Phase 2 — Scoring + suspects file

Combine Rung 1 + Rung 2 signals into
`data/dso_research/_hidden_corp_suspects_rung2_<date>.json`: per suspect — location_id, npi,
current tier, signals fired (S1–S9) with raw evidence snippets/URLs, and a proposed queue
(`dso_verify_hold` for strong multi-signal cases, `watchlist` for weak ones).

**Verification:** every suspect row carries ≥2 independent signals for the hold queue;
single-signal rows go to watchlist only. **Trap:** scoring shared LANDLORD addresses as S8
(medical office buildings front many unrelated PCs — require the agent, not just the address,
to repeat).

## Phase 3 — HUMAN GATE → hand to census machinery

Present the suspects file to the user with counts by strength. On approval, strong suspects
enter the census triage/holds flow (P1′ Track B style research with the Rung-2 evidence
attached). Tier changes then happen ONLY via the standard merge→consolidate chain with its
adversarial T4/T5 CONFIRM gate.

---

## Stop conditions

- State portal blocks/rate-limits hard → stop scraping, report, propose manual batch.
- Any temptation to write tiers, flip `entity_classification`, or "just fix" an obvious case
  directly — that routes around change control; the census chain is the only tier writer.
- Signal hit-rate wildly off plan expectations (e.g., S8 firing on >20% of suspects) — the
  signal is miscalibrated; recalibrate with the user before scoring.
