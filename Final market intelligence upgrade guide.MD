# DENTAL MARKET INTELLIGENCE UPGRADE GUIDE — FINAL BUILD SPECIFICATION

## FOR CLAUDE CODE: READ THIS ENTIRE DOCUMENT BEFORE WRITING ANY CODE

This is a build specification for upgrading the Dental PE Consolidation Intelligence Platform. It was developed through three rounds of adversarial expert review and represents final consensus on what to build, why, in what order, and how to verify each step.

**Do not skim this. Do not skip sections. Do not start coding until you have read every word.**

### How to Execute This Guide

**Phase 0: Reconnaissance**
Before writing a single line of code, you must:
1. Read this entire guide end-to-end
2. Read `README.md` and `CLAUDE.md` in the project root
3. Read `scrapers/database.py` to understand the current schema
4. Read `scrapers/merge_and_score.py` to understand existing dedup and scoring logic
5. Read `scrapers/dso_classifier.py` to understand existing classification logic
6. Read `scrapers/nppes_downloader.py` to understand how NPPES data is imported
7. Read `scrapers/data_axle_importer.py` — at minimum the class structure, field mappings, and Passes 5-6
8. Read `dashboard/app.py` — focus on the Job Market page and Market Intel page sections
9. Produce a written reconnaissance report summarizing: current schema, current scoring logic, current classification logic, current dashboard data flow. This report must be complete before any implementation begins.

**Phased Implementation**
This guide is organized into 5 implementation phases. Each phase has:
- A clear scope boundary
- Specific deliverables
- Verification checkpoints that MUST pass before proceeding to the next phase
- A completion report template

**Do not proceed to Phase N+1 until Phase N's verification checkpoints all pass.**

**Quality Standards**
- Every database migration must be backwards-compatible (existing data must not be lost or corrupted)
- Every new computation must be verified against at least 3 known ZIP codes with manually calculated expected values
- Every dashboard change must be tested with both enriched (Data Axle) and non-enriched (NPPES-only) data
- All existing tests and pipeline functionality must continue to work after each phase
- Show your work: log what you changed, why, and what the before/after looks like

---

## PHASE 1: DATA FOUNDATION

**Scope:** Schema changes + demographic data + provider last name column + data freshness tracking

**Why this is first:** Every metric in this guide depends on population data and reliable provider name data. Without Phase 1, nothing else works.

### 1.1 Add Demographic Columns to `watched_zips`

**File:** `scrapers/database.py`

Add these columns to the WatchedZip model:

```python
population = Column(Integer, nullable=True)                # ZIP-level total population (ACS 5-year estimates)
median_household_income = Column(Integer, nullable=True)   # ZIP-level MHI in dollars
population_growth_pct = Column(Float, nullable=True)       # 5-year population change percentage
```

**Migration approach:** Use ALTER TABLE to add columns. Do NOT drop and recreate the table. Existing data in watched_zips (290 rows with zip_code, city, state, metro_area) must be preserved exactly.

**Verification:** After migration, run `SELECT COUNT(*) FROM watched_zips` — must still return 290. Run `SELECT * FROM watched_zips LIMIT 5` — existing columns must have their original values, new columns should be NULL.

### 1.2 Create Census Data Loader

**New file:** `scrapers/census_loader.py`

This script populates the demographic columns. It should:

1. **Primary method:** Try to fetch from the Census Bureau API
   - Endpoint: `https://api.census.gov/data/2023/acs/acs5`
   - Variables: `B01003_001E` (total population), `B19013_001E` (median household income)
   - Geography: `for=zip%20code%20tabulation%20area:*&in=state:17,25` (IL and MA)
   - Note: ZCTAs approximate but do not perfectly align with USPS ZIP codes. Document this in comments.

2. **Fallback method:** If the API is unavailable or rate-limited, read from a local CSV
   - File: `data/zip_demographics.csv`
   - Format: `zip_code,population,median_household_income,population_growth_pct`
   - The script should create a template CSV with all 290 watched ZIPs if the file doesn't exist, so the user can fill it manually.

3. **Update logic:** For each watched ZIP, update population and median_household_income. Do NOT overwrite existing values with NULL if the API doesn't return data for a specific ZIP — only update when you have real values.

4. **Logging:** Use `pipeline_logger.log_scrape_start()` and `log_scrape_complete()` per existing pipeline conventions. Log how many ZIPs were updated, how many had no data available.

5. **Data freshness:** Store a record in a metadata field or log entry indicating when demographics were last updated.

**Verification checkpoint:**
```sql
-- After running census_loader.py, verify:
SELECT COUNT(*) FROM watched_zips WHERE population IS NOT NULL;
-- Should be > 250 (most ZIPs should have data)

SELECT zip_code, city, population, median_household_income 
FROM watched_zips 
WHERE zip_code IN ('60491', '60439', '60441', '60523')
ORDER BY zip_code;
-- Verify against known values:
-- 60491 Homer Glen: pop ~24,500, MHI ~$132k
-- 60439 Lemont: pop ~24,255, MHI ~$132k  
-- 60441 Lockport: pop ~37,093, MHI ~$104k
-- 60523 Oak Brook: pop ~8,100, MHI varies (commercial area)
```

### 1.3 Add `provider_last_name` Column to `practices`

**File:** `scrapers/database.py`

Add to the Practice model:

```python
provider_last_name = Column(String, nullable=True)  # Populated from NPPES "Provider Last Name" column for individuals
```

**Why this column exists:** Dynasty detection (identifying family-owned practices where 2+ providers at the same address share a last name) requires reliable last name data. The NPPES download already reads separate first/last name columns but discards them after constructing `practice_name = f"{first} {last}"`. This column preserves the last name from source data with zero parsing heuristics.

**File:** `scrapers/nppes_downloader.py`

Modify the import logic to populate `provider_last_name` during every NPPES import:
- For entity_type '1' (individual providers): set `provider_last_name` to the value from the NPPES "Provider Last Name (Legal Name)" column
- For entity_type '2' (organizations): leave NULL (organizations don't have personal last names)

**Backfill strategy for existing records:**

Create a one-time backfill script (`scrapers/backfill_last_names.py`) that:
1. Checks for the most recent NPPES snapshot file in `data/` (filename pattern: `nppes_dental_*.csv`)
2. If found: reads NPI + Provider Last Name columns, updates practices table where entity_type = '1'
3. If no snapshot available: parses `practice_name` for entity_type = '1' records using last-token heuristic (take the last whitespace-delimited word, strip common suffixes like DDS, DMD, PC, PLLC, LTD, INC, PA, LLC). Document that this is approximate (~90% accurate) and will be replaced by clean data on the next monthly NPPES refresh.
4. Logs: how many records updated, how many used clean source data vs heuristic parsing

**Verification checkpoint:**
```sql
-- After backfill:
SELECT COUNT(*) FROM practices WHERE provider_last_name IS NOT NULL;
-- Should be approximately the count of entity_type='1' practices (~290k)

SELECT practice_name, provider_last_name FROM practices 
WHERE entity_type = '1' AND provider_last_name IS NOT NULL
LIMIT 20;
-- Verify last names look correct (not first names, not suffixes)

-- Specifically check the known case from the conversation:
-- "Groselak" family in Lemont — should see multiple NPIs with provider_last_name = 'GROSELAK'
SELECT practice_name, provider_last_name, address, zip 
FROM practices 
WHERE zip = '60439' AND provider_last_name LIKE '%GROSELAK%';
```

### 1.4 Add `entity_classification` Column to `practices`

**File:** `scrapers/database.py`

Add to the Practice model:

```python
entity_classification = Column(String, nullable=True)
# Allowed values (use these exact strings):
# 'solo_established'    — Single-provider practice, operating 20+ years, has active presence
# 'solo_new'            — Single-provider practice, established within last 10 years
# 'solo_inactive'       — Single-provider practice, missing phone/web, likely retired or minimal activity
# 'solo_high_volume'    — Single-provider with high employee count (5-9) or high revenue (>$800k) — needs associate help
# 'family_practice'     — 2+ providers at same address share a last name (internal succession likely)
# 'small_group'         — 2-3 providers at same address, different last names, not matching known DSO
# 'large_group'         — 4+ providers at same address, not matching known DSO brand
# 'dso_regional'        — Appears independent but shows corporate signals (generic name + high count, or parent_company, or shared EIN across 3+, or franchise field)
# 'dso_national'        — Known national/regional DSO brand (Aspen, Heartland, etc.)
# 'specialist'          — Specialist practice (Ortho, Endo, Perio, OMS, Pedo)
# 'non_clinical'        — Dental lab, supply company, billing entity
```

**Note on naming:** These are professional, descriptive labels — not marketing jargon. Each label clearly states what the entity IS.

### 1.5 Add Data Freshness Tracking

**File:** `scrapers/database.py`

Add to a metadata table or to the existing pipeline logging:

```python
# Option A: Add to watched_zips
demographics_updated_at = Column(DateTime, nullable=True)  # When population/MHI was last loaded

# Option B: Store in a general metadata table (if one exists)
# Key: 'demographics_last_updated', Value: ISO timestamp
```

**Dashboard display:** On the System Health page AND on any page that shows demographic data, display the timestamp of the last demographics import. Format: "Demographics last updated: March 14, 2026"

If demographics are older than 365 days, show a warning: "⚠️ Demographic data is over 1 year old. Consider refreshing via `python3 scrapers/census_loader.py`"

### 1.6 Add New Metrics Columns to `zip_scores`

**File:** `scrapers/database.py`

Add to the ZipScore model:

```python
# Saturation metrics (computed by merge_and_score.py)
total_gp_locations = Column(Integer, nullable=True)       # De-duped GP office count (excludes specialists)
total_specialist_locations = Column(Integer, nullable=True) # De-duped specialist office count
dld_gp_per_10k = Column(Float, nullable=True)             # GP offices per 10k residents
dld_total_per_10k = Column(Float, nullable=True)          # All dental offices per 10k residents
people_per_gp_door = Column(Integer, nullable=True)       # Population / GP offices

# Ownership structure metrics
buyable_practice_count = Column(Integer, nullable=True)    # solo_established + solo_inactive + solo_high_volume (GP only)
buyable_practice_ratio = Column(Float, nullable=True)      # buyable_practice_count / total_gp_locations
corporate_location_count = Column(Integer, nullable=True)  # dso_regional + dso_national (GP only)
corporate_share_pct = Column(Float, nullable=True)         # corporate_location_count / total_gp_locations
family_practice_count = Column(Integer, nullable=True)     # family_practice classified locations
specialist_density_flag = Column(Boolean, nullable=True)   # True if specialist_locations > 3 (demand signal)

# Data quality
entity_classification_coverage_pct = Column(Float, nullable=True)  # % of practices with non-null entity_classification
data_axle_enrichment_pct = Column(Float, nullable=True)            # % of practices with Data Axle data
metrics_confidence = Column(String, nullable=True)                  # 'high', 'medium', 'low' based on data completeness

# Market classification
market_type = Column(String, nullable=True)       # Computed classification (see Phase 3)
market_type_confidence = Column(String, nullable=True)  # 'confirmed', 'provisional', 'insufficient_data'
```

**CRITICAL: Specialist Identification Methodology**

Every practice classified as `specialist` must be traceable. The classification logic MUST be auditable. Here is the definitive methodology for separating GP from specialist practices:

```python
# SPECIALIST DETECTION — AUDITABLE METHODOLOGY
# 
# A practice is classified as 'specialist' if ANY of the following conditions are met.
# Store WHICH condition triggered the classification in classification_reasoning.
#
# Condition 1: Taxonomy code match
# NPPES taxonomy codes for dental specialists:
SPECIALIST_TAXONOMY_CODES = {
    '1223D0001X': 'Dental Public Health',
    '1223E0200X': 'Endodontics',
    '1223G0001X': 'Oral and Maxillofacial Pathology',
    '1223P0106X': 'Oral and Maxillofacial Surgery',
    '1223P0221X': 'Pediatric Dentistry',
    '1223P0300X': 'Periodontics',
    '1223P0700X': 'Prosthodontics',
    '1223S0112X': 'Oral and Maxillofacial Surgery',
    '1223X0008X': 'Oral and Maxillofacial Radiology',
    '1223X0400X': 'Orthodontics and Dentofacial Orthopedics',
    '122300000X': 'Dentist (general - NOT specialist, do not match this)',
    '1223G0001X': 'General Practice (NOT specialist)',
}
# Only match the specific specialist codes, NOT the general dentist codes.
#
# Condition 2: Practice name keyword match (case-insensitive)
SPECIALIST_NAME_KEYWORDS = [
    'ORTHODONT',           # Orthodontics
    'PERIODON',            # Periodontics
    'ENDODONT',            # Endodontics
    'ORAL SURG',           # Oral Surgery
    'ORAL & MAXILLOFACIAL', # Oral & Maxillofacial Surgery
    'MAXILLOFACIAL',       # OMFS
    'PEDIATRIC DENT',      # Pediatric Dentistry
    'PEDODONT',            # Pediatric (older term)
    'PROSTHODONT',         # Prosthodontics
    'IMPLANT CENT',        # Implant-only centers
    'ORTHODONTIC',         # Orthodontics variant
]
# IMPORTANT: 'DENTAL IMPLANT' alone is NOT a specialist signal — many GPs do implants.
# Only 'IMPLANT CENTER' or similar dedicated-facility names qualify.
#
# Condition 3: taxonomy_code starts with a known specialist prefix
# This catches variants not in the explicit list above.
SPECIALIST_TAXONOMY_PREFIXES = ['1223D', '1223E', '1223P', '1223S', '1223X']
# Exclude '1223G' (General Practice) and '122300' (General Dentist)
#
# AUDIT TRAIL: When classifying a practice as specialist, store in classification_reasoning:
# "Specialist: [condition_number] — [specific match]. Taxonomy: [code]. Name: [name]."
# Example: "Specialist: Condition 1 — taxonomy 1223X0400X (Orthodontics). Name: BOOTH ORTHODONTICS"
# Example: "Specialist: Condition 2 — name contains 'ORAL SURG'. Name: SUBURBAN ORAL SURGERY"
```

**Verification checkpoint for Phase 1:**
```sql
-- Schema verification: all new columns exist
PRAGMA table_info(watched_zips);
-- Should show population, median_household_income, population_growth_pct, demographics_updated_at

PRAGMA table_info(practices);
-- Should show provider_last_name, entity_classification

PRAGMA table_info(zip_scores);
-- Should show all new metric columns

-- Data integrity: no existing data lost
SELECT COUNT(*) FROM watched_zips;  -- Still 290
SELECT COUNT(*) FROM practices;     -- Still ~400k
SELECT COUNT(*) FROM zip_scores;    -- Still ~290
SELECT COUNT(*) FROM deals;         -- Still ~2,500

-- Demographics populated
SELECT COUNT(*) FROM watched_zips WHERE population IS NOT NULL;  -- > 250

-- Last names populated  
SELECT COUNT(*) FROM practices WHERE provider_last_name IS NOT NULL;  -- > 200,000
```

**Phase 1 completion report must include:**
- Exact row counts before and after migration for all modified tables
- Number of ZIPs with demographic data populated
- Number of practices with provider_last_name populated
- Sample verification of 5 known ZIPs (60491, 60439, 60441, 60440, 60517) showing their demographic values
- Sample verification of 10 known providers showing their provider_last_name values
- Confirmation that `python3 pipeline_check.py` still passes
- Confirmation that `bash scrapers/refresh.sh` still runs without errors (or at minimum that individual scrapers still import correctly)

---

## PHASE 2: CLASSIFICATION ENGINE

**Scope:** Entity classification for all practices + address normalization assessment + specialty separation audit trail

**Depends on:** Phase 1 complete (provider_last_name populated, entity_classification column exists)

### 2.1 Assess Address Normalization Quality

Before computing any metrics, measure the impact of the current address normalization in `merge_and_score.py`.

**Create a diagnostic script** (`scrapers/assess_address_normalization.py`) that:

1. For 5 test ZIPs (60491, 60439, 60441, 60440, 60517), computes unique location count using:
   - **Method A (current):** `address.upper().strip()` + `city.upper().strip()` — this is what `deduplicate_practices_in_zip()` currently does
   - **Method B (enhanced):** Full normalization — expand abbreviations (ST→STREET, DR→DRIVE, RD→ROAD, AVE→AVENUE, BLVD→BOULEVARD, LN→LANE, CT→COURT, STE→SUITE, #→SUITE), strip suite/unit numbers, collapse multiple spaces, strip trailing punctuation

2. For each ZIP, output:
   ```
   ZIP 60491: Method A = 42 locations, Method B = 38 locations, diff = 4 (9.5%)
   ZIP 60439: Method A = 31 locations, Method B = 28 locations, diff = 3 (9.7%)
   ```

3. If the average difference exceeds 5%, port Method B normalization into `merge_and_score.py`'s `deduplicate_practices_in_zip()`. If < 5%, document the finding and proceed with existing normalization.

4. **IMPORTANT:** If you upgrade the normalization, the enhanced normalization function must be a standalone utility function (e.g., `normalize_address()` in `database.py` or a new `utils.py`) that can be used by both `merge_and_score.py` and the dashboard. Do not duplicate normalization logic.

**Verification:** Output the diagnostic report as a file (`data/address_normalization_assessment.txt`). Include the raw numbers, the decision made, and the rationale.

### 2.2 Implement Entity Classification

**File:** `scrapers/dso_classifier.py` (extend, do not replace existing logic)

Add a new function that runs AFTER the existing DSO classification:

```python
def classify_entity_types(session, zip_codes=None):
    """
    Second-pass classification that assigns entity_classification to practices.
    
    Runs AFTER the existing DSO classifier (which sets ownership_status).
    Does NOT modify ownership_status — entity_classification is an additional layer.
    
    Args:
        session: SQLAlchemy session
        zip_codes: Optional list of ZIPs to classify. If None, classifies all watched ZIPs.
    """
```

**Classification logic (execute in this exact order — first matching rule wins):**

```python
def _classify_single_location(practice, providers_at_address, last_names_at_address, 
                                all_practices_at_address):
    """
    Classify one practice location. Returns (classification, reasoning_text).
    
    The reasoning_text MUST explain WHY this classification was assigned,
    referencing specific data fields. This is the audit trail.
    
    Args:
        practice: Practice ORM object
        providers_at_address: int — count of distinct NPIs at same normalized address
        last_names_at_address: list of str — provider_last_name values for all 
                               individual-entity NPIs at this address (excluding NULLs)
        all_practices_at_address: list of Practice objects at this address
    """
    
    reasons = []
    
    # Rule 1: Non-clinical entity detection
    # Dental labs, supply companies, billing entities, resume services
    NON_CLINICAL_KEYWORDS = [
        'LABORATORY', 'DENTAL LAB', ' LAB ', 'SUPPLY', 'PATTERSON', 'SCHEIN',
        'RESUME', 'STAFFING', 'BILLING SERVICE', 'MANAGEMENT GROUP',
        'CONSULTING', 'INSURANCE', 'DENTAL PLAN'
    ]
    name_upper = (practice.practice_name or '').upper()
    for kw in NON_CLINICAL_KEYWORDS:
        if kw in name_upper:
            return ('non_clinical', f"Non-clinical: practice name contains '{kw}'. Full name: {practice.practice_name}")
    
    # Rule 2: Specialist detection (uses the auditable methodology from Phase 1)
    # Check taxonomy code first (most reliable)
    if practice.taxonomy_code:
        for prefix in SPECIALIST_TAXONOMY_PREFIXES:
            if practice.taxonomy_code.startswith(prefix):
                specialty_name = SPECIALIST_TAXONOMY_CODES.get(practice.taxonomy_code, 'Unknown Specialty')
                return ('specialist', 
                        f"Specialist: taxonomy code {practice.taxonomy_code} ({specialty_name}). "
                        f"Name: {practice.practice_name}")
    # Check practice name keywords
    for kw in SPECIALIST_NAME_KEYWORDS:
        if kw in name_upper:
            return ('specialist',
                    f"Specialist: practice name contains '{kw}'. "
                    f"Full name: {practice.practice_name}. Taxonomy: {practice.taxonomy_code or 'N/A'}")
    
    # Rule 3: Known DSO (national brand)
    if practice.ownership_status in ('dso_affiliated', 'pe_backed'):
        # Check if it matches a known national brand
        if practice.affiliated_dso and practice.classification_confidence and practice.classification_confidence >= 90:
            return ('dso_national',
                    f"National DSO: matched known brand '{practice.affiliated_dso}' "
                    f"with confidence {practice.classification_confidence}%.")
        else:
            return ('dso_regional',
                    f"Regional/stealth DSO: ownership_status={practice.ownership_status}, "
                    f"affiliated_dso={practice.affiliated_dso}, "
                    f"confidence={practice.classification_confidence}%.")
    
    # Rule 4: Corporate signals on ostensibly independent practices
    corporate_signals = []
    if practice.parent_company:
        corporate_signals.append(f"parent_company='{practice.parent_company}'")
    if practice.franchise_name:
        corporate_signals.append(f"franchise='{practice.franchise_name}'")
    if practice.location_type and practice.location_type.lower() in ('branch', 'subsidiary'):
        corporate_signals.append(f"location_type='{practice.location_type}'")
    # EIN shared with 3+ practices (check via query or pre-computed flag)
    # This check should use the existing stealth_dso detection results if available
    
    if len(corporate_signals) >= 2:
        return ('dso_regional',
                f"Likely corporate-affiliated: {'; '.join(corporate_signals)}. "
                f"Practice name: {practice.practice_name}")
    
    # Rule 5: Family practice detection (same last name at same address)
    if providers_at_address >= 2 and last_names_at_address:
        from collections import Counter
        name_counts = Counter(ln.upper().strip() for ln in last_names_at_address if ln)
        repeated_names = {name: count for name, count in name_counts.items() 
                         if count >= 2 and name not in ('', 'DDS', 'DMD', 'PC', 'LTD', 'INC', 'LLC')}
        if repeated_names:
            names_str = ', '.join(f"'{n}' ({c}x)" for n, c in repeated_names.items())
            return ('family_practice',
                    f"Family practice: {providers_at_address} providers at address, "
                    f"shared last names: {names_str}. "
                    f"Address: {practice.address}")
    
    # Rule 6: Large group (4+ providers, different names, not flagged as DSO)
    if providers_at_address >= 4:
        # Check for generic branding that suggests corporate even without DSO match
        GENERIC_BRAND_KEYWORDS = [
            'SMILE', 'SMILES', 'DENTAL CARE', 'FAMILY DENT', 'ADVANCED DENT',
            'PREMIER', 'GRAND DENTAL', 'VALLEY', 'PROFESSIONAL DENT',
            'COMPLETE DENT', 'PERFECT', 'IDEAL', 'MODERN DENT'
        ]
        is_generic = any(kw in name_upper for kw in GENERIC_BRAND_KEYWORDS)
        if is_generic and providers_at_address >= 5:
            return ('dso_regional',
                    f"Likely corporate: generic brand name + {providers_at_address} providers. "
                    f"Name: {practice.practice_name}")
        return ('large_group',
                f"Large group practice: {providers_at_address} providers at address with "
                f"different last names. Name: {practice.practice_name}")
    
    # Rule 7: Small group (2-3 providers, different names)
    if providers_at_address in (2, 3):
        return ('small_group',
                f"Small group/partnership: {providers_at_address} providers at address. "
                f"Name: {practice.practice_name}")
    
    # Rule 8: Single provider classifications
    if providers_at_address <= 1:
        # Solo — high volume indicators
        has_high_volume = (
            (practice.employee_count and practice.employee_count >= 5) or
            (practice.estimated_revenue and practice.estimated_revenue >= 800000)
        )
        if has_high_volume:
            vol_details = []
            if practice.employee_count: vol_details.append(f"employees={practice.employee_count}")
            if practice.estimated_revenue: vol_details.append(f"revenue=${practice.estimated_revenue:,.0f}")
            return ('solo_high_volume',
                    f"High-volume solo: single provider with {', '.join(vol_details)}. "
                    f"May need associate help. Name: {practice.practice_name}")
        
        # Solo — inactive/minimal signals
        has_no_contact = (
            (not practice.phone or practice.phone in ('Not Available', '')) and
            (not practice.website or practice.website == '')
        )
        if has_no_contact:
            return ('solo_inactive',
                    f"Inactive/minimal presence: no phone and no website on file. "
                    f"Entity type: {practice.entity_type}. Name: {practice.practice_name}")
        
        # Solo — established (20+ years)
        import datetime
        current_year = datetime.datetime.now().year
        if practice.year_established and (current_year - practice.year_established) >= 20:
            age = current_year - practice.year_established
            return ('solo_established',
                    f"Established solo: {age} years in practice (est. {practice.year_established}). "
                    f"Single provider. Name: {practice.practice_name}")
        
        # Solo — newer
        if practice.year_established and (current_year - practice.year_established) < 10:
            return ('solo_new',
                    f"Newer solo: established {practice.year_established} "
                    f"({current_year - practice.year_established} years). "
                    f"Name: {practice.practice_name}")
        
        # Default solo — not enough data to distinguish further
        return ('solo_established',
                f"Solo practice (default classification): single provider, "
                f"limited enrichment data available. Name: {practice.practice_name}")
    
    return (None, "Could not classify — unexpected provider count or data state")
```

**The classification reasoning stored in `classification_reasoning` MUST be specific and auditable.** It must reference the actual data values that triggered the classification. Not "probably a family practice" but "Family practice: 3 providers at address, shared last names: 'GROSELAK' (2x). Address: 15531 E 127TH ST."

### 2.3 Run Classification and Verify

After implementing the classifier, run it on all watched ZIPs:

```bash
cd ~/dental-pe-tracker && python3 scrapers/dso_classifier.py
```

**Verification checkpoint — classification distribution:**
```sql
SELECT entity_classification, COUNT(*) as cnt,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM practices WHERE zip IN (SELECT zip_code FROM watched_zips)), 1) as pct
FROM practices 
WHERE zip IN (SELECT zip_code FROM watched_zips)
GROUP BY entity_classification
ORDER BY cnt DESC;
```

Expected rough distribution (these are guidelines, not exact targets):
- `solo_established` should be the largest category (50-70% of classified)
- `specialist` should be 10-20%
- `small_group` should be 5-15%
- `family_practice` should be 2-8%
- `dso_national` + `dso_regional` should roughly match the existing dso_affiliated + pe_backed counts
- `non_clinical` should be < 1%
- NULL (unclassified) should be < 5%

**If any category is wildly off** (e.g., 0 family practices, or 50% specialist), investigate the classification logic before proceeding.

**Specific verification cases from the conversation's manual analysis:**

```sql
-- Homer Glen family practices: Groselak, Booth should be flagged
SELECT practice_name, provider_last_name, entity_classification, classification_reasoning
FROM practices WHERE zip = '60491' AND entity_classification = 'family_practice';

-- Lockport DSOs: Aspen Dental, Heartland should be dso_national  
SELECT practice_name, entity_classification, classification_reasoning
FROM practices WHERE zip = '60441' AND entity_classification IN ('dso_national', 'dso_regional');

-- Specialists should be properly separated
SELECT practice_name, taxonomy_code, entity_classification, classification_reasoning
FROM practices WHERE zip = '60491' AND entity_classification = 'specialist';
-- Should include the oral surgeon and orthodontist from Homer Glen
```

**Phase 2 completion report must include:**
- Address normalization assessment results (Method A vs Method B for 5 ZIPs)
- Whether normalization was upgraded and why/why not
- Full classification distribution table
- Specific verification of Homer Glen, Lemont, Lockport, Woodridge family practices and DSOs
- Specialist count per ZIP for 5 test ZIPs, with the specific taxonomy codes or name keywords that triggered each classification
- Count of practices where entity_classification is still NULL and why

---

## PHASE 3: SCORING ENGINE

**Scope:** Compute all new ZIP-level metrics, market type classification

**Depends on:** Phase 1 + Phase 2 complete

### 3.1 Extend `merge_and_score.py` with New Metric Computations

**File:** `scrapers/merge_and_score.py`

Add a new function (or extend the existing `score_watched_zips()`):

```python
def compute_saturation_metrics(session, zip_code):
    """
    Computes all new ZIP-level metrics and updates zip_scores.
    
    REQUIRES: 
    - population data in watched_zips (from Phase 1)
    - entity_classification populated (from Phase 2)
    
    Metrics computed:
    1. total_gp_locations — unique physical addresses with at least one GP practice
    2. total_specialist_locations — unique physical addresses with only specialist practices
    3. dld_gp_per_10k — GP locations per 10,000 residents
    4. dld_total_per_10k — all dental locations per 10,000 residents
    5. people_per_gp_door — population / GP locations
    6. buyable_practice_count — locations classified as solo_established, solo_inactive, or solo_high_volume (GP only)
    7. buyable_practice_ratio — buyable_practice_count / total_gp_locations
    8. corporate_location_count — locations classified as dso_regional or dso_national (GP only)
    9. corporate_share_pct — corporate / total GP locations
    10. family_practice_count — locations classified as family_practice
    11. specialist_density_flag — True if total_specialist_locations > 3
    12. entity_classification_coverage_pct — % of practices with non-null classification
    13. data_axle_enrichment_pct — % of practices with data_axle_import_date not null
    14. metrics_confidence — 'high' / 'medium' / 'low'
    """
```

**GP vs Specialist separation at the location level:**

A "location" (unique normalized address) is classified as GP if it contains at least one practice where `entity_classification NOT IN ('specialist', 'non_clinical')`. A location is specialist-only if ALL practices at that address are specialists. This means a building with both a GP and an orthodontist counts as a GP location (the orthodontist is a referral source, not competition displacement).

**Store which method was used:** In the zip_scores row, include a comment or log entry noting: "GP/specialist separation: [N] practices at [M] unique addresses. [X] addresses classified as GP, [Y] as specialist-only. Method: entity_classification field match."

**Metrics confidence calculation:**

```python
def compute_metrics_confidence(entity_classification_coverage_pct, data_axle_enrichment_pct, unknown_ownership_pct):
    """
    Returns 'high', 'medium', or 'low'.
    
    high: entity_classification coverage > 80% AND unknown ownership < 20%
    medium: entity_classification coverage > 50% AND unknown ownership < 40%
    low: anything else
    
    Note: data_axle_enrichment_pct affects the DEPTH of analysis possible
    but not the basic reliability of classification.
    """
```

### 3.2 Implement Market Type Classification

```python
def classify_market_type(dld_gp, bhr, mhi, corporate_share, family_count, total_gp, population, 
                         metrics_confidence, population_growth_pct=None):
    """
    Assigns a market type label based on computed metrics.
    
    Returns (market_type, market_type_confidence, explanation).
    
    market_type_confidence:
    - 'confirmed': metrics_confidence is 'high', all required inputs available
    - 'provisional': metrics_confidence is 'medium', label assigned but may change with more data
    - 'insufficient_data': metrics_confidence is 'low', label NOT assigned (returns market_type=None)
    
    IMPORTANT: If metrics_confidence is 'low', set market_type to NULL. 
    Do NOT assign a label when data quality is poor. The data is still STORED 
    in zip_scores for all the individual metrics — nothing is lost. 
    The market_type label is simply not computed because it would be unreliable.
    All underlying metrics (DLD, BHR, etc.) are always stored regardless of confidence.
    """
```

**Market type rules (evaluated in priority order — first match wins):**

| Priority | Type | Conditions | Explanation Template |
|----------|------|-----------|---------------------|
| 1 | `low_resident_commercial` | DLD-GP > 15.0 AND population < 15,000 | "Very high dental density ({dld}) relative to small residential population ({pop}). Likely a commercial/office hub where demand is driven by non-residents." |
| 2 | `high_saturation_corporate` | DLD-GP > 8.0 AND BHR < 25% AND corporate_share > 30% | "High dental density ({dld}) dominated by corporate chains ({corp_pct}% corporate). Competitive for patients, limited ownership access." |
| 3 | `corporate_dominant` | corporate_share > 50% AND BHR < 20% | "Over half of GP locations are corporate-affiliated. Market structure favors employment over ownership." |
| 4 | `family_concentrated` | BHR appears > 40% BUT family_count > 30% of buyable locations | "Many independent practices are family-operated with apparent internal succession. Nominal ownership availability ({bhr}%) overstates real opportunity." |
| 5 | `low_density_high_income` | DLD-GP < 5.0 AND BHR > 40% AND MHI > $120k AND population > 15,000 | "Below-average dental supply ({dld}/10k) in a high-income area (${mhi:,}). High share of independent practices ({bhr}% buyable)." |
| 6 | `low_density_independent` | DLD-GP 5.0-7.0 AND BHR > 50% AND corporate_share < 10% AND population < 30,000 | "Moderate density, predominantly independent practices, low corporate presence. Patient retention likely high." |
| 7 | `growing_undersupplied` | DLD-GP < 5.0 AND population_growth_pct > 10% | "Below-average dental supply in a growing population area. Supply may lag demand." |
| 8 | `balanced_mixed` | DLD-GP 4.0-8.0 AND BHR 25-50% AND corporate_share 15-35% | "Balanced mix of independent and corporate practices at moderate density." |
| 9 | `mixed` | Default | "Market does not fit a clear pattern. Review individual metrics." |

### 3.3 Data Quality Warnings

Add these warning computations to the scoring pipeline. Store them as flags or notes, and surface them in the dashboard.

**Warning 1: Capacity-substitution signal**
```python
# When a ZIP has few GP doors but high average employee count per door,
# the people-per-door ratio overstates the opportunity.
if people_per_gp_door > 2500:
    avg_emp = practices_in_zip.employee_count.dropna().mean()
    if avg_emp and avg_emp > 12:
        # Store warning
        warning = (f"Capacity substitution detected: {total_gp_locations} GP offices "
                   f"but average {avg_emp:.0f} employees per office. "
                   f"Few offices with large capacity — actual supply may be higher than door count suggests.")
```

**Warning 2: High income attracting high supply**
```python
if mhi and mhi > 120000 and dld_gp > 8.0:
    warning = (f"High-income area (${mhi:,} MHI) with high dental density ({dld_gp:.1f}/10k). "
               f"Wealthy areas attract more providers, increasing competition despite affluence.")
```

### 3.4 Run Scoring and Verify

```bash
cd ~/dental-pe-tracker && python3 scrapers/merge_and_score.py
```

**Verification checkpoint — compare against conversation's manual analysis:**

```sql
SELECT wz.zip_code, wz.city, wz.population, wz.median_household_income,
       zs.total_gp_locations, zs.dld_gp_per_10k, zs.buyable_practice_ratio,
       zs.corporate_share_pct, zs.market_type, zs.metrics_confidence
FROM zip_scores zs
JOIN watched_zips wz ON zs.zip_code = wz.zip_code
WHERE wz.zip_code IN ('60491', '60439', '60441', '60440', '60517', '60462', '60523', '60423')
ORDER BY zs.dld_gp_per_10k;
```

**Expected ranges (from conversation's manual analysis — verify each):**

| ZIP | Town | Expected DLD-GP Range | Expected BHR Range | Expected Market Type |
|-----|------|-----------------------|--------------------|---------------------|
| 60491 | Homer Glen | 1.5 - 4.0 | > 35% | low_density_high_income |
| 60439 | Lemont | 5.0 - 8.0 | > 40% | low_density_independent or balanced_mixed |
| 60441 | Lockport | 5.0 - 9.0 | < 20% | corporate_dominant or high_saturation_corporate |
| 60440 | Bolingbrook | 5.0 - 8.0 | mixed | balanced_mixed |
| 60517 | Woodridge | 5.0 - 8.0 | mixed | balanced_mixed |
| 60462 | Orland Park | > 8.0 | low | high_saturation_corporate |
| 60523 | Oak Brook | > 12.0 | low | low_resident_commercial |
| 60423 | Frankfort | > 8.0 | moderate | high_saturation_corporate or balanced_mixed |

**If computed values diverge significantly from these ranges, investigate in this order:**
1. Is the address deduplication working correctly? (Check unique location count)
2. Is the specialist separation correct? (Are GPs being miscounted as specialists or vice versa?)
3. Is the population data correct for this ZIP?
4. Is the entity_classification distribution reasonable for this ZIP?

**Phase 3 completion report must include:**
- Full metric values for all 8 test ZIPs in a table
- Comparison of computed values vs expected ranges, with explanations for any divergences
- Distribution of market types across all 290 ZIPs
- Distribution of metrics_confidence levels
- Count of ZIPs where market_type is NULL (insufficient data)
- Any data quality warnings generated and for which ZIPs

---

## PHASE 4: DASHBOARD ENHANCEMENTS

**Scope:** Surface all new metrics in the dashboard

**Depends on:** Phases 1-3 complete

### 4.1 Market Intel Page — Saturation Analysis Section

Add a new section after the existing consolidation map/ownership breakdown:

```python
st.subheader("Saturation Analysis")
```

**Cross-ZIP comparison table:**
Display for all watched ZIPs in the selected metro area:

| ZIP | Town | Pop | MHI | GP Offices | DLD-GP/10k | Buyable % | Corporate % | Type | Confidence |
|-----|------|-----|-----|------------|------------|-----------|-------------|------|------------|

- Sortable by any column
- Color-code DLD-GP: green (< 5.0), yellow (5.0-7.0), red (> 7.0)
- Color-code Buyable %: green (> 50%), yellow (20-50%), red (< 20%)
- Color-code Corporate %: green (< 15%), yellow (15-35%), red (> 35%)
- Show confidence as stars: ★★★ / ★★ / ★
- CSV download button
- Show "Demographics last updated: [date]" below the table

**Data completeness indicator:** If > 30% of ZIPs have metrics_confidence = 'low', show an info box:
> "Many ZIPs have limited data quality. Metrics marked ★ should be treated as directional only. Run Data Axle imports for enriched ZIPs to improve accuracy."

### 4.2 Job Market Page — Dual-Lens Tabs

Add two tabs within the practice directory section:

**Tab 1: "Employment Opportunities"**
- Filter: `employee_count >= 10` OR `entity_classification IN ('large_group', 'dso_national', 'dso_regional')`
- Sort by: employee_count DESC
- Columns: Practice Name, Address, ZIP, City, Employee Count, Entity Type, Affiliated DSO, Job Opportunity Score
- Header text: "Practices with high patient volume that are likely hiring associates."

**Tab 2: "Ownership Pipeline"**
- Filter: `entity_classification IN ('solo_established', 'solo_high_volume', 'solo_inactive')` AND `ownership_status IN ('independent', 'likely_independent')`
- Sort by: buyability_score DESC
- Columns: Practice Name, Address, ZIP, City, Year Established, Buyability Score, Confidence, Entity Classification
- Header text: "Independent practices with indicators suggesting the owner may be approaching transition."

**IMPORTANT:** Both tabs must include a note about data completeness for the selected zone. If < 20% of practices have Data Axle enrichment, show: "Limited business data available for this area. Employee counts and revenue figures may be incomplete."

### 4.3 Job Market Page — New KPI Cards

Add 3 new KPI cards alongside the existing 6:

```python
# Pull from zip_scores for the selected zone
zone_zs = zip_scores_df[zip_scores_df.zip_code.isin(zone_zips)]

# KPI 7: Average DLD-GP
avg_dld = zone_zs['dld_gp_per_10k'].mean()
st.metric("Avg Dental Density", f"{avg_dld:.1f}/10k",
          help="GP dental offices per 10,000 residents. National avg ~6.1. Lower = less competition.")

# KPI 8: Average Buyable Practice Ratio
avg_bhr = zone_zs['buyable_practice_ratio'].dropna().mean()
confidence = "★★★" if zone_zs.data_axle_enrichment_pct.mean() > 50 else "★★" if zone_zs.data_axle_enrichment_pct.mean() > 20 else "★"
st.metric("Buyable Practice %", f"{avg_bhr:.0%} {confidence}",
          help="Percentage of GP offices that are independently owned solos — potential acquisition or mentorship targets.")

# KPI 9: High-volume solos (mentorship targets)
if 'entity_classification' in prac_df.columns:
    high_vol_count = len(prac_df[prac_df.entity_classification == 'solo_high_volume'])
    st.metric("High-Volume Solos", high_vol_count,
              help="Solo practices showing high volume signals (5+ employees or $800k+ revenue). Likely need associate help.")
```

### 4.4 Practice-Level Detail View

When a user clicks on or expands a specific practice in the directory, show an enhanced detail panel:

```python
def render_practice_detail(practice):
    """
    Shows all available intelligence for a single practice.
    
    Always shows (from NPPES):
    - Practice name, address, phone
    - Entity type (individual vs organization)
    - Ownership status
    - Entity classification with reasoning
    
    Shows when available (from Data Axle):
    - Year established, employee count, estimated revenue
    - Parent company, franchise, EIN
    - Buyability score with confidence
    - Latitude/longitude
    
    Shows when available (from cross-referencing):
    - Other providers at same address
    - Whether any providers share a last name (family indicator)
    - Whether this practice name/EIN appears in other ZIPs
    """
```

**The classification reasoning display:** Show the full `classification_reasoning` text. If it's NULL (NPPES-only practice), generate a basic observation on-the-fly:

```python
def generate_basic_observations(practice):
    """
    For practices without stored classification_reasoning,
    generate observations from available fields.
    
    Uses enumeration_date from NPPES as a weak age proxy 
    (NPI registration started ~2005; enumeration_date > 2015 
    suggests a newer provider).
    """
    observations = []
    
    if practice.entity_type == '1':
        observations.append("Individual provider registration — likely a solo practitioner or associate")
    elif practice.entity_type == '2':
        observations.append("Organization registration — incorporated practice entity")
    
    if practice.year_established:
        age = datetime.now().year - practice.year_established
        if age >= 30:
            observations.append(f"Established {age} years ago ({practice.year_established}) — owner likely in late career")
        elif age >= 20:
            observations.append(f"Established {age} years ago ({practice.year_established}) — mature practice")
        elif age <= 5:
            observations.append(f"Established only {age} years ago ({practice.year_established}) — relatively new")
    
    if practice.employee_count:
        if practice.employee_count >= 10:
            observations.append(f"{practice.employee_count} employees — large enough to likely hire associates")
        elif practice.employee_count >= 5:
            observations.append(f"{practice.employee_count} employees — moderate-sized practice")
        else:
            observations.append(f"{practice.employee_count} employees — small practice")
    
    if practice.estimated_revenue:
        if practice.estimated_revenue >= 1000000:
            observations.append(f"Estimated revenue ${practice.estimated_revenue:,.0f} — high-volume production")
        elif practice.estimated_revenue >= 500000:
            observations.append(f"Estimated revenue ${practice.estimated_revenue:,.0f} — solid production")
    
    # Note data completeness
    if not practice.data_axle_import_date:
        observations.append("Limited business data — NPPES registration data only. "
                          "Employee count, revenue, and year established not available.")
    
    return observations
```

### 4.5 Data Freshness Display

On the System Health page AND on any page showing demographic or enrichment data:

```python
# Show demographics freshness
demo_date = get_demographics_last_updated()  # From metadata
if demo_date:
    days_old = (datetime.now() - demo_date).days
    if days_old > 365:
        st.warning(f"⚠️ Demographic data last updated {demo_date.strftime('%B %d, %Y')} ({days_old} days ago). Consider refreshing.")
    else:
        st.caption(f"Demographics last updated: {demo_date.strftime('%B %d, %Y')}")

# Show NPPES freshness
nppes_date = get_last_nppes_import_date()
st.caption(f"NPPES provider data last imported: {nppes_date.strftime('%B %d, %Y') if nppes_date else 'Unknown'}")

# Show Data Axle freshness  
axle_date = get_last_data_axle_import_date()
st.caption(f"Data Axle business data last imported: {axle_date.strftime('%B %d, %Y') if axle_date else 'Never'}")
```

### 4.6 Fix Job Market Page Consistency

The Job Market page currently recomputes practice counts on-the-fly from raw practices rows. Fix this to use `zip_scores.total_practices` (already deduplicated) for KPI calculations.

**Specific fix location:** Around line ~1696 in `dashboard/app.py` (the exact line may vary — search for `prac_df.groupby("zip").agg(total_practices=("npi", "count"))` or similar patterns).

Replace raw NPI counting with the deduplicated counts from zip_scores wherever ZIP-level practice counts are displayed.

**Verification:** Compare the KPI numbers before and after this fix for "All Chicagoland" view. The total should decrease (because deduplication removes multi-NPI entries at the same address). The consolidation percentages should remain similar.

**Phase 4 completion report must include:**
- Screenshots or descriptions of all new dashboard sections
- Verification that dual-lens tabs correctly filter practices
- Verification that KPI numbers use deduplicated counts
- Verification that data freshness timestamps display correctly
- Test with at least one enriched ZIP (e.g., 60491) and one non-enriched ZIP to confirm both display modes work
- Confirmation that all existing dashboard functionality still works (no regressions)

---

## PHASE 5: INTEGRATION TESTING AND POLISH

**Scope:** End-to-end verification, buyability score adjustments, SQL templates, documentation

### 5.1 Buyability Score Adjustments

**File:** `scrapers/data_axle_importer.py` (or wherever buyability scoring is computed)

Add these modifiers to the existing scoring logic:

```python
# Family practice penalty
# If entity_classification == 'family_practice', reduce buyability score
# Rationale: family succession makes outside acquisition difficult
if entity_classification == 'family_practice':
    score -= 20
    reasoning_parts.append("Family practice detected (-20): shared last name at address suggests internal succession")

# Multi-ZIP presence penalty
# If this practice's name or EIN appears in 3+ ZIPs, it's likely a chain
if multi_zip_count >= 3:
    score -= 15
    reasoning_parts.append(f"Multi-location entity (-15): appears in {multi_zip_count} ZIP codes")
```

### 5.2 SQL Query Templates

Add these to the Research page's SQL Explorer as pre-built templates:

**Template: "Saturation Comparison"**
```sql
SELECT wz.zip_code, wz.city, wz.population, wz.median_household_income,
       zs.total_gp_locations, zs.total_specialist_locations,
       zs.dld_gp_per_10k, zs.people_per_gp_door,
       zs.buyable_practice_ratio, zs.corporate_share_pct,
       zs.market_type, zs.metrics_confidence,
       zs.data_axle_enrichment_pct
FROM zip_scores zs
JOIN watched_zips wz ON zs.zip_code = wz.zip_code
WHERE wz.metro_area LIKE '%Chicagoland%'
ORDER BY zs.dld_gp_per_10k ASC;
```

**Template: "Family Practices in Watched ZIPs"**
```sql
SELECT p.zip, p.address, p.practice_name, p.provider_last_name,
       p.entity_classification, p.classification_reasoning,
       p.year_established, p.employee_count
FROM practices p
WHERE p.zip IN (SELECT zip_code FROM watched_zips)
  AND p.entity_classification = 'family_practice'
ORDER BY p.zip, p.address;
```

**Template: "High-Volume Solo Practices (Mentorship Targets)"**
```sql
SELECT p.practice_name, p.address, p.city, p.zip,
       p.year_established, p.employee_count, p.estimated_revenue,
       p.buyability_score, p.ownership_status, p.entity_classification
FROM practices p
WHERE p.zip IN (SELECT zip_code FROM watched_zips)
  AND p.entity_classification = 'solo_high_volume'
  AND p.ownership_status IN ('independent', 'likely_independent')
ORDER BY p.estimated_revenue DESC NULLS LAST;
```

**Template: "Data Enrichment Coverage by ZIP"**
```sql
SELECT wz.zip_code, wz.city, wz.metro_area,
       COUNT(*) as total_practices,
       SUM(CASE WHEN p.data_axle_import_date IS NOT NULL THEN 1 ELSE 0 END) as enriched,
       ROUND(100.0 * SUM(CASE WHEN p.data_axle_import_date IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as enrichment_pct
FROM watched_zips wz
LEFT JOIN practices p ON p.zip = wz.zip_code
GROUP BY wz.zip_code
ORDER BY enrichment_pct DESC;
```

### 5.3 Update CLAUDE.md

Add a section documenting the new metrics and classification system:

```markdown
### Entity Classification System
The entity_classification field provides granular practice-type labels beyond ownership_status.
Classifications are assigned by the DSO classifier's second pass, using provider count at address,
last name matching, taxonomy codes, and Data Axle enrichment data.

Values: solo_established, solo_new, solo_inactive, solo_high_volume, family_practice,
small_group, large_group, dso_regional, dso_national, specialist, non_clinical

Each classification stores its reasoning in classification_reasoning for auditability.

### Saturation Metrics (in zip_scores)
- dld_gp_per_10k: GP dental offices per 10,000 residents (national avg ~6.1)
- buyable_practice_ratio: % of GP offices that are independently-owned solos
- corporate_share_pct: % of GP offices that are DSO-affiliated
- market_type: Computed classification based on combined metrics (NULL when data insufficient)

GP/specialist separation uses taxonomy codes and practice name keywords.
A location with at least one GP counts as a GP location.
```

### 5.4 End-to-End Pipeline Test

Run the full pipeline and verify nothing breaks:

```bash
cd ~/dental-pe-tracker
python3 pipeline_check.py
python3 scrapers/dso_classifier.py
python3 scrapers/merge_and_score.py
python3 pipeline_check.py --fix  # Verify no issues
```

Then start the dashboard and verify:
```bash
bash start_dashboard.sh
```

Navigate to each page. Verify:
- Market Intel: saturation table appears, sorted correctly, color-coded
- Job Market: dual tabs work, KPIs show new metrics, data freshness displayed
- Buyability: scores reflect family practice and multi-ZIP penalties
- Research: new SQL templates available and execute correctly
- System: data freshness timestamps visible

### 5.5 Final Verification Report

Generate a comprehensive completion report covering:

1. **Schema changes:** List every column added, to which table, with data type
2. **Data population:** Row counts for demographics, last names, entity classifications, new zip_score metrics
3. **Metric verification:** Table of all 8 test ZIPs with computed DLD, BHR, corporate share, market type — compared against expected ranges
4. **Classification audit:** For 3 ZIPs (60491, 60439, 60441), full entity_classification distribution with sample classification_reasoning strings
5. **Specialist separation audit:** For 3 ZIPs, list every practice classified as specialist with the specific condition that triggered it
6. **Dashboard verification:** Confirmation that all new UI elements render correctly
7. **Regression check:** Confirmation that all existing functionality still works
8. **Data freshness:** Current timestamps for demographics, NPPES, and Data Axle imports
9. **Known limitations:** List any ZIPs with insufficient data, any known classification edge cases, any metrics that should be treated as provisional

---

## THINGS TO NOT DO

1. **Do NOT delete or modify existing data.** All changes are additive. Never DROP a column. Never DELETE rows from practices. Never overwrite ownership_status with entity_classification.

2. **Do NOT change existing buyability scoring weights.** Only ADD the new modifiers (family practice penalty, multi-ZIP penalty).

3. **Do NOT remove any existing dashboard sections.** All new sections are additions.

4. **Do NOT hardcode location-specific logic.** The thresholds and rules must work for ANY metro area, not just Chicagoland. The user plans to expand.

5. **Do NOT introduce date-based upserts in zip_scores.** This was a resolved bug. Always filter by zip_code only. Read the "Known Issues" section of README.md.

6. **Do NOT use classified_count as a denominator for any KPI.** Use total practices. This is an existing rule in CLAUDE.md.

7. **Do NOT suppress metrics when data quality is low.** Store all computed values always. Only suppress the market_type LABEL (not the underlying metrics) when confidence is insufficient. The user's explicit requirement: "I prioritize having full data regardless. I don't want data lost."

8. **Do NOT present computed classifications as certainty.** Always show the reasoning that led to the classification. Always show the confidence level. The classification_reasoning field exists specifically so users can audit and override if needed.

9. **Do NOT skip verification checkpoints.** Each phase has specific SQL queries and expected values. Run them. If they don't match expectations, investigate and fix before proceeding.

10. **Do NOT proceed to Phase N+1 until Phase N is complete and verified.** No partial implementations. No "I'll come back to this later." Each phase must be fully done.
