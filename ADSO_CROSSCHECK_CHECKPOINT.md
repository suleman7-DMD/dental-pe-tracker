# ADSO Cross-Check Checkpoint (paused 2026-04-25)

User asked: "is the 3.3% corporate share number a bandaid or did you do something real?"
Answer: **mixed — dedup is real, but a separate classifier bug is bleeding real DSOs into independent buckets.** The 3.3% headline is too low because of that leakage, not because of dedup.

## What was running when paused

Cross-checking `dso_locations` (92 ADSO-scraped DSO addresses) and `practice_locations.affiliated_dso` against `practice_locations.entity_classification` to measure how many real DSO sites are misclassified as `large_group`/`small_group`/`solo_*`.

## Root cause found (the bug)

**File:** `scrapers/reclassify_locations.py`
**Function:** `classify_one()` (line ~190-283)
**Line ~225-227:**

```python
# ---- Rule 3: dso_national ----
if _is_national_dso(name):
    return "dso_national", f"Known national DSO brand: {name}"
```

Rule 3 only checks the **practice name** against `_KNOWN_NATIONAL_DSOS`. It IGNORES the populated `affiliated_dso` field. So when:
- An NPI-1 row at "274 Newbury St" has `practice_name="JONATHAN MILLEN"` (individual provider) but `affiliated_dso="Gentle Dental"` set by classifier Pass 2 location-match
- The dedup script collapses NPI-1+...+NPI-N into one location row with `practice_name="Millen Dental"` (NPI-2 fallback) and `affiliated_dso="Gentle Dental"`
- Then `reclassify_locations.py::classify_one()` runs `_is_national_dso("Millen Dental")` — fails — falls through to provider-count rules
- 10 providers at the address → classified as `large_group` instead of `dso_national`

Worse, `affiliated_dso` isn't even SELECTed by `reclassify_all()` (line 328-335) — would need to be added to both SELECT clause and `cols` list before the rule can use it.

## Leakage measured (watched ZIPs only, post-Phase B)

130 location rows have a real-brand `affiliated_dso` (after excluding "General Dentistry"/"Oral Surgery"/etc. taxonomy leaks):
- 82 correctly classified as dso_national/dso_regional (63%)
- **48 LEAKED into independent buckets (37%)**

Top offenders:
| DSO Brand | Leaked | Total | Leakage % |
|---|---|---|---|
| Gentle Dental | 20 | 23 | **87%** |
| Choice Dental Group | 7 | 7 | **100%** |
| Heartland Dental | 2 | 2 | **100%** (one of the largest US DSOs!) |
| Aspen Dental | 5 | 18 | 28% |
| Western Dental | 4 | 12 | 33% |
| Midwest Dental | 4 | 8 | 50% |
| Familia Dental | 2 | 4 | 50% |
| 42 North Dental | 1 | 1 | 100% |
| Affordable Care | 1 | 8 | 13% |

Concrete examples (verified at NPI level — the underlying NPI-1 rows in `practices` ARE classified `dso_national`, the bug is only at location level):

```
274 Newbury St, Boston (02116) — Gentle Dental
  10 NPI-1 providers all classified `dso_national` confidence=85
  practice_locations row: large_group ❌
  reasoning: "10 providers at one location, no DSO/family signals"
```

## Fix proposal

In `scrapers/reclassify_locations.py::classify_one()`:

1. Add `affiliated_dso` to the SELECT in `reclassify_all()` (line ~328-335) and to the `cols` list (line ~338-344).
2. Add Rule 3b after Rule 3 (`_is_national_dso(name)`):

```python
# ---- Rule 3b: affiliated_dso match (set by Pass 2 location-match) ----
affiliated = (loc.get("affiliated_dso") or "").upper().strip()
if affiliated and not _is_taxonomy_leak(affiliated):
    for brand in _KNOWN_NATIONAL_DSOS:
        if brand in affiliated or affiliated in brand:
            return "dso_national", f"affiliated_dso match: {loc.get('affiliated_dso')}"
```

(Need to add a small `_is_taxonomy_leak` helper or just compare against the known taxonomy-noise set: `{"GENERAL DENTISTRY", "ORAL SURGERY", "ORTHODONTICS", "PERIODONTICS", "ENDODONTICS", "PEDIATRIC DENTISTRY", "PROSTHODONTICS", "DENTAL HYGIENE", "PEDODONTICS"}`.)

## After the fix

1. Re-run `python3 scrapers/reclassify_locations.py` (writes `practice_locations.entity_classification`).
2. Re-run `python3 scrapers/merge_and_score.py` (recomputes `zip_scores.corporate_share_pct` etc.).
3. Re-sync to Supabase via the `scrapers/upsert_practices_phaseB.py` workaround.
4. Verify: `SELECT entity_classification, COUNT(*) FROM practice_locations WHERE zip IN (SELECT zip_code FROM watched_zips) AND is_likely_residential=0 GROUP BY 1` — `dso_national` count should jump by ~30-50 in watched ZIPs alone.
5. Front-end Headline corporate % should rise from 3.3% to ~3-5% (dedup makes "real corporate ÷ true location count" still roughly the right proportion, but at least it won't be artificially low).

## What's still NOT addressed (next layer)

- `dso_locations.address` data is half-junk (6 rows have entire HTML pages scraped into `address` field — fix `adso_location_scraper.py` parser).
- Phase B's phone-only signal demotion was correct; do not undo it.
- The 3.3% corporate share is still 5-7× below ADA HPI's 25-35% national / 15-25% Chicagoland baseline. Even after fixing this leakage we'll only recover maybe 30-50 locations. The bigger gap is likely:
  - Brand-name fuzzy matching is too tight (only 13 brands hardcoded in `_KNOWN_NATIONAL_DSOS`)
  - DSO national-brand keywords missing: ADMI/Aspen, KOS Services, Sonrava, Pacific Dental Services, etc.
  - parent_company logic at line 231 is correct in principle but needs more brand variants

## Files I touched in this session (none, just queries)

No edits to fix yet. User said "pause" before I started fixing.

## Resume command

When user returns, confirm they want me to apply the fix, then:
1. Edit `scrapers/reclassify_locations.py` to add Rule 3b + add `affiliated_dso` to SELECT/cols
2. Run dry-run, show transitions
3. Apply, re-run merge_and_score, re-sync
4. Re-measure 3.3% headline
