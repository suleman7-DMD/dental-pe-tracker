"""
dso_brands.py — SINGLE SOURCE OF TRUTH for known DSO brand names.

Before this module, two separate brand lists existed and silently diverged:
  - dso_classifier.py::KNOWN_DSOS         (~75 brands, NPI-level name match)
  - reclassify_locations.py::_KNOWN_NATIONAL_DSOS (~40 brands, location-level)

The location reclassifier used the *smaller* list, so brands the NPI classifier
recognized were invisible at the location level — directly depressing the
confirmed corporate floor. This module merges both, expands coverage with
brands that have real Midwest/Chicagoland and Boston-metro footprints, and
corrects PE-sponsor attributions.

HONESTY RULE: pe_sponsor is set ONLY when the PE/control owner is known with
confidence as of 2026. Founder-owned DSOs (Pacific Dental, Comfort Dental,
Dental Dreams, 1st Family Dental) and brands whose sponsor we cannot verify
keep pe_sponsor=None. We do not guess sponsors — an unknown sponsor still
counts as a confirmed *DSO* (dso_affiliated), just not pe_backed.

Entries are (pattern_lower, canonical_name, pe_sponsor_or_None).
`match_dso_brand()` sorts longest-pattern-first to avoid partial collisions.
"""

# (dso_name_pattern_lowercase, canonical_dso_name, pe_sponsor_or_None)
KNOWN_DSOS = [
    # ── National platforms (largest, with confirmed PE/control owners) ──
    ("heartland dental", "Heartland Dental", "KKR"),
    ("aspen dental", "Aspen Dental", "American Securities; Leonard Green & Partners"),
    ("aspen dental management", "Aspen Dental", "American Securities; Leonard Green & Partners"),
    ("admi corp", "Aspen Dental", "American Securities; Leonard Green & Partners"),  # Aspen Dental Mgmt Inc
    ("tag - the aspen group", "Aspen Dental", "American Securities; Leonard Green & Partners"),
    ("the aspen group", "Aspen Dental", "American Securities; Leonard Green & Partners"),
    ("clearchoice", "ClearChoice Dental Implants", "American Securities; Leonard Green & Partners"),
    ("clear choice dental", "ClearChoice Dental Implants", "American Securities; Leonard Green & Partners"),
    ("pacific dental services", "Pacific Dental Services", None),  # founder-owned
    ("pds health", "Pacific Dental Services", None),
    ("western dental", "Western Dental", "New Mountain Capital"),
    ("sonrava health", "Western Dental", "New Mountain Capital"),
    ("sonrava", "Western Dental", "New Mountain Capital"),
    ("brident dental", "Brident", "New Mountain Capital"),  # Sonrava brand
    ("brident", "Brident", "New Mountain Capital"),
    ("castle dental", "Castle Dental", "New Mountain Capital"),  # Sonrava brand
    ("smile brands", "Smile Brands", "Gryphon Investors"),
    ("bright now", "Smile Brands", "Gryphon Investors"),
    ("bright now! dental", "Smile Brands", "Gryphon Investors"),
    ("monarch dental", "Monarch Dental", "Gryphon Investors"),  # Smile Brands brand
    ("midwest dental", "Midwest Dental", "Gryphon Investors"),  # Smile Brands (2019)
    ("affordable care", "Affordable Care", "Berkshire Partners"),
    ("affordable dentures", "Affordable Care", "Berkshire Partners"),
    ("great expressions", "Great Expressions", "Roark Capital"),
    ("dental care alliance", "Dental Care Alliance", "Harvest Partners"),
    ("north american dental group", "North American Dental Group", "Jacobs Holding"),
    ("nadg", "North American Dental Group", "Jacobs Holding"),
    ("mb2 dental", "MB2 Dental", "Charlesbank Capital Partners; Warburg Pincus"),
    ("benevis", "Benevis", None),
    ("kool smiles", "Benevis", None),
    ("interdent", "InterDent", None),
    ("gentle dental", "Gentle Dental", None),  # InterDent / 42 North in NE
    ("42 north dental", "42 North Dental", None),
    ("comfort dental", "Comfort Dental", None),  # franchise, founder-owned

    # ── Mid-size / specialty platforms (confirmed sponsors) ──
    ("dental365", "Dental365", "The Jordan Company"),
    ("dental 365", "Dental365", "The Jordan Company"),
    ("deca dental", "DECA Dental / Ideal Dental", "The Jordan Company"),
    ("ideal dental", "DECA Dental / Ideal Dental", "The Jordan Company"),
    ("sage dental", "Sage Dental", "Linden Capital Partners"),
    ("specialized dental partners", "Specialized Dental Partners", "Quad-C Management"),
    ("southern orthodontic partners", "Southern Orthodontic Partners", "Shore Capital Partners"),
    ("smile doctors", "Smile Doctors", "Thomas H. Lee Partners"),
    ("us oral surgery management", "USOSM", "Oak Hill Capital"),
    ("u.s. oral surgery management", "USOSM", "Oak Hill Capital"),
    ("usosm", "USOSM", "Oak Hill Capital"),
    ("salt dental", "SALT Dental", "Latticework Capital"),
    ("chord specialty", "Chord Specialty Dental Partners", "Rock Mountain Capital"),
    ("max surgical", "MAX Surgical", "MedEquity Capital"),
    ("smile partners", "Smile Partners USA", "Silver Oak Services Partners"),
    ("parkview dental partners", "Parkview Dental Partners", "Cathay Capital"),
    ("t management group", "T Management", "Georgia Oak Partners"),
    ("archway dental", "Archway Dental Partners", "Martis Capital"),
    ("bebright", "beBright", "InTandem Capital Partners"),
    ("riccobene", "Riccobene Associates", "Comvest Partners"),
    ("gen4 dental", "Gen4 Dental Partners", "Cordovan Capital Management"),
    ("rodeo dental", "Rodeo Dental", "Tinicum"),
    ("lightwave dental", "Lightwave Dental", None),
    ("imagen dental", "Imagen Dental Partners", None),

    # ── Founder-owned / sponsor-unverified DSOs (DSO, not pe_backed) ──
    ("tend dental", "Tend", None),
    ("tend studio", "Tend", None),
    ("mortenson dental", "Mortenson Dental Partners", None),
    ("community dental partners", "Community Dental Partners", None),
    ("risas dental", "Risas Dental", None),
    ("familia dental", "Familia Dental", None),
    ("jefferson dental", "Jefferson Dental", None),
    ("smile design dentistry", "Smile Design Dentistry", None),
    ("d4c dental", "D4C Dental Brands", None),
    ("smilist", "The Smilist", None),
    ("silver creek dental", "Silver Creek Dental Partners", None),
    ("elevate dental", "Elevate Dental", None),
    ("peak dental", "Peak Dental", None),
    ("dental one partners", "Dental One Partners", None),
    ("dentalone", "Dental One Partners", None),
    ("dentalcorp", "Dentalcorp", None),
    ("careington", "Careington", None),
    ("access dental", "Access Dental", None),
    ("birner dental", "Birner Dental", None),
    ("corus orthodontist", "Corus Orthodontists", None),
    ("orthosynetics", "OrthoSynetics", None),
    ("dental associates group", "Dental Associates Group", None),
    ("oms360", "OMS360", None),
    ("oral surgery partners", "Oral Surgery Partners", None),
    ("us endo partners", "US Endo Partners", None),
    ("endodontic practice partners", "Endodontic Practice Partners", None),
    ("vision dental partners", "Vision Dental Partners", None),
    ("apex dental partners", "Apex Dental Partners", None),
    ("blue sea dental", "Blue Sea Dental", None),
    ("motor city dental", "Motor City Dental Partners", None),
    ("pearl street dental", "Pearl Street Dental Partners", None),
    ("lumio dental", "Lumio Dental", None),
    ("straine dental", "Straine Dental Management", None),
    ("shared practices", "Shared Practices Group", None),
    ("choice dental", "Choice Dental Group", None),
    ("pepperpointe", "PepperPointe Partnerships", None),
    ("immediadent", "ImmediaDent", None),
    ("specialty dental brands", "Specialty Dental Brands", None),

    # ── Chicagoland / Midwest-rooted DSOs (high local relevance) ──
    ("dental dreams", "Dental Dreams", None),          # KOS Services, Chicago HQ
    ("kos services", "Dental Dreams", None),
    ("1st family dental", "1st Family Dental", None),   # Chicago DSO
    ("first family dental", "1st Family Dental", None),
    ("dentologie", "Dentologie", None),                # Chicago
    ("forwarddental", "Forward Dental", "Friedman Fleischer & Lowe"),
    ("forward dental", "Forward Dental", "Friedman Fleischer & Lowe"),
    ("webster dental", "Webster Dental Management", None),  # Chicago
    ("dental salon", "Dental Salon", None),
]

# Pre-sorted longest-first so e.g. "dental care alliance" beats "dental care".
_SORTED = sorted(KNOWN_DSOS, key=lambda x: len(x[0]), reverse=True)

# Uppercase brand tokens for fast "is this name a national DSO" checks
# (used by location reclassifier name-matching).
NATIONAL_DSO_BRANDS = sorted({canonical.upper() for _, canonical, _ in KNOWN_DSOS})


def match_dso_brand(name, dba=None):
    """Return (canonical_name, pe_sponsor) if `name`/`dba` contains a known DSO
    brand pattern, else None. Case-insensitive, longest-pattern-first.
    """
    haystack = " ".join(p for p in (name, dba) if p).lower()
    if not haystack:
        return None
    for pattern, canonical, pe_sponsor in _SORTED:
        if pattern in haystack:
            return canonical, pe_sponsor
    return None
