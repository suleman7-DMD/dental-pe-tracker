# Census Protocol — how to classify one practice

The per-practice verification recipe for the hand-verified census of all ~4,439 IL GP locations. Apply in order; stop at the first tier that documentary evidence supports. **Cheapest evidence first** (most practices resolve before the web step). Every classification writes one `LEDGER.jsonl` line.

## Inputs per location
`practice_locations`: `location_id`, `primary_npi`, `org_npi`, `provider_npis`, `practice_name`, `city`, `zip`, `entity_classification`. Pull owner/control signals first from NPPES authorized-official fields on `primary_npi`/`org_npi`; use parsed `provider_npis` for research context and intel coverage, but do not let floating associates create ownership clusters. Pull existing `practice_intel` dossiers before web search: 2,069/4,439 locations have primary-NPI intel, and 2,330/4,439 have intel through the full NPI bridge. Caveat: current `scrapers/consolidate_census.py` propagates ownership fields only to `primary_npi` + `org_npi`, not `provider_npis`.

## Decision ladder

**Step A — Institutional? (T6)**
Name/affiliation = FQHC, community health center, hospital system, university clinic, county/state/VA, or a Medicaid safety-net org. → `institutional`, `evidence_basis=structural` or `web_verified`. Not consolidated, not DSO.

**Step B — Branded DSO? (T5)**
The NPPES name IS a known DSO brand (Aspen, Dental Dreams, Western Dental, Comfort Dental, Great Expressions, etc.). Confirm against the brand's own locator at exact street+ZIP. → `branded_dso`, `pe_backed` per the brand's known sponsor (`PROGRESS.json` D1 pool carries the sponsor), `evidence_basis=locator`.

**Step C — Stealth DSO? (T4)** — the hard, high-value class
Local name but PE/MSO-backed via friendly-PC. Evidence, any ONE:
- DSO locator lists this exact street+ZIP under a local name (the Heartland-"Dental Professionals of Illinois PC" pattern).
- NPI's own `da_legal_name`/`parent_company` = a DSO/MSO.
- Real shared EIN across 3+ ZIPs with ≥1 already-confirmed corporate member at that EIN.
- `practice_intel` dossier names a PE sponsor/DSO with a citation URL.
→ `stealth_dso`, `pe_backed=true`, `evidence_basis` accordingly. **Single weak signal alone never qualifies.**

**Step D — Dentist-owned multi-location? (T3)** — the mini-DSO class
Same authorized official / owner dentist appears to operate 2+ locations across ZIPs, with NO PE/MSO tie. AO/mailing and name-chain results are **candidate discovery first**, not automatic classification. Gate on **mailing-address concentration**: ≤2 mailing addrs across many ZIPs = high confidence; high addr count → web-verify the dentist actually runs them, **never auto-reject** (Sweis-12-addr rule). Name-chain (same brand across 3+ ZIPs, surname-blocklisted) corroborates. Final tier depends on evidence: dentist-owned → `dentist_multi`; PE/MSO/friendly-PC → `stealth_dso`; unclear → `undetermined`.

**Step E — Single-location group? (T2)**
Multiple unrelated dentists at one location, dentist-owned, no multi-location reach, no DSO tie. (`large_group`/`small_group` with distinct surnames and a single address.) → `single_loc_group`. Counts as Consolidated, not DSO.

**Family practice rule:** multi-provider same-family-name offices can be `true_independent` only if one family/dentist owner controls one location and the authorized official/owner does not reappear elsewhere. If the family/owner controls 2+ locations, classify as `dentist_multi`; if ownership among unrelated dentists is plausible but not proven, use `single_loc_group` or `undetermined` with notes.

**Step F — True independent? (T1)** — EARNED, the last step
Authorized official appears at exactly ONE location/ZIP; solo or single-family-surname; no brand, no EIN chain, no PE tie. Confirm the owner doesn't reappear elsewhere in the watched set. → `true_independent`. **Never reached by default** — only after A–E are ruled out with evidence.

**Step G — Undetermined**
If A–F can't be settled with evidence (conflicting signals, dead practice, unresolved owner), → `undetermined`, `status=needs_verification`, note why. Re-queue. Never guess.

## Batch order (efficiency — work the levers, not random rows)
1. **D1 brand-tagged PE pool** (Heartland/KKR 74, Great Lakes/Shore 84, etc.) → mostly T4/T5, locator-confirmable, highest yield.
2. **D2 authorized-official clusters** (303 org NPIs span 3+ ZIPs; Shafi/Labinov/Brunetti) → candidate clusters only; resolve to T3/T4/undetermined after evidence.
3. **D3 name-chains** (Procare, Dental Town, Ashton; skip Patel) → candidate clusters only; corroborate D2 and web evidence.
4. **`practice_intel` mine** — 2,069 dossiers already name owners/brands; harvest before any web call.
5. **Zero-corp dense ZIP sweep** (60614, 60622, 60068 …; 119 ZIPs / 1,457 locations) — the long tail; expect mostly T1/T2 but find the missed T3/T4.

## Discovery is codified, not session-bound
The recurring failure was discovery living only in a session's head. Current candidate inputs include `scrapers/build_census_batches.py`, `scrapers/build_ownership_census.py` (known flawed if transitive; candidate-only until de-chained), and detector outputs under `data/dso_research/`. The planned/repair target is `scrapers/discover_owner_clusters.py` (joins authorized-official + mailing + name-chain + brand-tag → ranked candidates, **de-chained**: EIN-anchored, corroboration-only weak keys, surname block-list, mailing-hub suppression ≥5, multi-PE/multi-brand invalidation, pair-level scoring). Run candidate builders → record candidate pools; the protocol verifies them into the LEDGER. Candidate files never become classifications by themselves.

## Hard don'ts
Transitive union-find welding (the PATEL-71 / KKR-50 blobs) is BANNED — pair-level scoring only. No fabrication. No silent caps (log every ZIP/pool swept and anything dropped). No re-promoting a demoted `location_id`.
