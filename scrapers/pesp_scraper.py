"""
PESP Scraper — scrapes Private Equity Stakeholder Project monthly/annual posts
for dental PE acquisition deals.

Usage:
    python3 scrapers/pesp_scraper.py              # scrape and insert into DB
    python3 scrapers/pesp_scraper.py --dry-run     # parse only, print table
"""

import argparse
import re
import sys
import os
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.database import init_db, get_session, insert_deal, DB_PATH
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

log = get_logger("pesp_scraper")

# ── Constants ───────────────────────────────────────────────────────────────

HEADERS = {"User-Agent": "DentalPETracker/1.0 (academic research)"}
RATE_LIMIT_SECS = 2
DNS_RETRY_DELAYS = [1, 3, 10]  # seconds between retries on transient DNS/connection errors

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

YEARS = list(range(2020, date.today().year + 1))

KNOWN_PLATFORMS = [
    "Heartland Dental", "MB2 Dental", "Dental365", "Dental 365",
    "Specialized Dental Partners", "U.S. Oral Surgery Management", "USOSM",
    "Pacific Dental Services", "PDS Health", "PDS",
    "Aspen Dental", "Sage Dental", "Southern Orthodontic Partners",
    "Chord Specialty Dental Partners", "SALT Dental", "Salt Dental Collective",
    "Salt Dental Partners", "Smile Partners USA", "Parkview Dental Partners",
    "The Smilist", "Smilist Management", "Smilist Dental",
    "Lightwave Dental", "Great Expressions",
    "InterDent", "Affordable Care", "Benevis", "CDP", "Community Dental Partners",
    "Mortenson Dental Partners", "Risas Dental", "Western Dental",
    "Dental Care Alliance", "42 North Dental", "Tend", "MAX Surgical",
    "T Management", "Silver Creek Dental Partners",
    "Smile Doctors", "Apex Dental Partners", "Pearl Street Dental Partners",
    "PepperPointe Partnerships", "Shared Practices Group", "Lumio Dental",
    "Allied OMS", "beBright", "Choice Dental Group",
    "Blue Sea Dental", "Motor City Dental Partners", "Archway Dental Partners",
    "Vision Dental Partners", "Partnerships for Dentists",
    "Signature Dental Partners", "Haven Dental", "Sonrava Health",
    "North American Dental Group", "NADG", "Straine Dental Management",
    "D4C Dental Brands", "Midwest Dental", "Dental Associates Group",
    "OMS360", "Oral Surgery Partners", "US Endo Partners",
    "Endodontic Practice Partners", "MyOrthos",
    "Riccobene Associates", "Imagen Dental Partners",
    "Aria Care Partners", "Beacon Oral Specialists", "BRUSH 365",
    "Burch Dental Partners", "Choice Healthcare Services",
    "CollectiveCare Dental", "Damira Dental Studios",
    "EPIC4 Specialty Partners", "Guardian Dentistry Partners",
    "Innovate 32", "J&J Dental Support Services",
    "Magic Smiles for Kids", "Modern Micro Endodontics",
    "Operation Dental", "Passion Dental",
    "Premier Care Dental Management", "Specialty1 Partners",
    "Today's Dental Network",
    "Vitana Pediatric & Orthodontic Partners",
    "Dental Whale", "Shore Dental",
    # Additional platforms observed in PESP reports
    "Image Specialty Partners", "Mosaic Dental", "Dental Haus",
    "DCA", "Enable Dental", "Great Orthodontics", "Pinnacle Dental Partners",
    "Harmony Dental Partners", "Ascend Dental Solutions",
    "Ideal Dental Management Partners", "Ideal Dental",
]

KNOWN_PE_SPONSORS = [
    "KKR", "Charlesbank Capital Partners", "Charlesbank", "Warburg Pincus",
    "Quad-C Management", "Quad-C",
    "Oak Hill Capital", "The Jordan Company", "TJC", "Linden Capital Partners",
    "Rock Mountain Capital", "Cathay Capital", "Silver Oak Services Partners",
    "New Mountain Capital", "Vistria Group", "Ares Management", "American Securities",
    "Leonard Green & Partners", "Shore Capital Partners", "MedEquity Capital",
    "RF Investment Partners", "Latticework Capital", "Resolute Capital Partners",
    "Georgia Oak Partners", "Harvest Partners", "Mid Ocean Partners",
    "Partners Group", "Blackstone", "Audax Group", "Mubadala",
    "Comvest Partners", "Comvest Private Equity", "Comvest",
    "Great Hill Partners", "InTandem Capital Partners", "InTandem Capital",
    "Martis Capital", "ONCAP", "Zenyth Partners",
    "Brightwood Capital", "SkyKnight Capital", "Talisker Partners",
    "JLL Partners", "Sentinel Capital Partners", "Sun Capital Partners",
    "Court Square Capital", "Alpine Investors",
    "Bardo Capital",
    "Kohlberg & Company", "Thomas H. Lee Partners", "THL",
    "Clayton, Dubilier & Rice", "CD&R",
    "Mellon Stud Ventures",
]

STATE_MAP = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}
VALID_STATE_ABBREVS = set(STATE_MAP.values())

# Countries/regions that signal international deals (skip these)
INTERNATIONAL_KEYWORDS = [
    "australia", "australian", "canada", "canadian", "dentalcorp",
    "united kingdom", "u.k.", "uk-based", "england", "scotland", "wales",
    "ireland", "irish", "europe", "european", "belgium", "belgian",
    "france", "french", "germany", "german", "netherlands", "dutch",
    "spain", "spanish", "italy", "italian", "sweden", "swedish",
    "norway", "norwegian", "denmark", "danish", "switzerland", "swiss",
    "brazil", "brazilian", "mexico", "mexican", "new zealand",
    "toronto", "ontario", "british columbia", "alberta", "quebec",
]

CREDIT_KEYWORDS = [
    "s&p global", "s&p rated", "moody's", "fitch", "credit rating",
    "credit facility", "loan", "refinanc", "debt", "bond",
    "leverage ratio", "ebitda multiple", "provided financing",
    "term loan", "revolver", "capital structure",
]


# Phrases that indicate aggregate industry commentary, NOT a specific deal.
# Sentences containing these are pre-filtered BEFORE parse_deal() is called.
COMMENTARY_PATTERNS = [
    # Aggregate counts ("at least N dental companies", "N add-on acquisitions")
    r"at least \d+ (?:dental|outpatient|healthcare)",
    r"\d+ add-on acquisitions",
    r"\d+ deals? in \w+",
    r"\d+ (?:buyouts?|growth investments?|add-ons?)",
    # PESP self-referential
    r"\bpesp\b.{0,40}(?:report|document|identif|highlight|publish)",
    r"pesp reported how",
    r"pesp's \d{4} report",
    # "study found", "article highlighted", "researchers note", "critics"
    r"\bstudy found\b",
    r"\barticle (?:highlighted|reported)\b",
    r"\bresearchers? note\b",
    r"\bcritics? (?:have|claim)\b",
    r"\bexpos[eé]\b",
    r"\balleged\b",
    # Structural/aggregate commentary openings
    r"^dental care (?:was|saw|has|had|is)\b",
    r"^dental care (?:sector|industry|compan)",
    r"^(?:last year|in \d{4})[,\s]",
    r"^(?:seven|nine|ten|eleven|twelve|over half|more than half) of the",
    r"^(?:home health|outpatient care sector|january also|continued expansion)",
    r"^(?:both the dso|the dso industry|the risks? to|private equity has been|private equity firms? (?:have|dominate|spent|may))",
    r"^even amidst\b",
    r"^deeper dives\b",
    r"^a (?:similar|2021|month prior)\b",
    r"^for example,\b",
    r"^(?:over|more than) the (?:past|last|prior)",
    # Legislation / policy commentary
    r"laws? and proposed legislation",
    r"state legislative activity",
    # Generic PE risk commentary
    r"may come with risks",
    r"risks? to (?:quality of|patient)\b",
    r"profit-driven practices? in order to",
    # Additional boilerplate seen in PESP background sections
    r"^private.equity.owned dental companies have been found",
    r"^private equity(?:-owned)? (?:firms? )?(?:owned|dominated)",
    r"^because private equity firms? aim",
    r"^as of \d{4}, private equity",
    r"^these deals are primarily add-on acquisitions",
    r"^such acquisitions allow",
    r"^despite challenges in exit",
    r"^as (?:medical|msos|dental)",
    r"^pe firms? may believe",
    r"^private equity grows investment",
    r"^see our \d{4} report",
    r"dental care accounted for the (?:second|first|third|highest)",
    r"^the ftc (?:and|or)",
    r"^a recent research study",
    r"private equity firms? owned \d+ of the top \d+",
    r"^some private equity",
    r"pesp (?:recently|periodically|covers)",
    # More background phrases
    r"^according to the report",
    r"^the study also found",
    r"^for example, \w",
    r"growth among dental specialties",
    r"\ballege",
]

_COMMENTARY_RE = re.compile(
    "(?:" + "|".join(COMMENTARY_PATTERNS) + ")",
    re.IGNORECASE,
)


def _is_commentary(text):
    """Return True if text is aggregate/background commentary, not a specific deal."""
    return bool(_COMMENTARY_RE.search(text))


def _is_international(text):
    """Check if text describes an international (non-US) deal."""
    t = text.lower()
    for kw in INTERNATIONAL_KEYWORDS:
        if kw in t:
            return True
    if re.search(r'\buk\b', t):
        return True
    return False


def _is_credit_news(text):
    """Check if text is about credit/debt/ratings, not an actual deal."""
    t = text.lower()
    for kw in CREDIT_KEYWORDS:
        if kw in t:
            return True
    return False


# ── URL Discovery ───────────────────────────────────────────────────────────


def build_candidate_urls():
    """Generate all candidate PESP URLs to check."""
    urls = []
    for year in YEARS:
        for i, month in enumerate(MONTHS, 1):
            url = f"https://pestakeholder.org/news/private-equity-health-care-acquisitions-{month}-{year}/"
            urls.append((url, date(year, i, 1)))
        # Annual reviews — try both slug variants
        urls.append((
            f"https://pestakeholder.org/reports/healthcare-deals-{year}-in-review/",
            date(year, 12, 1),
        ))
        urls.append((
            f"https://pestakeholder.org/reports/pe-healthcare-deals-{year}-in-review/",
            date(year, 12, 1),
        ))
    return urls


def _request_with_retry(method, url, **kwargs):
    """Wrap requests.head/get with retry logic for transient DNS/connection errors."""
    last_exc = None
    for attempt, delay in enumerate([0] + DNS_RETRY_DELAYS):
        if delay:
            log.debug("Retry %d for %s (sleeping %ds)", attempt, url, delay)
            time.sleep(delay)
        try:
            fn = requests.head if method == "head" else requests.get
            return fn(url, **kwargs)
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            err_str = str(e)
            # Only retry on transient DNS / connection reset errors
            if "NameResolutionError" in err_str or "Failed to resolve" in err_str or "ConnectionReset" in err_str:
                log.debug("Transient connection error on attempt %d: %s", attempt + 1, err_str[:120])
                continue
            raise  # non-transient: propagate immediately
        except requests.RequestException:
            raise  # timeouts, HTTP errors etc — don't retry
    raise last_exc  # exhausted retries


def discover_valid_urls(candidates):
    """HEAD-check each URL, return list of (url, deal_date) that exist."""
    valid = []
    for url, deal_date in candidates:
        try:
            resp = _request_with_retry("head", url, headers=HEADERS, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                log.info("FOUND: %s", url)
                valid.append((url, deal_date))
            else:
                log.debug("SKIP %d: %s", resp.status_code, url)
        except requests.RequestException as e:
            log.warning("HEAD failed for %s: %s", url, e)
        time.sleep(0.3)  # light rate limit for HEAD checks
    log.info("Discovered %d valid pages out of %d candidates", len(valid), len(candidates))
    return valid


# ── Parsing ─────────────────────────────────────────────────────────────────


def fetch_page(url):
    """Fetch and parse a page. Returns BeautifulSoup or None."""
    try:
        resp = _request_with_retry("get", url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return None


def _normalize_text(el):
    """Extract text with spaces between tags, then collapse whitespace."""
    raw = el.get_text(separator=" ")
    return re.sub(r'\s+', ' ', raw).strip()


def extract_dental_sections(soup):
    """Find paragraphs/sections related to dental deals."""
    dental_paragraphs = []

    # Also look for headings that signal dental sections
    dental_section_active = False
    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "ul", "ol"]):
        text = _normalize_text(el)
        if not text:
            continue
        tag = el.name
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if re.search(r"\bdental\b", text, re.IGNORECASE):
                dental_section_active = True
                continue
            elif dental_section_active:
                # New non-dental heading ends the dental section
                dental_section_active = False
                continue

        # Skip footnote citations like "[1] ...", "[23] ..."
        if re.match(r'^\[\d', text):
            continue

        if dental_section_active and tag in ("p", "li", "td"):
            dental_paragraphs.append(text)
        elif tag in ("p", "li", "td") and _mentions_dental(text):
            dental_paragraphs.append(text)

    return dental_paragraphs


def _mentions_dental(text):
    """Check if text mentions dental-related content."""
    t = text.lower()
    if not re.search(r"\bdental\b|\borthodont|\bendodont|\bperiodont|\boral surgery\b|\bprosthodont|\bmaxillofacial\b|\bdso\b", t):
        return False
    # Must also mention a known platform or PE sponsor or an acquisition verb
    for p in KNOWN_PLATFORMS:
        if p.lower() in t:
            return True
    for s in KNOWN_PE_SPONSORS:
        if s.lower() in t:
            return True
    if re.search(r"\bacquir|\bmerge|\badd-on\b|\bbuyout\b|\brecap|\binvest|\bpartner|\bplatform\b|\bbacked\b|\bowned\b|\bportfolio\b", t):
        return True
    return False


def split_into_deal_sentences(paragraphs):
    """Split paragraphs into individual sentences that likely describe deals."""
    sentences = []
    for para in paragraphs:
        # Split on period followed by space+capital, or semicolons, or bullet-style
        # Protect known abbreviations from splitting
        protected = para
        for abbr in ('U.S.', 'Dr.', 'Mr.', 'Ms.', 'Jr.', 'Sr.', 'Inc.', 'Ltd.', 'Corp.', 'Co.', 'St.', 'Ave.', 'vs.', 'D.D.S.', 'D.M.D.', 'M.D.', 'Ph.D.', 'B.S.', 'M.S.', 'P.C.', 'P.A.', 'L.L.C.', 'L.P.', 'No.', 'Ft.', 'Mt.'):
            protected = protected.replace(abbr, abbr.replace('.', '\x00'))
        parts_raw = re.split(r'(?<=[.;])\s+(?=[A-Z])', protected)
        parts = [p.replace('\x00', '.') for p in parts_raw]
        for part in parts:
            part = part.strip()
            if len(part) > 30 and _is_deal_sentence(part):
                sentences.append(part)
    # If no sentence-level splits found anything, try whole paragraphs
    if not sentences:
        for para in paragraphs:
            if len(para) > 30 and _is_deal_sentence(para):
                sentences.append(para)
    return sentences


def _is_deal_sentence(text):
    """Does this sentence describe a specific acquisition/deal (not aggregate commentary)?"""
    # Pre-filter: reject known commentary patterns before expensive checks
    if _is_commentary(text):
        return False
    t = text.lower()
    has_verb = bool(re.search(r"\bacquir|\bmerge|\badd-on|\bbought|\bpurchas|\binvest|\bpartner|\bexpand|\bopen|\blaunch|\bgrowth|\brecap|\bbacked\b|\bowned\b|\bportfolio\b|\bplatform\b", t))
    has_entity = any(p.lower() in t for p in KNOWN_PLATFORMS) or any(s.lower() in t for s in KNOWN_PE_SPONSORS)
    return has_verb or has_entity


def parse_deal(sentence):
    """Parse a single deal sentence into structured fields. Returns list of deal dicts (one per state)."""
    if _is_international(sentence):
        return []
    if _is_credit_news(sentence):
        return []
    platform = extract_platform(sentence)
    pe_sponsor = extract_pe_sponsor(sentence)
    target = extract_target(sentence, platform)
    states = extract_states(sentence)
    specialty = detect_specialty(sentence)
    deal_type = detect_deal_type(sentence, platform)

    if not platform and not pe_sponsor:
        return []

    if not states:
        states = [None]

    deals = []
    for state in states:
        deals.append({
            "platform_company": platform or "Unknown",
            "pe_sponsor": pe_sponsor,
            "target_name": target,
            "target_state": state,
            "deal_type": deal_type,
            "specialty": specialty,
            "raw_text": sentence,
        })
    return deals


def extract_platform(text):
    """Find a known platform company in the text."""
    # Sort by length descending so longer names match first (e.g., "Pacific Dental Services" before "PDS")
    for p in sorted(KNOWN_PLATFORMS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(p) + r'\b', text, re.IGNORECASE):
            return p
    return None


def extract_pe_sponsor(text):
    """Extract PE sponsor from known patterns."""
    t = text

    # Pattern: "(Sponsor Name)" right after company — check ALL parentheticals
    for paren_match in re.finditer(r'\(([^)]{3,60})\)', t):
        candidate = paren_match.group(1).strip()
        sponsor = _match_known_sponsor(candidate)
        if sponsor:
            return sponsor

    # Pattern: "owned by X", "backed by X", "portfolio company of X"
    for pattern in [
        r'owned by\s+([A-Z][A-Za-z\s&]+?)(?:[,.\)]|which|that)',
        r'backed by\s+([A-Z][A-Za-z\s&]+?)(?:[,.\)]|which|that)',
        r'portfolio company of\s+([A-Z][A-Za-z\s&]+?)(?:[,.\)]|which|that)',
        r'owned by\s+([A-Z][A-Za-z\s&]+?)$',
        r'backed by\s+([A-Z][A-Za-z\s&]+?)$',
        r'portfolio company of\s+([A-Z][A-Za-z\s&]+?)$',
    ]:
        m = re.search(pattern, t)
        if m:
            sponsor = _match_known_sponsor(m.group(1).strip())
            if sponsor:
                return sponsor

    # Brute force: check all known sponsors against full text
    for s in sorted(KNOWN_PE_SPONSORS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(s) + r'\b', t, re.IGNORECASE):
            return s

    return None


def _match_known_sponsor(candidate):
    """Check if candidate string contains a known PE sponsor name."""
    if len(candidate.strip()) < 3:
        return None
    for s in sorted(KNOWN_PE_SPONSORS, key=len, reverse=True):
        if s.lower() in candidate.lower():
            return s
    return None


def extract_target(text, platform):
    """Try to extract the target practice name."""
    # Pattern: "acquired [Target Name]" or "added [Target Name]"
    for pattern in [
        r'acquir(?:ed|ing)\s+([A-Z][A-Za-z\s\'\-&]{3,50}?)(?:\s+in\s|\s+from\s|,|\.|;|\s+and\s)',
        r'added\s+([A-Z][A-Za-z\s\'\-&]{3,50}?)(?:\s+in\s|\s+to\s|,|\.|;|\s+and\s)',
        r'purchased\s+([A-Z][A-Za-z\s\'\-&]{3,50}?)(?:\s+in\s|\s+from\s|,|\.|;|\s+and\s)',
        r'bought\s+([A-Z][A-Za-z\s\'\-&]{3,50}?)(?:\s+in\s|\s+from\s|,|\.|;|\s+and\s)',
        r'merged with\s+([A-Z][A-Za-z\s\'\-&]{3,50}?)(?:\s+in\s|,|\.|;)',
    ]:
        m = re.search(pattern, text)
        if m:
            target = m.group(1).strip()
            # Don't return the platform as the target
            if platform and target.lower() == platform.lower():
                continue
            # Filter out generic words
            if target.lower() in ("the", "a", "an", "its", "their", "several", "multiple", "two", "three", "four", "five"):
                continue
            return target
    return None


def extract_states(text):
    """Extract state abbreviations from text."""
    states = set()

    # Check for 2-letter state abbreviations (bounded by non-alpha)
    for m in re.finditer(r'\b([A-Z]{2})\b', text):
        abbrev = m.group(1)
        if abbrev in VALID_STATE_ABBREVS:
            states.add(abbrev)

    # Check for full state names
    t_lower = text.lower()
    for name, abbrev in STATE_MAP.items():
        if re.search(r'\b' + re.escape(name) + r'\b', t_lower):
            states.add(abbrev)

    # Filter out false positives (common abbreviations that are also state codes)
    # Keep: most are fine. Remove obvious false positives contextually.
    false_positives = set()
    for s in states:
        if s == "OR" and not re.search(r'\bOregon\b', text, re.IGNORECASE):
            # "OR" is usually the conjunction, not Oregon
            if not re.search(r'\bOR\b(?:\s*,|\s*and\b|\s*-)', text):
                false_positives.add(s)
        if s == "IN" and not re.search(r'\bIndiana\b', text, re.IGNORECASE):
            false_positives.add(s)
        if s == "ME" and not re.search(r'\bMaine\b', text, re.IGNORECASE):
            false_positives.add(s)

    states -= false_positives
    return list(states) if states else []


def detect_specialty(text):
    """Detect dental specialty from text."""
    t = text.lower()
    if re.search(r'oral surgery|maxillofacial', t):
        return "oral_surgery"
    if re.search(r'orthodont', t):
        return "orthodontics"
    if re.search(r'endodont', t):
        return "endodontics"
    if re.search(r'periodont', t):
        return "periodontics"
    if re.search(r'pediatric dent|pedo', t):
        return "pediatric"
    if re.search(r'prosthodont', t):
        return "prosthodontics"
    if re.search(r'multi[- ]?specialty|multi[- ]?disciplin', t):
        return "multi_specialty"
    return "general"


def detect_deal_type(text, platform):
    """Detect deal type from text."""
    t = text.lower()
    if re.search(r'\brecapital|\brecap\b', t):
        return "recapitalization"
    if re.search(r'\bde novo\b|\bopened\b|\bnew location', t):
        return "de_novo"
    if re.search(r'\bnew platform\b', t):
        return "buyout"
    if re.search(r'\bbuyout\b', t):
        return "buyout"
    if re.search(r'\bgrowth\b|\bexpansion capital\b|\binvestment in\b', t):
        return "growth"
    if re.search(r'\bpartnership\b', t):
        return "partnership"
    # "acquired" by a known platform → add-on
    if platform and re.search(r'\bacquir|\badded\b|\badd-on\b|\bpurchas|\bbought\b', t):
        return "add-on"
    # "acquired" without known platform → could be buyout
    if re.search(r'\bacquir|\bpurchas|\bbought\b', t) and not platform:
        return "buyout"
    return "unknown"


# ── Scraper Orchestration ──────────────────────────────────────────────────


def scrape_page(url, deal_date):
    """Scrape a single page. Returns list of parsed deal dicts."""
    soup = fetch_page(url)
    if not soup:
        return None  # signals fetch failure

    paragraphs = extract_dental_sections(soup)
    if not paragraphs:
        log.info("No dental content found on %s", url)
        return []

    sentences = split_into_deal_sentences(paragraphs)
    log.info("Found %d dental deal sentences on %s", len(sentences), url)

    deals = []
    parse_failures = 0
    for sentence in sentences:
        try:
            parsed = parse_deal(sentence)
            if parsed:
                for d in parsed:
                    d["deal_date"] = deal_date
                    d["source"] = "pesp"
                    d["source_url"] = url
                deals.extend(parsed)
            else:
                log.warning("PARSE FAIL — could not extract deal from: %.200s", sentence)
                parse_failures += 1
        except Exception as e:
            log.warning("PARSE ERROR on sentence: %.200s — %s", sentence, e)
            parse_failures += 1

    return deals


def run(dry_run=False):
    """Main entry point."""
    _t0 = log_scrape_start("pesp_scraper")
    log.info("=" * 60)
    log.info("PESP Scraper starting (dry_run=%s)", dry_run)
    log.info("=" * 60)

    # Step 1: Discover valid URLs
    candidates = build_candidate_urls()
    log.info("Checking %d candidate URLs...", len(candidates))
    valid_urls = discover_valid_urls(candidates)

    if not valid_urls:
        log.warning("No valid PESP pages found. Exiting.")
        log_scrape_complete("pesp_scraper", _t0, new_records=0,
                            summary="PESP: No valid pages found")
        return

    # Step 2: Scrape each page
    if not dry_run:
        init_db()
    session = get_session() if not dry_run else None

    all_deals = []
    pages_success = 0
    pages_failed = 0
    failed_urls = []

    try:
        for url, deal_date in valid_urls:
            log.info("Scraping: %s", url)
            deals = scrape_page(url, deal_date)

            if deals is None:
                pages_failed += 1
                failed_urls.append(url)
            else:
                pages_success += 1
                all_deals.extend(deals)

            time.sleep(RATE_LIMIT_SECS)

        # Step 3: Insert or print
        new_inserted = 0
        duplicates = 0

        if dry_run:
            _print_dry_run_table(all_deals)
        else:
            for deal in all_deals:
                try:
                    result = insert_deal(
                        session,
                        deal_date=deal["deal_date"],
                        platform_company=deal["platform_company"],
                        pe_sponsor=deal.get("pe_sponsor"),
                        target_name=deal.get("target_name"),
                        target_state=deal.get("target_state"),
                        deal_type=deal.get("deal_type"),
                        specialty=deal.get("specialty"),
                        source=deal["source"],
                        source_url=deal["source_url"],
                        raw_text=deal.get("raw_text"),
                    )
                    if result:
                        new_inserted += 1
                    else:
                        duplicates += 1
                except Exception as e:
                    log.error("Insert error: %s", e)

        # Step 4: Summary
        log.info("")
        log.info("=" * 60)
        log.info("PESP SCRAPER SUMMARY")
        log.info("=" * 60)
        log.info("Pages found:            %d", len(valid_urls))
        log.info("Pages scraped OK:       %d", pages_success)
        log.info("Pages failed:           %d", pages_failed)
        if failed_urls:
            for u in failed_urls:
                log.info("  FAILED: %s", u)
        log.info("Total deal mentions:    %d", len(all_deals))
        if not dry_run:
            log.info("New deals inserted:     %d", new_inserted)
            log.info("Duplicates skipped:     %d", duplicates)
            log_scrape_complete("pesp_scraper", _t0, new_records=new_inserted,
                                summary=f"PESP: {new_inserted} new deals, {duplicates} dupes ({pages_success} pages scraped)",
                                extra={"duplicates": duplicates, "pages_scraped": pages_success, "pages_failed": pages_failed})
        log.info("=" * 60)
    finally:
        if session:
            session.close()


def _print_dry_run_table(deals):
    """Print parsed deals as a formatted table for visual verification."""
    if not deals:
        print("\n  No deals parsed.\n")
        return

    print()
    header = f"{'#':>3}  {'Date':10}  {'Platform':30}  {'PE Sponsor':28}  {'Target':30}  {'ST':2}  {'Type':10}  {'Specialty':14}"
    print(header)
    print("-" * len(header))
    for i, d in enumerate(deals, 1):
        print(
            f"{i:>3}  "
            f"{str(d.get('deal_date', '')):10}  "
            f"{(d.get('platform_company') or '?')[:30]:30}  "
            f"{(d.get('pe_sponsor') or '—')[:28]:28}  "
            f"{(d.get('target_name') or '—')[:30]:30}  "
            f"{(d.get('target_state') or '??'):2}  "
            f"{(d.get('deal_type') or '?')[:10]:10}  "
            f"{(d.get('specialty') or '?')[:14]:14}"
        )
    print(f"\nTotal: {len(deals)} deal(s) parsed\n")


# ── CLI ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape PESP for dental PE deals")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't insert into DB")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
