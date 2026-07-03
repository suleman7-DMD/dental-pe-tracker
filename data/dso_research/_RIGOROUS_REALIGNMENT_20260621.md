# Rigorous Realignment — 2026-06-21

## Current verdict

Autonomous evidence gathering worked, but the canonical manifest is not yet clean for consolidation.

Do not run `--allow-db-write`.

## Blocking fix before any consolidation

QA found 4 ready rows that self-identify as candidate / closed / operating-status-unverified. They remain in the current ready file and must be demoted to `needs_more_evidence` before any consolidation:

- `1fa86e6647cd57c5` — Khurana / Downers Grove Ogden
- `b184f060d46970cd` — Khurana / Lemont
- `e493e4371bb5cb22` — Khurana / Downers Grove Fairview
- `d5bc28878405a18c` — Palella / Modern Dental on Sheffield

Current ready count is 210. After this fix it should be 206 unless another merge changes the count.

## New evidence not yet merged

Main AO Wave 3:
- `ao_network_evidence_reach3_ranked_20260621.json`
- 51 networks / 138 locations
- 120 `ready_for_validation`, 12 candidate, 6 undetermined
- overlaps current manifest buckets: ready 8, needs_more 23, rejected 2, conflicts 1

Fleet B new lanes:
- `ownership_evidence_queue_fleet_b_local_clusters_20260621.json` — 637 rows, 19 classified, 618 needs_verification
- `ownership_evidence_queue_fleet_b_website_clusters_20260621.json` — 79 rows, 5 classified, 74 needs_verification
- `ownership_evidence_queue_fleet_b_structural_residue_20260621.json` — 4 rows, 2 classified, 2 needs_verification
- these have overlaps with existing buckets; Gate Owner must dedupe by `location_id`.

## Lane instructions

### Gate Owner

1. Apply QA MUST-FIX first: demote the 4 listed rows from ready to needs_more_evidence.
2. Regenerate the validator-native ready file and run validate-only.
3. Then merge Wave 3 + Fleet B new lanes in a separate pass.
4. Deduplicate by `location_id` across ready / needs_more / rejected / conflicts.
5. Preserve strategic network intelligence sidecars. Do not flatten AO/person/family/operator evidence.
6. Hand merged manifest back to QA.
7. No DB writes.

### QA

Wait for Gate Owner's re-merge. Review:
- the 4-row demotion landed
- no closed/unverified rows remain in ready
- Wave 3 overlaps were deduped correctly
- Fleet B overlaps were deduped correctly
- no AO-reach-only row entered ready
- strategic network sidecars survived

### Main AO

Hold new hunting until Gate Owner consumes Wave 3. Do not run reach=2 long tail yet.

### Fleet B

Hold deterministic DB-only lanes. Session index says structural veins are mined out. Future Fleet work should be web-verification / Phase-C style, not re-mining dead DB signals.

