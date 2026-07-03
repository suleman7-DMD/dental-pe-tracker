# FINDINGS — birds-eye synthesis (2026-06-20, Opus 4.8)

Integration of 5 prior investigation sessions (Codex/GPT-5.5 census-builder + 3 analyst reviews + this one) into one verified picture. Everything below was re-checked read-only against `data/dental_pe_tracker.db` this session unless flagged.

## 1. Ground truth (verified this session)
- **Census universe:** 4,439 IL GP locations (official `zip_scores` IL sum). 4,440 by direct `practice_locations` count — the +1 is a CA stray (MIKE MIN W KANG DDS, 60045). 269 IL watched ZIPs.
- **Legacy detector floor:** 268/4,801 total = 5.58%; IL 249/4,439 = 5.61%. NPI corp 1,152 (IL 1,070 + MA 82). **Per the user, this is "definitively false" (too low) — the census corrects it; it is NOT the answer.**
- **Denominator is SOUND, numerator is the problem.** The 558 org-shell rows are real. Duplicate evidence is currently two-tiered and must be reconciled before any collapse: pressure-test upper bound = 87 excess rows / 79 clusters; exact denominator audit = 48 suite-variant candidates / 48 excess rows. The undercount is missed corporate, not an inflated base.
- **Free evidence on hand:** 2,069 of 4,439 IL GP locations (≈46.6%) carry a `practice_intel` dossier on the primary NPI; full NPI bridge coverage is higher at 2,330/4,439 (≈52.5%). `practice_signals` has 67 stealth_dso NPI-row pre-flags across 13 clusters, which bridge to 40 current IL GP locations / 11 clusters (triage only). 119 positive-GP zero-corp ZIPs hold 1,457 GP locations (the long tail to sweep); including empty watched ZIP rows, zero-corp is 143/269.

## 2. The reframe (why the model changed)
`entity_classification` conflates **size** (solo/small/large/family) with **ownership** (dso_*). A 4-dentist `large_group` could be a true independent partnership OR a stealth DSO — the schema can't say. The census needs a **separate ownership axis**: the new `ownership_tier` column (6 tiers + `pe_backed` flag + Undetermined). This is settled (see README). The competing "add enum values" idea is subsumed.

**Two headlines, both census-derived, NO external anchor:** Consolidated % (T2+T3+T4+T5) and DSO/PE % (T4+T5), each shown with coverage %. The old floor→ADA-14.6% band is **dead** (user ruling).

## 3. Levers, with verified magnitudes
- **Engine A (affiliated_dso propagation) — DEAD as a bulk lever.** Only 1 of 121 brand-tagged rows (Southland Smiles→Heartland 60422) is defensibly flippable today; the other ~120 carry only a noisy Pass-2 address-fuzzy tag (the 1,072-false-positive scar lives here, `dso_classifier.py:742`). The "117 clean flips / 8.24%" claim from two analyst sessions was WRONG — 117 is a verification *queue*, not a result.
- **Engine B (ownership census / owner-identity clustering) — the real work,** but the existing `scrapers/build_ownership_census.py` uses transitive union-find and PRODUCES POISONED blobs (PATEL-71, KKR+Gryphon-50). Must be rewritten de-chained (EIN-anchored, pair-level, surname-blocklist, mailing-hub ≥5 suppression, multi-PE/multi-brand invalidation) before use.
- **D1 brand-tagged PE pool (highest near-term yield):** ~330 non-corp NPIs already carry a known PE/DSO brand tag — Great Lakes/Shore 84, Heartland/KKR 74, 1st Family 43, All Family/UDP 29, Western 28, Dental 360 24, Webster 13, Dental Dreams 12, Aspen 9, Comfort 9, Choice 6. **Ortho excluded** (Orthodontic Experts 45, Smile Doctors 19 — not GP). Why these never escalated: dso_classifier Pass-3 gate requires `ownership_status IN (pe_backed,dso_affiliated) AND confidence>=80` — investigate/relax with evidence.
- **D2 authorized-official clusters:** 303 org NPIs span 3+ ZIPs. High-confidence (≤2 mailing addrs): Shafi 18npi/17zip/1addr, Labinov 12/12/2, Brunetti(Procare) 9/9/2. Web-verify (high addr count, do NOT auto-reject): Ramaha 18/8/8, Sweis 13/10/12.
- **D3 name-chains:** Procare 9, Dental Town 10, Ashton 8 (=Shafi), D2 Dental 7 (all solo, possible franchise). SKIP Patel (19, common surname).

## 4. Contradictions resolved
- `practice_to_location_xref` does **not** exist — use `practice_locations.primary_npi`/`org_npi` for the NPI↔location bridge.
- Full bridge conceptually includes `provider_npis`, and local audit found 13,765 bridge entries / 9,326 distinct NPIs for 4,439 locations with 0 missing from `practices`. Caveat: current `scrapers/consolidate_census.py` propagates ownership fields only to `primary_npi` + `org_npi`, not `provider_npis`, and is write-capable.
- The "pipeline race condition" theory was wrong — it's *freezing*: dedup/reclassify scripts are NOT in `refresh.sh`, so directly-set `practice_locations` classifications are self-durable (merge_and_score recomputes `zip_scores` FROM them weekly).
- Naperville 60540 "Ashton Dental PC" pair (1767 W Ogden vs 1212 S Naper, different phones) is NOT a duplicate — CLAUDE.md is wrong; do not collapse.
- Mailing-address concentration is a CONFIDENCE signal, not an exclude (the over-correction on Sweis is reverted).
- `flip_queue_b_union.json` actual = 1,264 candidates (21/89/1,154) with a stale 5.27% projection — the root CLAUDE.md's "315" is stale.
- Stale doc numbers everywhere: CLAUDE.md says 5.43%/261/4,811/1,119; scrapers/CLAUDE.md says 5.27%. DB truth = 5.58%/268/4,801/1,152. The census supersedes all of them.
- Stale tier numbering appears in older analyst notes: old "T3 stealth / T4 branded" maps to this RESEARCH_HOME model as `T4 stealth_dso` and `T5 branded_dso`; `T3` now means `dentist_multi`.
- Frontend truth-pass bug ledger: Market Intel consolidation-map tooltip mixes legacy `independent_count` with GP-location totals; same map fallback must not compute location shares from NPI-row `dso_affiliated_count + pe_backed_count`; Market Intel sub-metro independent% must use the same location-unit path as All-Chicagoland; Launchpad's practice_locations count must not be labeled raw NPI rows; ZIP dossier percent fields are mixed intentionally (`corporate_share_pct`/`buyable_practice_ratio` fractions, `independent_pct_of_total`/`consolidation_pct_of_total`/`pct_unknown` percent values).

## 5. Magnitude expectation (for sanity, NOT a target — no anchor)
Of 4,439: ~84% are structurally tier-assignable from existing data; ~16% (~700) need web verification; ~42% (1,846) have no current owner anchor and rest on the zero-corp sweep + discoverer. The census will land the real Consolidated % wherever the evidence lands — could be well above the old 5%, with the DSO/PE sub-share its own number. We publish what we verify, with coverage. No prediction is pre-committed.

## 6. The one thing that kept failing
Findings evaporated — summarized in chat, never written to disk, lost when the session died (5× now). This RESEARCH_HOME is the fix. The highest-value action every session is appending durable rows to `LEDGER.jsonl` + updating `PROGRESS.json`, not producing prose.
