# Hidden Local Consolidator Discovery Wave 2 — 2026-06-21

## Purpose

This is a high-throughput evidence-gathering wave, not a consolidation/write wave.

Goal: surface the local ownership networks behind Chicagoland dentistry:
- dentist/family consolidators
- founder-led multi-location groups
- friendly-PC / LLC / LTD shell structures
- MSO / platform operators
- PE-backed DSOs where documentary evidence exists
- local brands that do not look corporate from the outside

The output must preserve network intelligence for future app use, not only row-level tier fields.

## Hard rules

- IL / Chicagoland only. MA/Boston remains parked.
- No DB writes.
- No `--allow-db-write`.
- Do not mutate `ownership_tier`, LEDGER, or PROGRESS.
- AO reach is a discovery signal, not proof.
- A row can be a valuable network lead even when it is not ready for final classification.
- Preserve unresolved/stale/closed/false-positive notes.
- Highest agent output status is `ready_for_validation`, never final.

## Current gate state at launch

The Gate Owner has merged Fleet B + Main AO backfill into the manifest:
- `ready_to_validate`: 123
- `needs_more_evidence`: 168
- `conflicts`: 74
- `evidence_gap_backfill_queue`: 55
- validate-only on `_ready_to_validate_merged_20260621.json` passes
- consolidation remains frozen pending QA and explicit user approval

This Wave 2 may run in parallel because it writes evidence files only.

## Primary hunt lanes

### Lane A — Main AO: staged reach=4 AO networks

Run the staged reach=4 batch in `scrapers/ao_network_evidence.js`.

Targets currently staged in the runner:
- BELINDA HUERTA
- LAWRENCE GROH
- OSCAR GONZALEZ
- STEVE NAPIER
- MOHAMED WAHEED
- KHALIL TAKLA
- LINDSAY BEARDEN
- STEVEN REMPAS
- SANJEEV PAL
- NAGARAJ
- HARALAMPOPOULOS
- PARIKH
- KURAL
- HOFFMAN

Expected output:
- `data/dso_research/ao_network_evidence_reach4_20260621.json`
- `data/dso_research/ao_network_evidence_reach4_20260621_qa.json`
- network-level sidecar/summary preserving ownership intelligence

Every network summary should include:
- AO/person name
- network_id
- linked location_ids, names, ZIPs, addresses
- owner/family/operator identity where documented
- brand/trade names
- legal entities / PCs / LLCs / LTDs
- EIN/address/name-chain artifacts
- MSO/platform/PE evidence if present
- stale/closed/false-positive notes
- evidence_chain: AO signal -> documentary corroboration
- recommended tier and confidence
- future_app_notes

### Lane B — Fleet B: staged Lane 1B explicit ownership rows

Release the staged Tier B explicit-ownership feed, not broad random scraping.

Targets:
- `data/dso_research/_shards_fleet_b/_feed_w2_lane1B_*.json`
- tightened set: about 236 rows

Purpose:
- mine `practice_intel` and DB evidence for explicit ownership/network language
- surface founder/family/local-brand groups
- avoid boilerplate "owner-operated" false positives

Expected output:
- `data/dso_research/ownership_evidence_queue_fleet_b_lane1B_20260621.json`
- validation txt
- QA flags
- network-intelligence sidecar if clusters emerge

### Lane C — Fleet B or a fresh data-hunt session: local brand/EIN cluster discovery

Build a new candidate file from the DB, evidence-only:
- same brand across 3+ ZIPs
- same EIN across 3+ ZIPs
- local brand names with multiple legal shells
- `dso_regional` rows that may actually be dentist/family-owned consolidators
- `dentist_multi` rows that may hide MSO/platform structure

Do not auto-classify. Produce ranked candidates and evidence gaps.

Suggested output:
- `data/dso_research/local_consolidator_cluster_candidates_20260621.json`

## QA / Gate handling

QA should not block the evidence hunt. QA reviews finished outputs when they land.

Gate Owner should not run research agents. Gate Owner continues:
- merged manifest QA handoff
- validate-only only
- no DB writes
- later merge new evidence outputs into a future manifest pass

## Success criteria

This wave is successful if it produces:
- 10+ network-level ownership summaries
- 50+ location-level evidence rows or held leads
- clear differentiation of dentist/family-owned consolidators vs DSO/MSO/PE structures
- future-app-ready notes explaining "who controls this network and how we know"

