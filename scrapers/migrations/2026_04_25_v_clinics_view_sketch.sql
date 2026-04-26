-- v_clinics — derived view that collapses NPI rows to physical-clinic rows
--
-- Status: SKETCH — DO NOT APPLY YET. Phase 1 of NPI_VS_PRACTICE_AUDIT.md.
-- See repo-root /NPI_VS_PRACTICE_AUDIT.md for full context, caveats, and rollout plan.
--
-- WHY: practices table conflates NPI-1 (individual dentist) and NPI-2 (organization).
-- 14,053 NPI rows in watched ZIPs collapse to ~7,100 distinct addresses. 5,100 NPI-1s
-- have NO NPI-2 at the same address (residential phantoms). 482 NPI-1 dentists are
-- mis-classified as dso_regional by classifier Pass 3.
--
-- BEFORE APPLYING:
-- 1. Resolve open caveat #1 (multi-tenant medical buildings — addr_norm-only key vs addr+org_name)
-- 2. Resolve open caveat #4 (solo specialists with NPI-1 only at a real clinic)
-- 3. Verify address normalization is good enough (this sketch uses LOWER+TRIM only;
--    real impl should match scrapers/data_axle_importer._normalize_address_for_grouping)
-- 4. Phase 2 plan: ship view, switch ONE frontend surface (Market Intel "Total practices"),
--    validate count drops from 7,183 → ~7,100, document publicly. Reversible in 1 commit.

CREATE OR REPLACE VIEW v_clinics AS
WITH normalized AS (
  SELECT
    npi,
    entity_type,
    practice_name,
    doing_business_as,
    address,
    LOWER(TRIM(REGEXP_REPLACE(COALESCE(address, ''), '\s+', ' ', 'g'))) AS addr_norm,
    city,
    state,
    zip,
    phone,
    taxonomy_code,
    ownership_status,
    entity_classification,
    affiliated_dso,
    affiliated_pe_sponsor,
    buyability_score,
    classification_confidence,
    parent_company,
    ein,
    latitude,
    longitude,
    year_established,
    employee_count,
    estimated_revenue,
    num_providers
  FROM practices
  WHERE address IS NOT NULL AND TRIM(address) <> ''
),
addr_has_org AS (
  SELECT DISTINCT addr_norm FROM normalized WHERE entity_type = 'organization'
)
SELECT
  -- Canonical clinic identity
  MD5(n.addr_norm) AS clinic_id,
  n.addr_norm,

  -- Prefer NPI-2 row for clinic-level fields
  COALESCE(
    (SELECT n2.npi FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization'
       ORDER BY n2.estimated_revenue DESC NULLS LAST,
                n2.year_established ASC NULLS LAST
       LIMIT 1),
    MAX(n.npi)
  ) AS primary_npi,

  COALESCE(
    (SELECT n2.practice_name FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization' LIMIT 1),
    MAX(n.practice_name)
  ) AS clinic_name,

  -- Provider count = NPI-1 count at this address (the actual dentists)
  COUNT(*) FILTER (WHERE n.entity_type = 'individual') AS provider_count,
  COUNT(*) FILTER (WHERE n.entity_type = 'organization') AS org_count,

  -- Clinic-level location
  MAX(n.address) AS address,
  MAX(n.city) AS city,
  MAX(n.state) AS state,
  MAX(n.zip) AS zip,
  MAX(n.latitude) AS latitude,
  MAX(n.longitude) AS longitude,

  -- Inherit classification: org wins if present
  COALESCE(
    (SELECT n2.entity_classification FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization' LIMIT 1),
    MAX(n.entity_classification)
  ) AS entity_classification,

  -- Ownership signals: org NPI is authoritative
  COALESCE(
    (SELECT n2.ownership_status FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization' LIMIT 1),
    MAX(n.ownership_status)
  ) AS ownership_status,

  COALESCE(
    (SELECT n2.affiliated_dso FROM normalized n2
       WHERE n2.addr_norm = n.addr_norm AND n2.entity_type = 'organization' LIMIT 1),
    MAX(n.affiliated_dso)
  ) AS affiliated_dso,

  -- Aggregated scoring
  MAX(n.buyability_score) AS buyability_score,
  AVG(n.classification_confidence) AS avg_classification_confidence,
  MAX(n.year_established) AS year_established,
  MAX(n.employee_count) AS employee_count,
  MAX(n.estimated_revenue) AS estimated_revenue
FROM normalized n
WHERE
  -- Phantom NPI-1 filter: include only if NPI-2 is org, OR an NPI-2 exists at this address
  n.entity_type = 'organization'
  OR n.addr_norm IN (SELECT addr_norm FROM addr_has_org)
GROUP BY n.addr_norm
;

-- Validation queries (run after CREATE):
--
-- 1. Maple Park Dental Care, P.C. → expect 1 row, provider_count=2
--    SELECT * FROM v_clinics WHERE clinic_name ILIKE 'Maple Park Dental%';
--
-- 2. Total clinic count in watched ZIPs → expect ~7,100
--    SELECT COUNT(*) FROM v_clinics WHERE zip IN (SELECT zip_code FROM watched_zips);
--
-- 3. Geocoded clinic count → expect ~2,500-2,800
--    SELECT COUNT(*) FROM v_clinics
--    WHERE zip IN (SELECT zip_code FROM watched_zips)
--      AND latitude IS NOT NULL AND longitude IS NOT NULL;
--
-- 4. dso_regional count after dedup → expect <1,181 (the 482 unambiguous misfires drop)
--    SELECT COUNT(*) FROM v_clinics
--    WHERE entity_classification = 'dso_regional'
--      AND zip IN (SELECT zip_code FROM watched_zips);
