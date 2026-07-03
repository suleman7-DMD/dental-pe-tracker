# Duplicate Location Candidate Review — Chicagoland IL

**Generated:** 2026-07-02  |  **By:** sonnet-5 dup-gen under Fable PM  |  **DB Writes:** NONE

---

## Summary Counts

| Metric | Value |
|--------|-------|
| Total phone+ZIP combos with >1 location_id (IL GP+Corporate watched) | **221** |
| Raw excess location rows | **246** |
| `likely_duplicate` combos | **128** |
| Rows proposed `mark_duplicate_location` (conservative — excludes ambiguous members) | **125** |
| `distinct_shared_phone` combos (shared phone, clearly different practices) | **86** |
| `needs_review` combos (ambiguous — human call required) | **7** |
| Trunk-line suspect phones (>=3 ZIPs) | **8** |
| Members already classified `duplicate_location` | **0** (excluded from scope query) |

---

## Method & Thresholds

**Scope:** `practice_locations` WHERE `state='IL'` AND `zip IN watched_zips` AND
`entity_classification NOT IN ('specialist','non_clinical','da_unverified','duplicate_location')`
AND `phone IS NOT NULL`. Group by `(phone, zip)`; find combos with >1 `location_id`.

**Address normalization:** lowercase → strip suite/unit/floor/ste/#/apt tokens →
remove punctuation → collapse whitespace. Extract house number (leading digit sequence)
and street stem (first 3 tokens after house number).

**Pairwise classification rules (applied to each member pair in a combo):**

| Rule | Condition | Notes |
|------|-----------|-------|
| `likely_dup` pair | Same house number AND SequenceMatcher ratio ≥ 0.80 | Core rule — address typo/suite variant |
| `likely_dup` pair | No house number extracted AND ratio ≥ 0.90 | Rare — unnumbered street forms |
| `distinct` pair | Explicitly different house numbers (regardless of string ratio) | Prevents '141 vs 111 W Jackson' false positives |
| `distinct` pair | No house number extracted AND ratio < 0.60 | Clearly different street |
| `ambiguous` pair | Same house but ratio in [0.60, 0.80) | Escalates combo to `needs_review` |

**Combo-level classification:**
- `likely_duplicate`: any pairwise comparison = `likely_dup` (trunk-line override: ratio must be ≥ 0.95)
- `distinct_shared_phone`: all pairs = `distinct`; or trunk-line phone with no high-match pair
- `needs_review`: mixed ambiguous pairs, no clear `likely_dup`
- `trunk_line_suspect`: phone appears in ≥ 3 distinct ZIPs across all scoped practice_locations

**proposed_keep selection:** highest `provider_count` → has website → lowest `location_id`.
For multi-member combos, members with explicitly different house numbers from the proposed_keep
get `proposed_action: 'keep_distinct_address'` — NOT marked as duplicates.

---

## 15 Example `likely_duplicate` Pairs

Addresses shown side-by-side. These are proposals — human review required before applying `mark_duplicate_location`.

### 1. Phone `(773) 588-7840` — ZIP 60640

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `ba858690c8a5` | Renieris Irene | 1945 w wilson suite | 1 |
| MARK DUP | `e32ed1606301` | THE DENTAL MASTRS OF RAVENSWOOD LLC | 1945 w wilson ste | 0 |

Max pairwise ratio: **1.0** | same_house: True

### 2. Phone `(847) 397-6060` — ZIP 60008

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `535142f00b19` | Marietta Bufalina DDS | 4005 1/2 algonquin rd | 1 |
| MARK DUP | `9f75426d8a35` | MARIETTA A BUFALINO INC | 4005 1 2 algonquin rd | 0 |

Max pairwise ratio: **1.0** | same_house: True

### 3. Phone `(847) 692-7350` — ZIP 60068

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `d3a0e2085a1e` | Barrett Dental | 35 1 2 s prospect ave | 1 |
| MARK DUP | `fe4e8aece6d7` | PARK RIDGE DENTISTRY PLLC | 35 1/2 s prospect ave | 1 |

Max pairwise ratio: **1.0** | same_house: True

### 4. Phone `(847) 864-8151` — ZIP 60201

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `b9a649e2efff` | STEPHENS DENTISTRY, INC. | 1560 sherman ave | 7 |
| MARK DUP | `2c1671236a9f` | Stephens Dental | 1560 sherman ave suite | 1 |

Max pairwise ratio: **1.0** | same_house: True

### 5. Phone `(630) 529-5559` — ZIP 60139

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `89e20a69d8cb` | Denta Care | 2184b bloomingdale rd | 1 |
| MARK DUP | `629ed0ab1ee9` | OSAMA ISMAIL D.D.S. | 2184 bloomingdale rd | 1 |

Max pairwise ratio: **0.9756** | same_house: True

### 6. Phone `(773) 486-6500` — ZIP 60639

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `27d2656a3607` | HASSAN & RIZKALLA DENTAL PLLC | 4434 w fullerton ave | 3 |
| MARK DUP | `a4f9068791f4` | DENTAL STARZ, LLC | 4434a w fullerton ave | 1 |

Max pairwise ratio: **0.9756** | same_house: True

### 7. Phone `(708) 479-9888` — ZIP 60448

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `f51841bcca18` | LEON J WITKOWSKI JR DDS LTD | 19665 s la grange rd | 3 |
| MARK DUP | `6399268006b0` | Witkowski Dental | 19665 s lagrange rd | 1 |

Max pairwise ratio: **0.9744** | same_house: True

### 8. Phone `(708) 562-4474` — ZIP 60154

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `c65aad1eabe4` | DRS SULLIVAN & SUCHY LTD | 1200 highridge pkwy | 2 |
| MARK DUP | `fd93dc3b061f` | Sullivan Dental | 1200 high ridge pkwy | 1 |

Max pairwise ratio: **0.9744** | same_house: True

### 9. Phone `(331) 234-3000` — ZIP 60005

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `1bf81b2f3eaf` | SONRISA ARLINGTON HEIGHTS | 1768 w algonquin rd | 2 |
| MARK DUP | `fff89ee2312c` | NEW FAMILY DENTAL | 1768 w algonqun rd | 0 |

Max pairwise ratio: **0.973** | same_house: True

### 10. Phone `(773) 651-8700` — ZIP 60620

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `412fc113ebdf` | Orrington Dental | 8244 so ashland ave | 1 |
| MARK DUP | `62ddee9ac0a0` | BANKS DENTAL GROUP INC | 8244 s ashland ave | 0 |

Max pairwise ratio: **0.973** | same_house: True

### 11. Phone `(630) 279-3070` — ZIP 60126

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `d4158d668f7c` | COTTAGE HILL DENTAL CARE, LTD. | 135 n addison ave | 4 |
| MARK DUP | `a32753d24d08` | JERALD SCHARFENBERG DDS PC | 135d n addison ave | 0 |

Max pairwise ratio: **0.9714** | same_house: True

### 12. Phone `(630) 898-3100` — ZIP 60504

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `3cde649d1d08` | Lodestro Dental | 4230a westbrook dr | 1 |
| MARK DUP | `e785695ebba3` | PETER A LO DESTRO DDS PC | 4230 westbrook dr | 0 |

Max pairwise ratio: **0.9714** | same_house: True

### 13. Phone `(773) 284-0037` — ZIP 60632

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `4edc896d5fbf` | May Dental | 5109 s pulaski rd | 1 |
| MARK DUP | `a9f083121a51` | ARAS DENTAL INCORPORATION | 5109b s pulaski rd | 1 |

Max pairwise ratio: **0.9714** | same_house: True

### 14. Phone `(708) 547-1100` — ZIP 60104

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `0dcc04c8a118` | Muthuramaswami Dental | 4209st charles rd | 1 |
| MARK DUP | `5ffd5386b51d` | AMERICAN FAMILY DENTAL CARE P.C | 4209stcharles rd | 0 |

Max pairwise ratio: **0.9697** | same_house: True

### 15. Phone `(847) 517-7919` — ZIP 60173

| Role | location_id | Practice Name | Address | NPIs |
|------|-------------|---------------|---------|------|
| KEEP | `534c8e9adfa8` | Valis Dental | 1320e american ln | 1 |
| MARK DUP | `f849d9ecf776` | ILLINOIS DENTAL PROVIDRS (SCHAUMBURG), P.C. | 1320 american ln | 0 |

Max pairwise ratio: **0.9697** | same_house: True

---

## 5 Trunk-Line Shared Phone Examples

These phones appear in 3+ ZIPs and connect to clearly distinct practices — DSO call centers,
answering services, or shared appointment lines. Combos with these phones are classified
`distinct_shared_phone` unless address ratio ≥ 0.95.

### `(773) 728-5333` — 4 ZIPs: 60120, 60623, 60640, 60647

### `(312) 607-8382` — 3 ZIPs: 60056, 60076, 60630

### `(630) 972-4010` — 3 ZIPs: 60435, 60440, 60540

### `(312) 274-0308` — 3 ZIPs: 60506, 60610, 60620

### `(312) 846-6752` — 9 ZIPs: 60201, 60605, 60610, 60611, 60614, 60640, 60647, 60654, 60657

| ZIP | Practice | Address |
|-----|----------|---------|
| 60657 | David Drake DDS | 963 w belmont ave |
| 60657 | Monks Allison DMD | 3423 n southport ave |

---

## `needs_review` Combos (7 total)

Address pairs with same house number but ratio < 0.80 — possible different suites,
partial address data, or adjacent buildings sharing a phone.

| Phone | ZIP | Address A | Address B | Ratio | Notes |
|-------|-----|-----------|-----------|-------|-------|
| `(312) 500-7080` | 60613 | 3901 n broadway chicago il 60613 | 3901 n broadway | 0.6383 |  |
| `(630) 333-9571` | 60563 | 760 n route 59 | 760 n illinois rte 59 | 0.6857 |  |
| `(630) 372-9800` | 60103 | 849 s route 59 | 849 s sutton rd | 0.6207 |  |
| `(630) 552-9200` | 60545 | 901 w route 34 | 901 w us hwy 34 | 0.6897 |  |
| `(773) 247-0404` | 60608 | 3443 s ashland ave | 3443 s halsted st | 0.6286 |  |
| `(773) 384-4333` | 60647 | 3230 w n ave | 3230 w n ave chicago | 0.75 |  |
| `(847) 697-9900` | 60123 | 2375 bowes rd | 2375 bowes dental care | 0.6857 |  |

---

## Statement of No DB Writes

This file and `duplicate_candidates_review_20260702.json` were generated by **read-only**
SQLite queries on `data/dental_pe_tracker.db`. No `UPDATE`, `INSERT`, or `DELETE`
statements were executed. The `duplicate_location` entity_classification was **not**
applied to any row. All `proposed_actions` in the JSON are proposals for a human reviewer
to evaluate before running the existing `scrapers/cleanup_duplicate_location_rows.py` script.

**Sanity check:** 0 members in scope had `entity_classification = 'duplicate_location'`
(that class was excluded from the query, confirming no already-handled rows are re-proposed).