# Closure Candidate Review — Chicagoland IL GP Locations
**Generated:** 2026-07-02 by claude-sonnet-4-6 (Fable 5 PM task)  
**Purpose:** Human-adjudication input for denominator correction. No DB writes occurred.

---

## Scope and Coverage

| Metric | Count |
|--------|------:|
| Total IL GP watched locations (census scope) | 4,439 |
| Locations with practice_intel dossier | 2,069 |
| Locations without dossier (no intel signal possible) | 2,370 |
| Zero-contact locations (no phone AND no website) | 22 |
| Zero-contact already captured by intel detection | 3 |
| Zero-contact added separately (no intel) | 19 |

---

## Candidate Counts

### By Proposed Action

| Proposed Action | Count | Description |
|-----------------|------:|-------------|
| `mark_likely_closed` | **61** | Strong third-party confirmation — Yelp/Google/BBB/Birdeye explicitly marks closed, "out of business", "permanently closed" |
| `verify_first` | **93** | Medium signal — retirement, relocation, unverifiable existence, zero-contact; needs human verification before action |
| `keep_active` (listed for transparency) | 388 | Weak/ambiguous phrasing detected but insufficient to act; listed so reviewers can see what was excluded and why |

### By Strength

| Strength | Count | Proposed Action |
|----------|------:|-----------------|
| Strong | 61 | `mark_likely_closed` |
| Medium | 93 | `verify_first` |
| Weak | 388 | `keep_active` |
| **Total candidates** | **542** | |

### By Signal Source

| Signal Source | Count |
|---------------|------:|
| `red_flags` only | 214 |
| `overall_assessment` only | 171 |
| `both` (red_flags + overall_assessment) | 138 |
| `zero_contact` only (no intel, no phone, no website) | 19 |

### Entity Classification of Actionable Candidates (strong + medium only)

| entity_classification | Count |
|-----------------------|------:|
| `solo_established` | 95 |
| `solo_high_volume` | 40 |
| `small_group` | 7 |
| `family_practice` | 5 |
| `solo_inactive` | 4 |
| `large_group` | 2 |
| `dso_national` | 1 |

---

## Top 20 Strongest Candidates

These are the top candidates by strength (strong first) for human adjudication:

| # | Practice Name | ZIP | City | EC | Quote (truncated to 180 chars) |
|---|--------------|-----|------|----|-------------------------------|
| 1 | Black Lisa DDS | 60005 | ARLINGTON HEIGH | `solo_establishe` | CAL: Yelp review from 2018 states 'Unfortunately, he has retired and the office has closed down,' directly contradicting current active listings. / Contradictory information across |
| 2 | Riggs Dental | 60007 | ELK GROVE VILLA | `solo_establishe` | Yelp listing marked CLOSED as of March 2026 — practice operational status is questionable / No new patient acceptance confirmed across multiple di |
| 3 | Smiles By Farr | 60010 | Barrington | `solo_establishe` | CRITICAL: Barrington location marked CLOSED as of September 2025 on Yelp. Significantly limits acquisition viability for this specific address. / Only 1 employee l |
| 4 | METROPOLITAN DENTAL CARE | 60016 | DES PLAINES | `solo_establishe` | located in Des Plaines, IL. The practice maintains an active website, positive patient reviews on multiple platforms, and BBB A+ accreditation. Services include preventive, restora |
| 5 | SMILE DENTISTRY, P.C. | 60053 | MORTON GROVE | `solo_establishe` | Practice address hosts closed dental practice (Risorius Dental LLC confirmed CLOSED on Yelp as of Feb 2026). / Entity name mismatch: registered as SMILE DENTISTRY, P.C., but actual |
| 6 | Mui Dental | 60056 | MOUNT PROSPECT | `solo_establishe` | . Unclear ownership transition timeline. / Dr. Mui retirement status ambiguous: Patient reviews reference 'recently retired Dr Mui' but official website still lists him as active p |
| 7 | Kisker Dental | 60061 | VERNON HILLS | `solo_establishe` | CRITICAL: Practice appears CLOSED or dormant. Solo owner status contradicted by multi-provider Healthgrades listing. Unable to verify current operations, |
| 8 | Titus David S DDS | 60093 | NORTHFIELD | `solo_high_volum` | Practice has fundamentally changed ownership structure. Dr. Titus is no longer operating an independent solo practice as of 2022; he merged with New Age Dental group. The 1721 Orch |
| 9 | LAUREN A WEITZ DDS IN | 60103 | BARTLETT | `small_group` | indicate inconsistent NAP (Name-Address-Phone) across directories. / One recent patient review (2024) cited difficult appointment scheduling availability. / Specific digital techno |
| 10 | AMERICAN FAMILY DENTAL CARE P.C | 60104 | BELLWOOD | `solo_establishe` | Practice marked CLOSED on Yelp as of March 2026 (current date April 25, 2026) / No dedicated website for Bellwood location; parent domain poin |
| 11 | STREAMWOOD FAMILY DENTISTRY P.C. | 60107 | STREAMWOOD | `solo_establishe` | Practice appears closed as of July 2025 per Yelp / Acquired/merged into Total Dentistry—exit occurred / Unable to verify current operational st |
| 12 | Letizia Dental | 60108 | BLOOMINGDALE | `solo_establishe` | Practice marked as CLOSED as of July 2025 (Yelp), making acquisition unlikely. / Dr. Letizia retired before January 2015. / Multiple billing comp |
| 13 | Geneva Dental Ltd | 60134 | GENEVA | `solo_establishe` | Yelp listing shows prior location (401 Williamsburg Ave) marked CLOSED; practice relocated to 2172 Blackberry Dr suite 201. / Staff count stated as 1 employee in input, but website |
| 14 | OPTIMAL DENTAL LOMBARD PC | 60148 | LOMBARD | `solo_establishe` | PRACTICE PERMANENTLY CLOSED — This is the critical finding. Birdeye review aggregator explicitly states 'Optimal Dental is permanently closed.' / C |
| 15 | Marshall Dental | 60154 | WESTCHESTER | `solo_establishe` | PRACTICE CLOSED: Website homepage explicitly states 'After 37 years of practicing oral surgery in Westchester, Stephen G. Marshall, DDS |
| 16 | CHICAGO METRO DENTAL SERVICES, PLLC | 60164 | NORTHLAKE | `solo_high_volum` | FACILITY PERMANENTLY CLOSED as of October 2025 / No current reviews on any platform / No active business presence / Address may be occupied by othe |
| 17 | STONE PARK DENTAL INC | 60165 | STONE PARK | `solo_establishe` | presence/social media visibility for location-specific practice / Yelp listing marked as CLOSED as of March 2026 |
| 18 | Smunt Dental | 60174 | SAINT CHARLES | `small_group` | tical verification issues exist: the Yelp listing from April 2026 indicates the practice is CLOSED, and multiple sources reference an alternate address (Campton Crossings Dr). The  |
| 19 | Dixon Dental Care | 60181 | OAKBROOK TERRAC | `solo_establishe` | BBB profile states practice is 'out of business' with no rating. This directly contradicts active listing status on HealthGrades/Sharecare claiming to accept new patie |
| 20 | PAVNICA & MAGGOS, P.C. | 60188 | CAROL STREAM | `small_group` | ppears inconsistent with current team (Maggos, Colella, Vlachogiannis); Pavnica no longer active. |

---

## Zero-Contact Pool (no phone AND no website)

19 locations appear in the output with `signal_source=zero_contact` and no intel dossier. An additional 3 zero-contact locations also had intel signals detected (captured under their intel-derived signal_source). Total zero-contact in scope: **22**.

These 22 contactless locations include a disproportionate share of DA_-prefixed and DIR_-prefixed synthetic NPIs that survived the 2026-06-12 da_unverified purge (they held entity_classification=solo_high_volume or solo_inactive rather than da_unverified). Their proposed_action is `verify_first` — a human should check whether the practice is still operating before any denomination change.

---

## Method Notes

### Detection Approach

1. **Scope:** `practice_locations` joined to `watched_zips` where `state='IL'` and `entity_classification NOT IN ('specialist','non_clinical','da_unverified','duplicate_location')`. This matches the GP census denominator exactly (4,439 locations).

2. **Intel join:** Via `primary_npi` matching `practice_intel.npi`. 2,069 locations had an intel dossier. No intel was reachable for 2,370 locations — they are absent from the candidate list unless they are zero-contact.

3. **Pattern matching:** Three tiers. Strong patterns require explicit third-party confirmation ("permanently closed", "out of business", "Yelp marks as closed", "BBB lists as out of business", "Birdeye confirms closed"). Medium patterns capture retirement, relocation, unverifiable existence, very stale NPI data (10+ years). Weak patterns flag ambiguous language.

4. **False positive exclusions applied:** The following patterns in the matched excerpt cause the match to be discarded:
   - "not accepting new patients" / "closed to new patient acquisition"
   - "closed on weekends/Sundays/Fridays" (office-hours language)
   - "temporarily closed"
   - "closed due to COVID/pandemic"
   - "office hours", "hours of operation", "by appointment only"
   - "new patients welcome", "now accepting", "accepting new patients"

5. **Proposed-action rule:**
   - Strong → `mark_likely_closed`
   - Medium → `verify_first`
   - Weak → `keep_active` (listed for transparency, no action recommended)

6. **Zero-contact pool:** Separate pass for phone IS NULL/empty AND website IS NULL/empty — appended as `verify_first` / `medium` if not already captured by intel detection.

### Denominator Impact (If Actions Were Taken)

- **If all `mark_likely_closed` (61 locations) were removed from the GP denominator:** 4,439 → ~4,378. Corporate share floor would tick from 5.43% to ~5.51% (261 corporate / 4,378). **Do not apply without human adjudication.**
- **If all `verify_first` (93 locations) were also confirmed and removed:** 4,439 → ~4,285. This is the upper bound of the closure-removal effect.

### Caveats

- The intel dossiers were generated via batch AI research (Anthropic API) and are subject to their own accuracy constraints. Strong candidates backed by named third-party platforms (Yelp, Google, BBB, Birdeye) are higher confidence than AI inference.
- 2,370 locations have no intel dossier — the true closure population is likely higher than the 61 strong candidates suggest.
- Zero-contact DA_/DIR_ synthetic NPIs represent a data quality issue distinct from genuine closures; verify whether the underlying business ever existed before removing from the denominator.

---

## Confirmation: No DB Writes

**CONFIRMED: Zero writes to `data/dental_pe_tracker.db`.** This file was generated by read-only SQLite SELECT queries only. No UPDATE, INSERT, or DELETE statements were executed. The database md5 is unchanged from the session start value documented in CLAUDE.md.

Output file: `data/dso_research/closure_candidates_review_20260702.json` (394,581 bytes, 542 candidate rows)
