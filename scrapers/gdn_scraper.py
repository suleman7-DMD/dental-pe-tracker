"""
GDN Scraper — scrapes Group Dentistry Now monthly "DSO Deal Roundup" posts
for dental PE acquisition deals.

Usage:
    python3 scrapers/gdn_scraper.py              # scrape and insert into DB
    python3 scrapers/gdn_scraper.py --dry-run     # parse only, print table
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
from scrapers.database import init_db, get_session, insert_deal
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

log = get_logger("gdn_scraper")

# ── Constants ───────────────────────────────────────────────────────────────

HEADERS = {"User-Agent": "DentalPETracker/1.0 (academic research)"}
RATE_LIMIT_SECS = 2
CATEGORY_BASE = "https://www.groupdentistrynow.com/dso-group-blog/category/dso-news/dso-deals/"
MAX_PAGES = 10  # safety cap

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
    "Allied OMS", "beBright", "BeBright", "Choice Dental Group",
    "Blue Sea Dental", "Motor City Dental Partners", "Archway Dental Partners",
    "Vision Dental Partners", "Partnerships for Dentists",
    "Signature Dental Partners", "Haven Dental", "Sonrava Health",
    "North American Dental Group", "NADG", "Straine Dental Management",
    "D4C Dental Brands", "Midwest Dental", "Dental Associates Group",
    "OMS360", "Oral Surgery Partners", "US Endo Partners",
    "Endodontic Practice Partners", "MyOrthos",
    "Riccobene Associates", "Imagen Dental Partners",
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
    "Comvest Partners", "Comvest Private Equity",
    "Great Hill Partners", "InTandem Capital Partners", "InTandem Capital",
    "Martis Capital", "ONCAP", "Zenyth Partners",
    "Brightwood Capital", "SkyKnight Capital", "Talisker Partners",
    "JLL Partners", "Sentinel Capital Partners", "Sun Capital Partners",
    "Court Square Capital", "Alpine Investors",
    "Kohlberg & Company", "Thomas H. Lee Partners", "THL",
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
    "north yorkshire", "south perth", "western australia", "queensland",
    "ontario", "british columbia", "alberta", "quebec",
    "dental care ireland", "the dental hub",
]

# Credit/debt/ratings keywords — skip these entries
CREDIT_KEYWORDS = [
    "s&p global", "s&p rated", "moody's", "fitch", "credit rating",
    "credit facility", "loan", "refinanc", "debt", "bond",
    "leverage ratio", "ebitda multiple", "provided financing",
    "term loan", "revolver", "capital structure",
]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _normalize_text(el):
    """Extract text with spaces between tags, then collapse whitespace."""
    raw = el.get_text(separator=" ")
    return re.sub(r'\s+', ' ', raw).strip()


# ── URL Discovery ───────────────────────────────────────────────────────────


def discover_roundup_urls():
    """Crawl the GDN dso-deals category pages to find all roundup post URLs."""
    all_posts = []  # list of (url, title)
    page_num = 1

    while page_num <= MAX_PAGES:
        if page_num == 1:
            cat_url = CATEGORY_BASE
        else:
            cat_url = f"{CATEGORY_BASE}page/{page_num}/"

        log.info("Fetching category page %d: %s", page_num, cat_url)
        try:
            resp = requests.get(cat_url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                log.info("Category page %d returned 404, done.", page_num)
                break
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("Failed to fetch category page %d: %s", page_num, e)
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # Find post links — they're in article titles or entry-title headings
        found_on_page = 0
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            # Filter for roundup posts
            if _is_roundup_link(href, text):
                url = href if href.startswith("http") else f"https://www.groupdentistrynow.com{href}"
                if url not in [u for u, _ in all_posts]:
                    all_posts.append((url, text))
                    found_on_page += 1

        log.info("Found %d roundup links on page %d", found_on_page, page_num)
        if found_on_page == 0:
            break

        page_num += 1
        time.sleep(1)

    log.info("Total roundup URLs discovered: %d", len(all_posts))
    return all_posts


def _is_roundup_link(href, text):
    """Check if a link is a DSO Deal Roundup post."""
    t = text.lower()
    h = href.lower()
    # Title-based: must contain "deal roundup" or "dso deal"
    if "deal roundup" in t or "dso deal" in t:
        return True
    # URL-based: common roundup slug patterns
    if re.search(r'dso-deal-roundup|dso-deals|dso-mergers|dso-acquisitions|dental-mergers|dental-acquisitions|dental-business|dso-dental-mergers|dso-and-dental-mergers|q[1-4]-20\d{2}', h):
        # Exclude "top 10" year-end listicles
        if "top-10" in h or "top 10" in t:
            return False
        return True
    return False


# ── Post Parsing ────────────────────────────────────────────────────────────


def extract_deal_date_from_title(title):
    """Extract month/year from a roundup post title like 'DSO Deal Roundup – October 2025'."""
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    t = title.lower()

    # Try "month year" pattern
    for name, num in months.items():
        m = re.search(rf'\b{name}\s+(\d{{4}})\b', t)
        if m:
            return date(int(m.group(1)), num, 1)

    # Try Q1-Q4 pattern
    qm = re.search(r'\bq([1-4])\s+(\d{4})\b', t)
    if qm:
        quarter = int(qm.group(1))
        year = int(qm.group(2))
        month = (quarter - 1) * 3 + 1
        return date(year, month, 1)

    # Try just a year
    ym = re.search(r'\b(20\d{2})\b', t)
    if ym:
        return date(int(ym.group(1)), 1, 1)

    return None


def fetch_page(url):
    """Fetch and parse a page. Returns BeautifulSoup or None."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return None


def extract_title(soup):
    """Extract the post title from the page."""
    title_el = soup.find("h1", class_="entry-title") or soup.find("h1")
    if title_el:
        return _normalize_text(title_el)
    return ""


def extract_deal_blocks(soup):
    """Split the post content into individual deal blocks separated by <hr> or ***."""
    # Find the main content area
    content = soup.find("div", class_="entry-content")
    if not content:
        content = soup.find("article") or soup

    # Collect all direct children (p, hr, h2, h3, etc.)
    blocks = []
    current_block = []

    for el in content.find_all(["p", "hr", "h2", "h3", "h4", "ul", "ol", "li"]):
        if el.name == "hr":
            # Separator — flush current block
            if current_block:
                blocks.append(" ".join(current_block))
                current_block = []
            continue

        text = _normalize_text(el)
        if not text:
            continue

        # Check for *** or ——— text separators (sometimes rendered as text, not <hr>)
        if re.match(r'^[\*\-–—\s]{3,}$', text) or text.strip() in ("***", "* * *", "---"):
            if current_block:
                blocks.append(" ".join(current_block))
                current_block = []
            continue

        # Skip headings but use them as separators
        if el.name in ("h2", "h3", "h4"):
            if current_block:
                blocks.append(" ".join(current_block))
                current_block = []
            continue

        current_block.append(text)

    # Flush remaining
    if current_block:
        blocks.append(" ".join(current_block))

    return blocks


def is_international(text):
    """Check if a deal block describes an international (non-US) deal."""
    t = text.lower()
    for kw in INTERNATIONAL_KEYWORDS:
        if kw in t:
            return True
    return False


def is_credit_news(text):
    """Check if a deal block is about credit/debt/ratings, not an actual deal."""
    t = text.lower()
    for kw in CREDIT_KEYWORDS:
        if kw in t:
            return True
    return False


def is_deal_block(text):
    """Check if a text block actually describes a deal/acquisition."""
    t = text.lower()
    deal_verbs = (
        r'\bacquir|\baffilia|\bpartner|\bmerge|\bsale to\b|\bsold to\b|\bsold\b'
        r'|\bwelcom|\bjoined\b|\bopened\b|\bopening\b|\bgrand opening\b'
        r'|\bde novo\b|\bnew location|\bnew office|\bnew practice'
        r'|\badded\b|\bexpand|\bcompleted\b|\bannounced\b'
        r'|\binvest|\bbacked\b|\brecap'
    )
    if not re.search(deal_verbs, t):
        return False
    # Must be longer than a tiny fragment
    if len(text) < 40:
        return False
    return True


# ── Field Extraction ────────────────────────────────────────────────────────


def extract_platform(text):
    """Find a known platform company in the text."""
    for p in sorted(KNOWN_PLATFORMS, key=len, reverse=True):
        if re.search(re.escape(p), text, re.IGNORECASE):
            return p
    return None


def extract_pe_sponsor(text):
    """Extract PE sponsor from known patterns."""
    # Pattern: "(Sponsor)" in parentheses
    for m in re.finditer(r'\(([^)]{3,60})\)', text):
        candidate = m.group(1).strip()
        sponsor = _match_known_sponsor(candidate)
        if sponsor:
            return sponsor

    # Pattern: "owned by X", "backed by X", "portfolio company of X", "X-backed"
    for pattern in [
        r'owned by\s+([A-Z][A-Za-z\s&\-]+?)(?:[,.\)]|which|that|$)',
        r'backed by\s+([A-Z][A-Za-z\s&\-]+?)(?:[,.\)]|which|that|$)',
        r'([A-Z][A-Za-z\s&\-]+?)-backed\b',
        r'portfolio company of\s+([A-Z][A-Za-z\s&\-]+?)(?:[,.\)]|which|that|$)',
        r'a\s+([A-Z][A-Za-z\s&\-]+?)\s+portfolio\b',
    ]:
        m = re.search(pattern, text)
        if m:
            sponsor = _match_known_sponsor(m.group(1).strip())
            if sponsor:
                return sponsor

    # Brute force: check all known sponsors
    for s in sorted(KNOWN_PE_SPONSORS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(s) + r'\b', text, re.IGNORECASE):
            return s

    return None


def _match_known_sponsor(candidate):
    """Check if candidate matches a known PE sponsor."""
    for s in sorted(KNOWN_PE_SPONSORS, key=len, reverse=True):
        if s.lower() in candidate.lower():
            return s
    return None


def extract_target(text, platform):
    """Try to extract the target practice name."""
    # GDN patterns: "sale to [Platform]" means we want the entity before "sale to"
    # "advised [Target] in its sale"
    for pattern in [
        r'advised\s+([A-Z][A-Za-z\s\'\-&\.]{3,50}?)\s+(?:in its|on its|in the)',
        r'acqui(?:red|sition of)\s+([A-Z][A-Za-z\s\'\-&\.]{3,50}?)(?:\s+in\s|\s+from\s|,|\.|;|\s+and\s|\s+to\s)',
        r'partnership with\s+(?:Dr\.\s+[A-Za-z]+\s+[A-Za-z]+\s+and\s+(?:the\s+)?)?([A-Z][A-Za-z\s\'\-&\.]{3,50}?)(?:\s+team|\s+in\s|,|\.|;)',
        r'affiliated with\s+([A-Z][A-Za-z\s\'\-&\.]{3,50}?)(?:\s+in\s|,|\.|;)',
        r'addition of\s+([A-Z][A-Za-z\s\'\-&\.]{3,50}?)(?:\s+in\s|\s+to\s|,|\.|;)',
        r'welcomed\s+([A-Z][A-Za-z\s\'\-&\.]{3,50}?)(?:\s+as\s|\s+to\s|\s+in\s|,|\.|;)',
        r'merged with\s+([A-Z][A-Za-z\s\'\-&\.]{3,50}?)(?:\s+in\s|,|\.|;)',
        r'sale (?:of|to)\s+(?:[A-Z][A-Za-z\s]+?\s+(?:to|by)\s+)?([A-Z][A-Za-z\s\'\-&\.]{3,50}?)(?:\.|,|;)',
    ]:
        m = re.search(pattern, text)
        if m:
            target = m.group(1).strip().rstrip(".")
            # Don't return the platform as the target
            if platform and target.lower() == platform.lower():
                continue
            # Filter out generic words
            if target.lower() in ("the", "a", "an", "its", "their", "several", "multiple",
                                   "two", "three", "four", "five", "dr", "new"):
                continue
            # Filter out if it matches a known platform (we want the TARGET, not acquirer)
            if any(target.lower() == p.lower() for p in KNOWN_PLATFORMS):
                continue
            return target

    return None


def extract_states(text):
    """Extract state abbreviations from text."""
    states = set()

    # Check for 2-letter state abbreviations
    for m in re.finditer(r'\b([A-Z]{2})\b', text):
        abbrev = m.group(1)
        if abbrev in VALID_STATE_ABBREVS:
            states.add(abbrev)

    # Check for full state names
    t_lower = text.lower()
    for name, abbrev in STATE_MAP.items():
        if re.search(r'\b' + re.escape(name) + r'\b', t_lower):
            states.add(abbrev)

    # Filter false positives
    false_positives = set()
    for s in states:
        if s == "OR" and not re.search(r'\bOregon\b', text, re.IGNORECASE):
            if not re.search(r'\bOR\b(?:\s*,|\s*and\b|\s*-)', text):
                false_positives.add(s)
        if s == "IN" and not re.search(r'\bIndiana\b', text, re.IGNORECASE):
            false_positives.add(s)
        if s == "ME" and not re.search(r'\bMaine\b', text, re.IGNORECASE):
            false_positives.add(s)
        if s == "PA" and not re.search(r'\bPennsylvania\b|\b[A-Z][a-z]+,?\s+PA\b', text, re.IGNORECASE):
            # PA appears in "PA" as abbreviation but could be false positive
            pass  # keep — PA after city name is valid

    states -= false_positives
    return list(states) if states else []


def detect_specialty(text):
    """Detect dental specialty from text."""
    t = text.lower()
    if re.search(r'oral surgery|maxillofacial|oms\b', t):
        return "oral_surgery"
    if re.search(r'orthodont', t):
        return "orthodontics"
    if re.search(r'endodont', t):
        return "endodontics"
    if re.search(r'periodont', t):
        return "periodontics"
    if re.search(r'pediatric dent|pedo|children.s dentistry', t):
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
    if re.search(r'\bde novo\b|\bgrand opening\b|\bnew office\b|\bnew location\b|\bopened\b', t):
        return "de_novo"
    if re.search(r'\bnew platform\b|\bbuyout\b', t):
        return "buyout"
    if re.search(r'\bgrowth\b|\bexpansion capital\b|\binvestment in\b|\bgrowth investment\b', t):
        return "growth"
    if re.search(r'\bpartnership\b|\bpartnered\b|\baffilia', t):
        return "partnership"
    if re.search(r'\bacquir|\badd-on\b|\bsale to\b|\bsold to\b|\bpurchas|\bbought\b|\bmerge', t):
        return "add-on"
    if re.search(r'\bwelcom|\bjoined\b|\baddition of\b|\badded\b', t):
        return "add-on"
    return "add-on"


def extract_num_locations(text):
    """Extract number of locations from text."""
    t = text.lower()
    for pattern in [
        r'(\d+)[- ]location',
        r'(\d+)\s+(?:dental\s+)?(?:locations|offices|practices|clinics)',
        r'(\d+)\s+(?:new\s+)?(?:partner\s+)?practices',
        r'operates\s+(\d+)',
        r'(?:with|across)\s+(?:over\s+|more than\s+)?(\d+)\s+(?:locations|offices|practices)',
    ]:
        m = re.search(pattern, t)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 2000:  # sanity check
                return n
    return None


# ── Deal Parsing ────────────────────────────────────────────────────────────


def parse_deal_block(block, deal_date, source_url):
    """Parse a single deal block into one or more deal dicts."""
    # Skip international
    if is_international(block):
        log.debug("SKIP international: %.100s", block)
        return []

    # Skip credit/debt news
    if is_credit_news(block):
        log.debug("SKIP credit/debt: %.100s", block)
        return []

    # Must look like a deal
    if not is_deal_block(block):
        return []

    platform = extract_platform(block)
    pe_sponsor = extract_pe_sponsor(block)
    target = extract_target(block, platform)
    states = extract_states(block)
    specialty = detect_specialty(block)
    deal_type = detect_deal_type(block, platform)
    num_locations = extract_num_locations(block)

    if not platform and not pe_sponsor and not target:
        log.warning("PARSE FAIL — no platform/sponsor/target: %.200s", block)
        return []

    if not states:
        states = [None]

    deals = []
    for state in states:
        deals.append({
            "deal_date": deal_date,
            "platform_company": platform or "Unknown",
            "pe_sponsor": pe_sponsor,
            "target_name": target,
            "target_state": state,
            "deal_type": deal_type,
            "specialty": specialty,
            "num_locations": num_locations,
            "source": "gdn",
            "source_url": source_url,
            "raw_text": block,
        })
    return deals


# ── Scraper Orchestration ──────────────────────────────────────────────────


def scrape_post(url, title, fallback_date):
    """Scrape a single roundup post. Returns list of deal dicts, or None on fetch failure."""
    soup = fetch_page(url)
    if not soup:
        return None

    # Get date from title (more reliable than fallback)
    page_title = extract_title(soup) or title
    deal_date = extract_deal_date_from_title(page_title) or fallback_date
    if not deal_date:
        log.warning("Could not determine date for %s, using 2020-01-01", url)
        deal_date = date(2020, 1, 1)

    log.info("Post: %s  →  date=%s", page_title, deal_date)

    blocks = extract_deal_blocks(soup)
    log.info("Found %d content blocks on %s", len(blocks), url)

    deals = []
    parse_failures = 0
    for block in blocks:
        try:
            parsed = parse_deal_block(block, deal_date, url)
            deals.extend(parsed)
        except Exception as e:
            log.warning("PARSE ERROR: %.200s — %s", block, e)
            parse_failures += 1

    log.info("Parsed %d deals from %s (parse failures: %d)", len(deals), url, parse_failures)
    return deals


def run(dry_run=False):
    """Main entry point."""
    _t0 = log_scrape_start("gdn_scraper")
    log.info("=" * 60)
    log.info("GDN Scraper starting (dry_run=%s)", dry_run)
    log.info("=" * 60)

    # Step 1: Discover roundup URLs
    roundup_posts = discover_roundup_urls()
    if not roundup_posts:
        log.warning("No roundup posts found. Exiting.")
        return

    # Step 2: Scrape each post
    if not dry_run:
        init_db()
        session = get_session()

    all_deals = []
    pages_success = 0
    pages_failed = 0
    failed_urls = []

    for url, title in roundup_posts:
        log.info("Scraping: %s", url)
        deals = scrape_post(url, title, fallback_date=None)

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
                    num_locations=deal.get("num_locations"),
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
    log.info("GDN SCRAPER SUMMARY")
    log.info("=" * 60)
    log.info("Pages found:            %d", len(roundup_posts))
    log.info("Pages scraped OK:       %d", pages_success)
    log.info("Pages failed:           %d", pages_failed)
    if failed_urls:
        for u in failed_urls:
            log.info("  FAILED: %s", u)
    log.info("Total deal mentions:    %d", len(all_deals))
    if not dry_run:
        log.info("New deals inserted:     %d", new_inserted)
        log.info("Duplicates skipped:     %d", duplicates)
        log_scrape_complete("gdn_scraper", _t0, new_records=new_inserted,
                            summary=f"GDN: {new_inserted} new deals, {duplicates} dupes ({pages_success} pages scraped)",
                            extra={"duplicates": duplicates, "pages_scraped": pages_success, "pages_failed": pages_failed})
    log.info("=" * 60)


def _print_dry_run_table(deals):
    """Print parsed deals as a formatted table."""
    if not deals:
        print("\n  No deals parsed.\n")
        return

    print()
    header = f"{'#':>4}  {'Date':10}  {'Platform':30}  {'PE Sponsor':28}  {'Target':30}  {'ST':2}  {'Type':12}  {'Spec':14}  {'Locs':>4}"
    print(header)
    print("-" * len(header))
    for i, d in enumerate(deals, 1):
        locs = str(d.get("num_locations") or "—")
        print(
            f"{i:>4}  "
            f"{str(d.get('deal_date', '')):10}  "
            f"{(d.get('platform_company') or '?')[:30]:30}  "
            f"{(d.get('pe_sponsor') or '—')[:28]:28}  "
            f"{(d.get('target_name') or '—')[:30]:30}  "
            f"{(d.get('target_state') or '??'):2}  "
            f"{(d.get('deal_type') or '?')[:12]:12}  "
            f"{(d.get('specialty') or '?')[:14]:14}  "
            f"{locs:>4}"
        )
    print(f"\nTotal: {len(deals)} deal(s) parsed\n")


# ── CLI ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape GDN for dental PE deals")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't insert into DB")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
