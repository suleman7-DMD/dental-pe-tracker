"""
reclassify_locations.py — Location-aware entity classification for `practice_locations`.

Replaces the inherited NPI-row classifications (which used the buggy
"high provider count = dso_regional" heuristic) with rules driven by
LOCATION-LEVEL signals. Reads from `practice_locations` (output of
`dedup_practice_locations.py`) and updates `entity_classification` +
`classification_reasoning` in-place.

Spec: /tmp/dedup_design.md §"Entity classification recomputation rules (location-level)"

Rules in priority order (first match wins):
  1. non_clinical    — labs, supply, billing, staffing, schools, universities
  2. specialist      — is_specialist_only=TRUE
  3. dso_national    — known national DSO brand match
  4. dso_regional    — STRONG corporate signals only:
                          parent_company (real, not university), OR
                          ein shared with 2+ different ZIPs (chain), OR
                          franchise_name matches a real brand (not taxonomy noise), OR
                          location_type='branch' + parent_company present
  5. org_only_npi    — has_org_npi AND provider_count==0 (billing/admin-only,
                          closed practice; NOT solo_inactive — split 2026-04-26)
  6. family_practice — provider_count>=2 AND >=2 NPI-1s share a last name
  7. large_group     — provider_count>=4
  8. small_group     — provider_count in (2,3)
  9. solo_high_volume— provider_count==1 AND (employee_count>=5 OR revenue>=800k)
 10. solo_inactive   — provider_count<=1 AND no phone AND no website
 11. solo_new        — provider_count==1 AND year_established>=2016
 12. solo_established— default for provider_count==1 (or fallback)

Usage:
    python3 scrapers/reclassify_locations.py
    python3 scrapers/reclassify_locations.py --dry-run
    python3 scrapers/reclassify_locations.py --sample 50    # spot-check 50 random rows
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from sqlalchemy import text
from scrapers.database import get_session
from scrapers.logger_config import get_logger
from scrapers.dso_brands import match_dso_brand, KNOWN_DSOS

log = get_logger("reclassify_locations")


# ---------------------------------------------------------------------------
# Name-pattern detection (mirrors dedup_practice_locations.py)
# ---------------------------------------------------------------------------

# Raw lowercase brand patterns from the shared registry — used by the
# franchise-noise filter. Brand *name* matching itself goes through
# match_dso_brand() so the NPI and location classifiers stay in lock-step.
_KNOWN_DSO_PATTERNS = [pattern for pattern, _canonical, _pe in KNOWN_DSOS]

# Affiliated_dso strings that are pure NPPES taxonomy noise — NOT real DSOs
_AFFILIATED_DSO_TAXONOMY_LEAKS = {
    "GENERAL DENTISTRY", "ORAL SURGERY", "ORTHODONTICS",
    "PERIODONTICS", "ENDODONTICS", "PEDIATRIC DENTISTRY",
    "PROSTHODONTICS", "DENTAL HYGIENE", "PEDODONTICS",
    "ORAL AND MAXILLOFACIAL SURGERY", "DENTIST",
}

# Hard-classify as non_clinical (always)
_NON_CLINICAL_HARD = [
    " LAB ", "LABORATORY", "DENTAL LAB",
    "SUPPLY", "BILLING SERVICE", "STAFFING",
    "SCHOOL OF DENT", "COLLEGE OF DENT",
    "DENTAL SCHOOL", "DENTAL COLLEGE",
    "GOLDMAN SCHOOL", "DENTAL MEDICINE",
    "TRUSTEES OF",
]

# Soft non-clinical — only if no dental practice keywords also present
_NON_CLINICAL_SOFT = [
    "MANAGEMENT GROUP", "MANAGEMENT COMPANY",
    "MANAGEMENT SERVICES", "INSURANCE",
    "DENTURE CLINIC",  # often a denturist not dentist, but case-by-case
]

# Indicates a real practice — used to override non-clinical false positives
_PRACTICE_SAFE_KEYWORDS = ["DENTAL", "DENTISTRY", "ORTHODONT", "IMPLANT", "DDS", "DMD", "DENTAL CARE"]

# Parent-company patterns that indicate ACADEMIC, not corporate-DSO
_UNIVERSITY_PARENTS = [
    "UNIVERSITY", "BOARD-TRUSTEES", "COLLEGE", "BOARD OF TRUSTEES",
]


def _is_non_clinical_name(name: str) -> bool:
    if not name:
        return False
    n = name.upper()
    # Hard hits — schools, labs, supply, billing
    for kw in _NON_CLINICAL_HARD:
        if kw in n:
            return True
    # Soft hits — only if no dental practice context
    has_dental = any(k in n for k in _PRACTICE_SAFE_KEYWORDS)
    if not has_dental:
        for kw in _NON_CLINICAL_SOFT:
            if kw in n:
                return True
    return False


def _match_national_dso(name: str):
    """Return (canonical_brand, pe_sponsor) if the practice name contains a known
    DSO brand, else None. Backed by the shared scrapers/dso_brands registry."""
    if not name:
        return None
    return match_dso_brand(name)


def _is_national_dso(name: str) -> bool:
    return _match_national_dso(name) is not None


def _is_university_parent(parent: str) -> bool:
    """Return True if parent_company is an academic institution, not a DSO."""
    if not parent:
        return False
    p = parent.upper()
    return any(kw in p for kw in _UNIVERSITY_PARENTS)


def _norm_entity_name(s: str) -> str:
    """Strip punctuation + common legal/location suffixes for self-reference test."""
    if not s:
        return ""
    s = "".join(ch if ch.isalnum() or ch == " " else " " for ch in s.upper())
    # Drop trailing legal-entity tokens that don't change identity
    drop = {"LLC", "PC", "PLLC", "LTD", "INC", "LLP", "LP", "PA", "CO",
            "CORP", "DDS", "DMD", "ASSOCIATES", "AND", "THE", "OF"}
    toks = [t for t in s.split() if t not in drop]
    return " ".join(toks).strip()


def _is_self_referential_parent(parent: str, name: str) -> bool:
    """True if parent_company is essentially the practice's OWN name — i.e. the
    practice listed itself as its parent. This is a FALSE corporate signal
    (e.g. 'Advanced Family Dental & Orthodontics' with parent 'Advanced Family
    Dental'), NOT evidence of DSO ownership. Known DSO brands are matched before
    this runs, so a true brand parent never reaches here."""
    p, n = _norm_entity_name(parent), _norm_entity_name(name)
    if not p or not n:
        return False
    if p in n or n in p:
        return True
    # Heavy token overlap (parent is a short prefix of the practice's own name)
    ptoks, ntoks = set(p.split()), set(n.split())
    if len(ptoks) >= 2 and ptoks.issubset(ntoks):
        return True
    return False


# ---------------------------------------------------------------------------
# Seeded DSO office-address matching (ground-truth registry)
# ---------------------------------------------------------------------------

_ADDR_ABBREV = {
    " STREET": " ST", " AVENUE": " AVE", " BOULEVARD": " BLVD", " DRIVE": " DR",
    " ROAD": " RD", " LANE": " LN", " COURT": " CT", " PLACE": " PL",
    " HIGHWAY": " HWY", " PARKWAY": " PKWY", " SUITE": " STE", " NORTH ": " N ",
    " SOUTH ": " S ", " EAST ": " E ", " WEST ": " W ",
}


def _norm_addr(addr: str) -> str:
    """Light address normalization for fuzzy comparison (street number + name)."""
    if not addr:
        return ""
    a = " " + addr.upper().strip() + " "
    for long, short in _ADDR_ABBREV.items():
        a = a.replace(long, short)
    # keep only the leading 'number + street' segment (drop suite/unit tails)
    a = a.split(" STE ")[0].split(" #")[0].split(" UNIT ")[0]
    return " ".join(a.split())


def _build_dso_location_index(session):
    """ZIP -> list of (dso_name, normalized_address) from seeded dso_locations."""
    index = defaultdict(list)
    try:
        rows = session.execute(text(
            "SELECT dso_name, zip, address FROM dso_locations "
            "WHERE address IS NOT NULL AND address <> '' AND zip IS NOT NULL"
        )).fetchall()
    except Exception as e:  # table may not exist on a fresh DB
        log.warning("dso_locations unavailable for seeded-address match: %s", e)
        return index
    for dso_name, zc, addr in rows:
        index[zc.strip()].append((dso_name, _norm_addr(addr)))
    return index


def _match_seeded_dso_location(zip_code, normalized_address, dso_loc_index):
    """Return (dso_name, score) if the location's address fuzzy-matches a seeded
    DSO office in the same ZIP (token_sort_ratio >= 88), else None."""
    if not zip_code or not normalized_address or not dso_loc_index:
        return None
    candidates = dso_loc_index.get(zip_code.strip())
    if not candidates:
        return None
    from rapidfuzz import fuzz
    target = _norm_addr(normalized_address)
    if not target:
        return None
    best = None
    for dso_name, seed_addr in candidates:
        if not seed_addr:
            continue
        score = fuzz.token_sort_ratio(target, seed_addr)
        if score >= 88 and (best is None or score > best[1]):
            best = (dso_name, score)
    return best


def _is_real_franchise(franchise: str) -> bool:
    """franchise_name field is polluted with taxonomy strings.

    Only treat as a real franchise signal if it matches a known brand.
    'General Dentistry', 'Endodontics', etc. are NOT franchises.
    """
    if not franchise:
        return False
    f = franchise.upper().strip()
    # Reject generic taxonomy values
    _TAXONOMY_NOISE = {
        "GENERAL DENTISTRY", "ORTHODONTICS", "ORAL SURGERY",
        "ENDODONTICS", "PEDODONTICS", "PERIODONTICS", "PROSTHODONTICS",
    }
    if f in _TAXONOMY_NOISE:
        return False
    # Match against known DSO brands (shared registry)
    return match_dso_brand(f) is not None


# ---------------------------------------------------------------------------
# Specialist taxonomy detection (from taxonomy_codes JSON)
# ---------------------------------------------------------------------------

_GP_TAXONOMY_PREFIXES = {"122300000X", "1223G0001X"}
_SPECIALIST_TAXONOMY_PREFIXES = ("1223D", "1223E", "1223P", "1223S", "1223X")
_SPECIALIST_NAME_KEYWORDS = [
    "ORTHODONT", "PERIODON", "ENDODONT", "ORAL SURG", "MAXILLOFACIAL",
    "PEDIATRIC DENT", "PEDODONT", "PROSTHODONT", "IMPLANT CENT",
]


def _is_specialist_name(name: str) -> bool:
    if not name:
        return False
    n = name.upper()
    return any(kw in n for kw in _SPECIALIST_NAME_KEYWORDS)


# ---------------------------------------------------------------------------
# Family practice detection (last-name match)
# ---------------------------------------------------------------------------

def _has_shared_last_name(last_names: list) -> bool:
    """Return True if any last name appears 2+ times in the list."""
    if not last_names:
        return False
    cleaned = [ln.strip().upper() for ln in last_names if ln and ln.strip()]
    if len(cleaned) < 2:
        return False
    counts = Counter(cleaned)
    return any(c >= 2 for c in counts.values())


# ---------------------------------------------------------------------------
# Main reclassification driver
# ---------------------------------------------------------------------------

def classify_one(loc, ein_zip_count, last_names_by_npi, primary_npi_extras,
                 dso_loc_index=None):
    """Classify a single location row. Returns (entity_classification, reasoning)."""
    name = loc["practice_name"] or ""
    parent = (loc["parent_company"] or "").strip()
    ein = (loc["ein"] or "").strip()
    provider_count = loc["provider_count"] or 0
    has_org_npi = bool(loc["has_org_npi"])
    is_specialist_only = bool(loc["is_specialist_only"])
    employee_count = loc["employee_count"]
    estimated_revenue = loc["estimated_revenue"]
    year_established = loc["year_established"]
    phone = (loc["phone"] or "").strip()
    website = (loc["website"] or "").strip()
    provider_npis_json = loc["provider_npis"] or "[]"

    # Look up additional fields from the primary NPI in practices table
    extras = primary_npi_extras.get(loc["primary_npi"], {})
    franchise = (extras.get("franchise_name") or "").strip()
    iusa = (extras.get("iusa_number") or "").strip()
    location_type = (extras.get("location_type") or "").strip()
    num_providers = extras.get("num_providers")  # org-reported headcount fallback

    # Effective provider count: NPPES NPI-1 dedup is fragile (individuals filed
    # at slightly different addresses don't group), leaving real multi-dentist
    # practices at provider_count==0. Fall back to the org NPI's reported
    # num_providers so these aren't dumped into the org_only_npi junk bucket.
    eff_pc = provider_count if provider_count else (num_providers or 0)

    # Get provider last names for family-practice detection
    try:
        provider_npis = json.loads(provider_npis_json)
    except Exception:
        provider_npis = []
    last_names = [last_names_by_npi.get(npi, "") for npi in provider_npis]
    last_names = [ln for ln in last_names if ln]

    # ---- Rule 1: non_clinical ----
    if _is_non_clinical_name(name):
        return "non_clinical", f"Non-clinical entity (school/lab/supply/billing): {name}"

    # ---- Rule 2: specialist ----
    if is_specialist_only:
        return "specialist", "All providers at address have specialist taxonomy"

    # Specialty by name (only if no GP taxonomy mixed in — already covered by is_specialist_only,
    # but guard solo NPI-1s with specialist names that lack taxonomy)
    if _is_specialist_name(name) and provider_count <= 1 and not has_org_npi:
        return "specialist", f"Specialty practice by name: {name}"

    # ---- Rule 3: dso_national (known brand in the practice name) ----
    brand = _match_national_dso(name) or _match_national_dso(loc.get("doing_business_as") or "")
    if brand:
        canonical, pe = brand
        tag = f"{canonical}" + (f" — PE: {pe}" if pe else "")
        return "dso_national", f"Known DSO brand in name: {tag}"

    # ---- Rule 3a: seeded DSO office address (ground-truth location registry) ----
    # Catches DSO-acquired practices that kept their local name and so never
    # name-match. Matches the location's normalized address against curated
    # dso_locations rows seeded for the same ZIP.
    if dso_loc_index:
        seeded = _match_seeded_dso_location(
            loc.get("zip"), loc.get("normalized_address"), dso_loc_index
        )
        if seeded:
            seeded_brand, score = seeded
            hit = match_dso_brand(seeded_brand)
            if hit:
                canonical, pe = hit
                tag = f"{canonical}" + (f" — PE: {pe}" if pe else "")
                return "dso_national", f"Seeded DSO office address match: {tag} (score={score})"
            return "dso_regional", f"Seeded DSO office address match: {seeded_brand} (score={score})"

    # ---- Rule 3b: dso_national via affiliated_dso (set by Pass 2 location-match) ----
    affiliated = (loc.get("affiliated_dso") or "").upper().strip()
    if affiliated and affiliated not in _AFFILIATED_DSO_TAXONOMY_LEAKS:
        hit = match_dso_brand(affiliated)
        if hit:
            canonical, pe = hit
            tag = f"{canonical}" + (f" — PE: {pe}" if pe else "")
            return "dso_national", f"affiliated_dso match: {tag}"
        # Affiliated_dso is set, non-leaky, but doesn't match a known national brand
        # — treat as dso_regional (real DSO signal but not nationally branded)
        return "dso_regional", f"affiliated_dso present (non-national): {loc.get('affiliated_dso')}"

    # ---- Rule 4: dso_regional (STRONG signals only) ----
    # 4-pre. parent_company carries a KNOWN DSO brand (Data Axle Pass-6 corporate
    # linkage often names the acquirer even when the practice kept its local
    # name — e.g. parent='SONRAVA HEALTH' on 'Dentist in Vernon Hills LLC').
    # Promote to dso_national, but ONLY if the parent isn't just the practice's
    # own name echoed back (self-referential false positive).
    if parent and not _is_self_referential_parent(parent, name):
        phit = match_dso_brand(parent)
        if phit:
            canonical, pe = phit
            tag = f"{canonical}" + (f" — PE: {pe}" if pe else "")
            return "dso_national", f"Parent company is known DSO brand: {tag} (parent={parent})"

    # 4a. Parent company is a real corporate parent (not a university,
    #     not the practice echoing its own name back as parent)
    if parent and not _is_university_parent(parent) and not _is_self_referential_parent(parent, name):
        return "dso_regional", f"Corporate parent: {parent}"

    # 4b. EIN shared across 3+ different ZIPs (genuine multi-location chain).
    #     Threshold raised from 2→3 (2026-05-30): a shared EIN across only TWO
    #     ZIPs is ambiguous — often two solo dentists sharing one billing/tax
    #     entity, not a corporate chain. Requiring 3+ ZIPs keeps the corporate
    #     floor defensible (Family Dental Care, Brite, Elmhurst remain; solo
    #     partnerships drop out).
    if ein and ein_zip_count.get(ein, 0) >= 3:
        zip_count = ein_zip_count[ein]
        return "dso_regional", f"EIN {ein} present in {zip_count} different ZIPs (multi-location chain)"

    # 4c. Real franchise (not taxonomy noise)
    if _is_real_franchise(franchise):
        return "dso_regional", f"Franchise affiliation: {franchise}"

    # 4d. branch + parent_company already handled by 4a; iusa+parent already handled by 4a

    # ---- University-parent special case: classify as non_clinical (academic) ----
    if parent and _is_university_parent(parent):
        return "non_clinical", f"Academic institution affiliation: {parent}"

    # ---- Edge case: genuinely empty shell ----
    # An org NPI is filed at the address but there are NO individual providers
    # AND no org-reported headcount AND no contact info — a billing-only /
    # admin-only / closed registration. Only THESE stay org_only_npi.
    # (Previously this swallowed ~500 real multi-dentist practices whose NPI-1
    #  records simply failed to group — see eff_pc fallback above.)
    if has_org_npi and eff_pc == 0 and not phone and not website:
        return "org_only_npi", "Org NPI only — no providers, no headcount, no contact info (admin/billing/closed)"
    # Otherwise (contact info present, or headcount available) fall through to
    # the size rules below; a contactable shell lands on solo_established via
    # the contactable-shell fallback rather than being junked.

    # ---- Rule 5: family_practice ----
    if eff_pc >= 2 and _has_shared_last_name(last_names):
        return "family_practice", f"{eff_pc} providers, ≥2 share a last name"

    # ---- Rule 6: large_group ----
    if eff_pc >= 4:
        return "large_group", f"{eff_pc} providers at one location, no DSO/family signals"

    # ---- Rule 7: small_group ----
    if eff_pc in (2, 3):
        return "small_group", f"{eff_pc} providers at one location, no DSO/family signals"

    # ---- Rule 8: solo_high_volume ----
    if eff_pc == 1:
        if (employee_count or 0) >= 5 or (estimated_revenue or 0) >= 800_000:
            return "solo_high_volume", f"Solo provider, {employee_count or 0} employees, ${(estimated_revenue or 0):,} revenue"

    # ---- Rule 9: solo_inactive ----
    if eff_pc <= 1 and not phone and not website:
        return "solo_inactive", "Solo/empty provider, no phone or website"

    # ---- Rule 10: solo_new ----
    if eff_pc == 1 and year_established and year_established >= 2016:
        return "solo_new", f"Solo provider, established {year_established}"

    # ---- Rule 11: solo_established (default) ----
    if eff_pc == 1:
        return "solo_established", "Solo provider, default (long-running or unknown vintage)"

    # ---- Fallback: contactable org shell with unknown size ----
    # eff_pc==0 but has phone/website → a real but un-sizable practice. Count it
    # as an independent solo (conservative) rather than invisible junk.
    if phone or website:
        return "solo_established", "Org NPI with contact info but no countable providers — presumed solo independent"

    # Final fallback (shouldn't hit)
    return "solo_established", "Default fallback"


def reclassify_all(session, dry_run=False):
    """Recompute entity_classification for every row in practice_locations."""

    # 1. Build EIN → ZIP-count map for chain detection
    log.info("Building EIN → distinct-ZIP map...")
    ein_rows = session.execute(text(
        "SELECT ein, COUNT(DISTINCT zip) AS zips "
        "FROM practice_locations "
        "WHERE ein IS NOT NULL AND ein <> '' "
        "GROUP BY ein"
    )).fetchall()
    ein_zip_count = {r[0]: r[1] for r in ein_rows}
    chain_eins = {e for e, c in ein_zip_count.items() if c >= 2}
    log.info("Found %d EINs total; %d shared across 2+ ZIPs (chain candidates)",
             len(ein_zip_count), len(chain_eins))

    # 2. Build NPI → last_name map for family-practice detection
    log.info("Building NPI → last_name map...")
    name_rows = session.execute(text(
        "SELECT npi, provider_last_name FROM practices "
        "WHERE provider_last_name IS NOT NULL AND provider_last_name <> ''"
    )).fetchall()
    last_names_by_npi = {r[0]: r[1] for r in name_rows}
    log.info("Loaded %d NPI → last_name mappings", len(last_names_by_npi))

    # 3. Build primary_npi → (franchise_name, iusa_number, location_type,
    #    num_providers) map. num_providers is the org-reported headcount used to
    #    rescue org_only_npi locations whose NPI-1 records failed to group.
    log.info("Building primary_npi → corporate-signal map...")
    extras_rows = session.execute(text(
        "SELECT npi, franchise_name, iusa_number, location_type, num_providers FROM practices"
    )).fetchall()
    primary_npi_extras = {
        r[0]: {
            "franchise_name": r[1],
            "iusa_number": r[2],
            "location_type": r[3],
            "num_providers": r[4],
        }
        for r in extras_rows
    }
    log.info("Loaded extras for %d NPIs", len(primary_npi_extras))

    # 3b. Build ZIP → [(dso_name, normalized_address)] index from seeded
    #     dso_locations (ground-truth office registry). Lets us catch
    #     DSO-acquired practices that kept their local name.
    dso_loc_index = _build_dso_location_index(session)
    log.info("Built seeded-DSO address index covering %d ZIPs", len(dso_loc_index))

    # 4. Fetch all locations
    log.info("Fetching all practice_locations rows...")
    loc_rows = session.execute(text(
        "SELECT location_id, normalized_address, zip, city, state, "
        "       practice_name, doing_business_as, primary_npi, org_npi, provider_npis, "
        "       provider_count, has_org_npi, is_specialist_only, is_likely_residential, "
        "       entity_classification, parent_company, ein, employee_count, "
        "       estimated_revenue, year_established, phone, website, taxonomy_codes, "
        "       affiliated_dso "
        "FROM practice_locations"
    )).fetchall()
    log.info("Loaded %d practice_locations rows", len(loc_rows))

    cols = [
        "location_id", "normalized_address", "zip", "city", "state",
        "practice_name", "doing_business_as", "primary_npi", "org_npi", "provider_npis",
        "provider_count", "has_org_npi", "is_specialist_only", "is_likely_residential",
        "entity_classification", "parent_company", "ein", "employee_count",
        "estimated_revenue", "year_established", "phone", "website", "taxonomy_codes",
        "affiliated_dso",
    ]

    before_counts = Counter()
    after_counts = Counter()
    transitions = Counter()
    updates = []

    for row in loc_rows:
        loc = dict(zip(cols, row))
        before_ec = loc["entity_classification"] or "NULL"
        before_counts[before_ec] += 1

        new_ec, reasoning = classify_one(
            loc, ein_zip_count, last_names_by_npi, primary_npi_extras,
            dso_loc_index=dso_loc_index,
        )
        after_counts[new_ec] += 1
        transitions[(before_ec, new_ec)] += 1

        if new_ec != before_ec or True:  # always store reasoning
            updates.append({
                "location_id": loc["location_id"],
                "entity_classification": new_ec,
                "classification_reasoning": reasoning,
            })

    log.info("Reclassification computed for %d rows", len(updates))
    log.info("BEFORE distribution: %s", dict(before_counts.most_common()))
    log.info("AFTER  distribution: %s", dict(after_counts.most_common()))

    # Print top transitions
    log.info("Top reclassification transitions:")
    for (before, after), count in transitions.most_common(15):
        if before != after:
            log.info("  %-25s -> %-25s : %d", before, after, count)

    if dry_run:
        log.info("[DRY RUN] Skipping database update.")
        return before_counts, after_counts, transitions

    # 5. Apply updates
    log.info("Writing %d updates to practice_locations...", len(updates))
    now = datetime.utcnow().isoformat()
    BATCH = 500
    for i in range(0, len(updates), BATCH):
        chunk = updates[i:i + BATCH]
        for u in chunk:
            session.execute(
                text(
                    "UPDATE practice_locations "
                    "SET entity_classification=:ec, "
                    "    classification_reasoning=:reason, "
                    "    updated_at=:now "
                    "WHERE location_id=:lid"
                ),
                {
                    "ec": u["entity_classification"],
                    "reason": u["classification_reasoning"],
                    "now": now,
                    "lid": u["location_id"],
                },
            )
        session.commit()
        if (i // BATCH) % 10 == 0:
            log.info("  ... committed %d/%d", min(i + BATCH, len(updates)), len(updates))

    log.info("All updates committed.")
    return before_counts, after_counts, transitions


# ---------------------------------------------------------------------------
# Spot-check sampler (validation aid)
# ---------------------------------------------------------------------------

def sample_validation(session, n=50):
    """Pick n random rows, print classification + reasoning for human review."""
    rows = session.execute(text(
        "SELECT practice_name, zip, city, provider_count, has_org_npi, "
        "       entity_classification, classification_reasoning, parent_company, ein "
        "FROM practice_locations "
        "ORDER BY RANDOM() LIMIT :n"
    ), {"n": n}).fetchall()

    print(f"\n{'='*100}")
    print(f"RANDOM SAMPLE OF {n} PRACTICE LOCATIONS — POST-RECLASSIFICATION")
    print(f"{'='*100}\n")
    for i, r in enumerate(rows, 1):
        print(f"{i:3d}. {(r[0] or '<no name>')[:50]:<50s} | {r[1]} {(r[2] or ''):<15s} | pc={r[3] or 0} org={r[4]} | {r[5]:<20s}")
        print(f"     reason: {(r[6] or '')[:120]}")
        if r[7]:
            print(f"     parent={r[7]}")
        if r[8]:
            print(f"     ein={r[8]}")
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Don't write to DB.")
    ap.add_argument("--sample", type=int, default=0, help="After update, print N random rows.")
    args = ap.parse_args()

    session = get_session()
    try:
        before, after, transitions = reclassify_all(session, dry_run=args.dry_run)

        print("\n" + "="*60)
        print("RECLASSIFICATION SUMMARY")
        print("="*60)
        print(f"\nBEFORE → AFTER counts:")
        all_keys = sorted(set(before) | set(after))
        print(f"  {'classification':<22s} {'before':>8s} {'after':>8s} {'delta':>8s}")
        for k in all_keys:
            b = before.get(k, 0)
            a = after.get(k, 0)
            print(f"  {k:<22s} {b:>8d} {a:>8d} {a-b:>+8d}")

        print(f"\nKey transitions (only different):")
        for (b, a), c in transitions.most_common():
            if b != a:
                print(f"  {b:<22s} -> {a:<22s} : {c:>5d}")

        if args.sample:
            sample_validation(session, n=args.sample)

    finally:
        session.close()


if __name__ == "__main__":
    main()
