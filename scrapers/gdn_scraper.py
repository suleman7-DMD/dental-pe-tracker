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
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.database import init_db, get_session, insert_deal, normalize_punctuation, Deal
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

log = get_logger("gdn_scraper")

# ── Constants ───────────────────────────────────────────────────────────────

HEADERS = {"User-Agent": "DentalPETracker/1.0 (academic research)"}
RATE_LIMIT_SECS = 2
CATEGORY_BASE = "https://www.groupdentistrynow.com/dso-group-blog/category/dso-news/dso-deals/"
MAX_PAGES = 12  # safety cap (7 pages as of 2026-04, extra headroom for growth)
MAX_RETRIES = 3  # retries for transient network errors (e.g. brief DNS blip)
RETRY_BACKOFF = [3, 8, 20]  # seconds between retry attempts

# URLs we know are real roundup posts but that the category crawl misses
# (GDN's category index occasionally drops older posts). Each entry gets a
# HEAD check — 200 means include, non-200 means stale-skip with a warning.
# Keep this list small and deliberate; blanket month enumeration generates
# too many false HEADs for inconsistent slugs.
OVERRIDE_ROUNDUP_URLS: tuple[str, ...] = (
    # Late-2020 / early-2021 quarterly roundups — GDN's category index drops
    # these older posts past page 7. Verified 200 + parses cleanly by
    # _inferred_months (it handles q1/q4 + combined-quarter slugs). Without
    # these, 4 months show false gaps (2020-11, 2020-12, 2021-02, 2021-03)
    # because GDN published quarterly aggregates instead of monthly during
    # the transition period before the dec-2020 → q4-roundup pivot.
    "https://www.groupdentistrynow.com/dso-group-blog/dso-deal-roundup-q1-2021/",
    "https://www.groupdentistrynow.com/dso-group-blog/q4-2020-q1-2021-dso-deals-recent-ma-de-novo-and-pe-activity-roundup/",

    # The bare "/dso-deals/" URL referenced in earlier plan docs was NOT the
    # July-2024 roundup — it 404s today and Wayback shows no archives of that
    # path. Confirmed via 2026-04-23 re-audit that GDN simply did not publish a
    # standalone July 2024 roundup (category pagination walked clean). Kept the
    # tuple here so future slug-less roundups can be pinned without editing the
    # discovery helper.
)

# Earliest month GDN has ever published a DSO deal roundup — used by the
# completeness warning to compute missing-month gaps.
GDN_EARLIEST_YEAR_MONTH = (2020, 10)

# Months where GDN is known not to have published a standalone roundup.
# Verified via category pagination + live HEAD probe during the 2026-04-23
# pipeline audit. Subtracted from the coverage warning so the GATE log ("no
# gaps since 2020-10") is achievable without synthesizing phantom posts.
GDN_EXPECTED_EMPTY_MONTHS = frozenset({
    (2020, 11),  # Rolled into Q4-2020+Q1-2021 combined-quarter roundup (see OVERRIDE_ROUNDUP_URLS). Verified 2026-04-25: HEAD probe of -november-2020 and -nov-2020 slugs both 404; Wayback has no archive.
    (2020, 12),  # Same combined-quarter roundup as 2020-11.
    (2021, 2),   # Rolled into the standalone Q1-2021 roundup (see OVERRIDE_ROUNDUP_URLS). Verified 2026-04-25: HEAD probe of -february-2021 and -feb-2021 slugs both 404; Wayback empty.
    (2021, 3),   # Same Q1-2021 roundup as 2021-02.
    (2024, 7),   # No standalone July 2024 roundup — June and August posts both exist and contain only their own month's deals.
})

# Month-word → number lookup used by _inferred_months (URL + title slug parsing).
# Full names + common abbreviations we have seen in production slugs: "oct",
# "dec", "sept". Keyed lowercase for simple matching.
_MONTH_WORDS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
# Longest-first so "september" wins against "sep" in re.finditer.
_MONTH_RE = re.compile(
    r"(?<![a-z])(" + "|".join(sorted(_MONTH_WORDS, key=len, reverse=True)) + r")[\s\-_]+(20\d{2})(?![0-9])",
    re.IGNORECASE,
)
_Q_RE = re.compile(r"(?<![a-z])q([1-4])[\s\-_]+(20\d{2})(?![0-9])", re.IGNORECASE)
_YEAR_RE = re.compile(r"(?<![0-9])(20\d{2})(?![0-9])")


def _inferred_months(url, title=None):
    """Return the set of (year, month) tuples a roundup URL+title covers.

    Handles:
      - monthly posts ("dso-deal-roundup-january-2023", "dso-deals-oct-2025")
      - single-quarter posts ("q1-2021")
      - combined-quarter posts ("q4-2020-q1-2021-dso-deals…") — BOTH quarters
      - year-in-review / top-10 posts — all 12 months of the year

    Returns an empty set if the URL/title carries no month signal; callers fall
    back to deal_date in that case.
    """
    text = ""
    if url:
        text += url.lower()
    if title:
        text += " " + title.lower()
    covered = set()
    for m in _MONTH_RE.finditer(text):
        covered.add((int(m.group(2)), _MONTH_WORDS[m.group(1).lower()]))
    for m in _Q_RE.finditer(text):
        q, y = int(m.group(1)), int(m.group(2))
        for dm in range(1, 4):
            covered.add((y, (q - 1) * 3 + dm))
    if re.search(r"year[\s\-]?in[\s\-]?review|year[\s\-]?end|top[\s\-]?10[\s\-]?dso", text):
        ym = _YEAR_RE.search(text)
        if ym:
            yy = int(ym.group(1))
            for mm in range(1, 13):
                covered.add((yy, mm))
    return covered

KNOWN_PLATFORMS = [
    "Gen4 Dental Partners",
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
    "toronto",
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

    # Merge in override URLs (posts the category index drops, e.g. the bare
    # /dso-deals/ slug for July 2024). HEAD-check each so we don't cascade
    # bad URLs into downstream parsing.
    existing_urls = {u for u, _ in all_posts}
    override_added = 0
    for override_url in OVERRIDE_ROUNDUP_URLS:
        if override_url in existing_urls:
            continue
        try:
            resp = requests.head(override_url, headers=HEADERS, timeout=15, allow_redirects=True)
            final_url = resp.url or override_url
            if resp.status_code == 200:
                if final_url in existing_urls:
                    log.debug("override redirect already covered: %s -> %s", override_url, final_url)
                    continue
                log.info("FOUND (override): %s", final_url)
                all_posts.append((final_url, ""))  # title will be re-extracted from the page
                existing_urls.add(final_url)
                override_added += 1
            else:
                log.warning("override URL %s returned %d — removing from registry", override_url, resp.status_code)
        except requests.RequestException as e:
            log.warning("override HEAD failed for %s: %s", override_url, e)
    if override_added:
        log.info("override registry: +%d posts", override_added)

    log.info("Total roundup URLs discovered: %d", len(all_posts))
    return all_posts


def _is_roundup_link(href, text):
    """Check if a link is a DSO Deal Roundup post."""
    t = text.lower()
    h = href.lower()
    # Exclude category/pagination index pages — they contain "dso-deals" in the
    # path but are not individual roundup posts.
    if "/category/" in h or re.search(r'/page/\d+/?', h):
        return False
    # Exclude "top 10" year-end listicles BEFORE any title/URL matching,
    # BUT only if they don't also match roundup keywords (e.g.,
    # "Top 10 DSO Deal Roundup Highlights of March 2026" IS a roundup)
    _has_top10 = ("top-10" in h or "top 10" in t or "top-5" in h
                  or "top 5" in t or "best-of" in h or "year-end" in h)
    _roundup_kws = ("roundup" in t or "round-up" in t or "round up" in t
                    or "recap" in t or "deals of" in t
                    or "roundup" in h or "round-up" in h)
    if _has_top10 and not _roundup_kws:
        return False
    # Title-based: must contain "deal roundup" or "dso deal"
    if "deal roundup" in t or "dso deal" in t:
        return True
    # URL-based: common roundup slug patterns
    if re.search(r'dso-deal-roundup|dso-deals|dso-mergers|dso-acquisitions|dental-mergers|dental-acquisitions|dental-business|dso-dental-mergers|dso-and-dental-mergers|q[1-4]-20\d{2}', h):
        return True
    return False


# ── Post Parsing ────────────────────────────────────────────────────────────


_MONTHS_FULL = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Used by per-deal date inference inside Q-roundup / annual posts. Includes
# common abbreviations so blocks like "Feb. 5, 2021" or "in Sept 2025" hit.
MONTH_NAME_TO_NUM = {
    **_MONTHS_FULL,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Match "<Month> <Year>" or "<Month> <Day>, <Year>" — both forms REQUIRE an
# explicit 4-digit year. Bare-month mentions are too noisy (a Q1-2021 block
# saying "ABC closed in March" might mean March 2018 if ABC was founded then).
# The leading word boundary plus optional day/punctuation captures:
#   "January 2021", "Jan 2021", "Jan. 2021", "January, 2021"
#   "January 5, 2021", "Jan 5 2021", "January 5th, 2021"
_BLOCK_DATE_RE = re.compile(
    r'\b(' + "|".join(sorted(MONTH_NAME_TO_NUM.keys(), key=len, reverse=True)) +
    r')\.?\s+(?:(\d{1,2})(?:st|nd|rd|th)?,?\s+)?(\d{4})\b',
    re.IGNORECASE,
)


def extract_deal_date_from_title(title):
    """Extract month/year from a roundup post title like 'DSO Deal Roundup – October 2025'."""
    t = title.lower()

    # Try "month year" pattern
    for name, num in _MONTHS_FULL.items():
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


def extract_post_date_range(title):
    """Return (start_date, end_date) covered by a roundup post's title.

    Used as a guard for per-deal date inference: a block-level "Feb 2021"
    hint is only honored when the post itself covers Feb 2021. Without this
    guard, back-references like "founded January 2010" or "previously
    acquired in 2018" would silently re-date a deal to stale data.

    Returns None when the title carries no derivable date signal — in that
    case the caller stays on whatever fallback_date was supplied.
    """
    t = title.lower()

    for name, num in _MONTHS_FULL.items():
        m = re.search(rf'\b{name}\s+(\d{{4}})\b', t)
        if m:
            year = int(m.group(1))
            start = date(year, num, 1)
            end = (date(year, 12, 31) if num == 12
                   else date(year, num + 1, 1) - timedelta(days=1))
            return (start, end)

    qm = re.search(r'\bq([1-4])\s+(\d{4})\b', t)
    if qm:
        quarter = int(qm.group(1))
        year = int(qm.group(2))
        first_month = (quarter - 1) * 3 + 1
        last_month = first_month + 2
        start = date(year, first_month, 1)
        end = (date(year, 12, 31) if last_month == 12
               else date(year, last_month + 1, 1) - timedelta(days=1))
        return (start, end)

    ym = re.search(r'\b(20\d{2})\b', t)
    if ym:
        year = int(ym.group(1))
        return (date(year, 1, 1), date(year, 12, 31))

    return None


def infer_deal_date_from_block(block, date_range):
    """Look for a month+year date hint inside a single deal block.

    Conservative: only fires on explicit "<Month> <Year>" / "<Month> <Day>,
    <Year>" patterns AND only accepts dates that fall inside the post's
    title-derived window. Returns the FIRST in-window hit, collapsed to the
    1st of that month (matches how monthly posts are dated elsewhere). None
    when no usable hint is present, leaving the caller on the post date.
    """
    if not date_range:
        return None
    start, end = date_range
    for match in _BLOCK_DATE_RE.finditer(block):
        month = MONTH_NAME_TO_NUM.get(match.group(1).lower().rstrip("."))
        if not month:
            continue
        try:
            candidate = date(int(match.group(3)), month, 1)
        except (ValueError, TypeError):
            continue
        if start <= candidate <= end:
            return candidate
    return None


def fetch_page(url):
    """Fetch and parse a page, with retries for transient network errors.

    Returns BeautifulSoup on success, or None after MAX_RETRIES failures.
    All failures are transient (DNS, timeout, connection reset) — permanent
    404s are handled upstream via resp.status_code checks.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=(10, 30))
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[attempt]
                log.warning("Fetch attempt %d/%d failed for %s: %s — retrying in %ds",
                            attempt + 1, MAX_RETRIES, url, e, wait)
                time.sleep(wait)
            else:
                log.warning("Failed to fetch %s after %d attempts: %s", url, MAX_RETRIES + 1, e)
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
    # Track elements already consumed as children of <li> to avoid duplicates
    # (e.g., <li><p>text</p></li> — the <li> handler covers the <p> text)
    seen_elements = set()

    for el in content.find_all(["p", "hr", "h2", "h3", "h4", "li"]):
        if id(el) in seen_elements:
            continue

        if el.name == "hr":
            # Separator — flush current block
            if current_block:
                blocks.append(" ".join(current_block))
                current_block = []
            continue

        # Each <li> is a potential deal — treat as its own block
        if el.name == "li":
            text = _normalize_text(el)
            if text and len(text) > 30:
                if current_block:
                    blocks.append(" ".join(current_block))
                    current_block = []
                current_block.append(text)
            # Mark child p/h2/h3/h4 as seen so they aren't processed again
            for child in el.find_all(["p", "h2", "h3", "h4"]):
                seen_elements.add(id(child))
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

        # Old GDN format (2020-2022): no <hr> separators — deals are
        # individual <p> elements 150+ chars.  Flush the current block
        # before starting a new substantial paragraph so each deal gets
        # its own block instead of being merged into one giant block.
        if (el.name == "p" and len(text) > 150
                and current_block and len(" ".join(current_block)) > 100):
            blocks.append(" ".join(current_block))
            current_block = []

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
    # Word-boundary keywords that would false-positive as substrings
    if re.search(r'\buk\b', t):
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
    """Find a known platform company in the text.

    First checks KNOWN_PLATFORMS list.  Falls back to a heuristic that
    extracts the first capitalized multi-word entity at the start of a
    text block when it is immediately followed by a deal verb.
    """
    for p in sorted(KNOWN_PLATFORMS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(p) + r'\b', text, re.IGNORECASE):
            return p

    # Fallback: word-by-word walk to extract the leading entity before a deal verb.
    # Handles ALL-CAPS names (CORDENTAL, DECA, SIMKO) and auxiliary verbs
    # ("has Partnered", "has been acquired") that precede the deal verb.
    # NOTE: "partners" is intentionally NOT in _DEAL_VERB_SET — it is ambiguous
    # (noun in "Zyphos Dental Partners", verb in "BrandX partners with Y") and
    # handled via a dedicated lookahead below.
    _DEAL_VERB_SET = {
        "acquired", "acquires", "acquiring",
        "partnered", "partnering",
        "affiliated", "affiliates", "affiliating",
        "announced", "announces", "announcing",
        "welcomed", "welcomes", "welcoming",
        "opened", "opens", "opening",
        "merged", "merges", "merging",
        "expanded", "expands", "expanding",
        "added", "adds", "adding",
        "introduced", "introduces", "introducing",
        "completed", "completes", "completing",
        "invested", "invests", "investing",
        "joined", "joins", "joining",
        "formed", "forms", "forming",
        "launched", "launches", "launching",
        "grew", "grows", "growing",
        "celebrated", "celebrates", "celebrating",
        "onboarded", "onboards", "onboarding",
        "continues", "continuing", "continued",
        "strengthens", "strengthening", "strengthened",
        "deepens", "deepening", "deepened",
        "located", "situated", "positioned",
    }
    _PARTNERS_VERB_NEXT = {"with", "to", "and"}
    _AUX_SET = {"has", "have", "had", "is", "are", "was", "were", "will", "would"}
    _TITLE_PREFIXES = {"dr.", "mr.", "ms.", "dr", "mr", "ms"}
    _PASS_THROUGH_SET = {"&", "and", "of"}

    words = text.split()
    entity_words = []
    i = 0
    while i < len(words):
        w = words[i]
        w_lower = w.lower().rstrip(".,;:")

        # "Partners" lookahead: verb iff next token is with/to/and, else
        # treat as a noun and include it in the entity ("Zyphos Dental Partners").
        if w_lower == "partners":
            next_lower = ""
            if i + 1 < len(words):
                next_lower = words[i + 1].lower().rstrip(".,;:")
            if next_lower in _PARTNERS_VERB_NEXT:
                break  # verb sense — stop entity here
            # noun sense — accumulate and continue
            entity_words.append(w)
            i += 1
            continue

        # Stop at deal verb (optionally preceded by auxiliaries)
        if w_lower in _DEAL_VERB_SET:
            break

        # Skip auxiliary verbs mid-stream (e.g. "has Partnered" -> skip "has")
        if w_lower in _AUX_SET:
            i += 1
            continue

        # Skip title prefixes before entity start (Dr., Mr., Ms.)
        if not entity_words and w_lower in _TITLE_PREFIXES:
            i += 1
            continue

        # Pass through connector tokens ("&", "and", "of") when already capturing
        # an entity — handles "Pacific & Western Dental Partners", "Bank of America Dental".
        if entity_words and w_lower in _PASS_THROUGH_SET:
            entity_words.append(w)
            i += 1
            continue

        # Accept words that start with a capital letter OR are all-caps tokens
        # (handles CORDENTAL, DECA, SIMKO, etc.)
        if w[0].isupper() or w.isupper():
            entity_words.append(w)
            i += 1
        else:
            # Lowercase word that is not an aux/verb — entity has ended
            break

    if entity_words:
        candidate = " ".join(entity_words).strip()
        # Must be multi-word; reject single generic words
        if len(entity_words) >= 2 and len(candidate) <= 60:
            log.debug("Fallback platform extracted: %s", candidate)
            return candidate

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
    # Character class for target names: includes apostrophe, smart quote, hyphen, ampersand, period
    _N = r"A-Za-z0-9\s\'\u2019\-&\."

    _TARGET_STOP_WORDS = {"which", "located", "headquartered", "based", "situated",
                          "operating", "serving", "providing", "offering", "established",
                          "positioned", "that", "where", "while", "after", "since",
                          "led", "owned", "founded", "managed", "run", "operated"}
    # Auxiliaries + connectors that legitimately precede a stop word in a relative clause
    # ("X which is located", "Y that has been operating since 1980", "Z which is led by Dr")
    _TARGET_AUX_WORDS = {"is", "was", "are", "were", "has", "have", "had",
                         "been", "being", "will", "would", "by", "dr", "dr.", "mr.", "ms."}

    def _clean_target(raw):
        words = raw.strip().rstrip(".").split()
        while words:
            last = words[-1].lower().rstrip(".,;")
            if last in _TARGET_STOP_WORDS:
                words.pop()
                # Drop trailing auxiliaries that preceded the stop word
                # (e.g. "Bowers ... which is located" → strip "located", then "is", then "which")
                while words and words[-1].lower().rstrip(".,;") in _TARGET_AUX_WORDS:
                    words.pop()
                continue
            # Also strip dangling auxiliaries even without a preceding stop word
            # (e.g. "Heart of Texas Oral Surgery which is led by Dr" — when regex stopped at "Dr")
            if last in _TARGET_AUX_WORDS:
                words.pop()
                continue
            break
        return " ".join(words).strip() if words else None

    _GENERIC_WORDS = {"the", "a", "an", "its", "their", "several", "multiple",
                      "two", "three", "four", "five", "dr", "new"}

    # --- Inverted patterns (target before verb) — check first ---
    inverted_patterns = [
        rf'([A-Z][{_N}]{{3,50}}?)\s+was\s+acquired\s+by\s+',
        rf'([A-Z][{_N}]{{3,50}}?)\s+has\s+joined\s+',
        rf'([A-Z][{_N}]{{3,50}}?)\s+affiliated\s+with\s+',
        rf'([A-Z][{_N}]{{3,50}}?),?\s+(?:led by|owned by|founded by).*?(?:has joined|was acquired by)\s+',
        rf'(?:(?:Advised|Represented|Assisted|Helped|Supported)\s+)?([A-Z][{_N}]{{3,50}}?)\s+(?:in (?:her|his|their) sale)[\s.,;]',
    ]
    for pattern in inverted_patterns:
        m = re.search(pattern, text)
        if m:
            target = _clean_target(m.group(1))
            if not target:
                continue
            if platform and target.lower() == platform.lower():
                continue
            if target.lower() in _GENERIC_WORDS:
                continue
            if any(target.lower() == p.lower() for p in KNOWN_PLATFORMS):
                continue
            return target

    # --- Standard patterns (verb before target) ---
    for pattern in [
        rf'advised\s+([A-Z][{_N}]{{3,50}}?)\s+(?:in its|on its|in the)',
        rf'acqui(?:red|sition of)\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|\s+from\s|,|\.|;|\s+and\s|\s+to\s)',
        rf'acquired:\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|\s+from\s|,|\.|;|\s+and\s|\s+to\s)',
        rf'partnerships?\s+with\s+(?:Dr\.\s+[A-Za-z]+\s+[A-Za-z]+\s+and\s+(?:the\s+)?)?([A-Z][{_N}]{{3,50}}?)(?:\s+team|\s+in\s|,|\.|;|\(|\s+and\s)',
        rf'affiliated with\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|,|\.|;)',
        rf'addition of\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|\s+to\s|,|\.|;)',
        rf'welcomed\s+([A-Z][{_N}]{{3,50}}?)(?:\s+as\s|\s+to\s|\s+in\s|,|\.|;)',
        rf'merged with\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|,|\.|;)',
        rf'sale (?:of|to)\s+(?:[A-Z][{_N}]+?\s+(?:to|by)\s+)?([A-Z][{_N}]{{3,50}}?)(?:\.|,|;)',
        rf'partnered\s+with:?\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|,|\.|;|\()',
        rf'welcomed\s+.*?:\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|,|\.|;|\()',
    ]:
        m = re.search(pattern, text)
        if m:
            target = _clean_target(m.group(1))
            if not target:
                continue
            if platform and target.lower() == platform.lower():
                continue
            if target.lower() in _GENERIC_WORDS:
                continue
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


# ── Coverage diagnostics ────────────────────────────────────────────────────


def _missing_months(session):
    """Return YYYY-MM strings where source='gdn' has no coverage.

    Coverage is computed from source URLs (and, as a fallback, deal_date). This
    matters because the scraper collapses quarterly + combined-quarter posts
    (e.g. ``q4-2020-q1-2021-dso-deals-…``) to a single deal_date, which would
    otherwise show false gaps for the remaining months the post actually covers.

    Gap window: GDN_EARLIEST_YEAR_MONTH (2020-10) through the month BEFORE the
    current month. The current month is excluded because roundups publish late
    in the cycle.
    """
    rows = session.query(Deal.source_url, Deal.deal_date).filter(
        Deal.source == "gdn"
    ).all()

    present: set[tuple[int, int]] = set()
    # url -> set of deal_date months we saw for it (used as fallback when slug
    # has no month signal, e.g. "/dso-deals/").
    url_fallback: dict[str, set[tuple[int, int]]] = {}
    for src_url, dd in rows:
        if src_url:
            inferred = _inferred_months(src_url)
            if inferred:
                present.update(inferred)
            elif dd is not None:
                url_fallback.setdefault(src_url, set()).add((dd.year, dd.month))
        elif dd is not None:
            present.add((dd.year, dd.month))
    for months in url_fallback.values():
        present.update(months)

    today = date.today()
    missing = []
    y, m = GDN_EARLIEST_YEAR_MONTH
    while (y, m) < (today.year, today.month):
        if (y, m) not in present and (y, m) not in GDN_EXPECTED_EMPTY_MONTHS:
            missing.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1
    return missing


def _log_coverage_warning(session):
    """Emit a WARNING if GDN has any unexpected missing months in the 2020-10..today window."""
    try:
        missing = _missing_months(session)
    except Exception as e:
        log.warning("coverage check failed: %s", e)
        return
    if missing:
        log.warning("GDN month coverage gap: missing %s", ", ".join(missing))
    else:
        log.info(
            "GDN month coverage: no unexpected gaps since %04d-%02d (known-empty months suppressed)",
            *GDN_EARLIEST_YEAR_MONTH,
        )


# ── Deal Parsing ────────────────────────────────────────────────────────────


def parse_deal_block(block, deal_date, source_url, date_range=None):
    """Parse a single deal block into one or more deal dicts.

    When `date_range` is provided (set by scrape_post for posts whose title
    yielded a window), each block is scanned for a month+year hint that
    falls inside that window. A hit overrides the post-level deal_date so
    Q-aggregate / annual posts no longer collapse every deal onto the
    first month of the window. Monthly posts pass a single-month window,
    so the override is a no-op there.
    """
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

    platform = normalize_punctuation(extract_platform(block))
    pe_sponsor = normalize_punctuation(extract_pe_sponsor(block))
    target = normalize_punctuation(extract_target(block, platform))
    states = extract_states(block)
    specialty = detect_specialty(block)
    deal_type = detect_deal_type(block, platform)
    num_locations = extract_num_locations(block)

    if not platform and not pe_sponsor and not target:
        log.warning("PARSE FAIL — no platform/sponsor/target: %.200s", block)
        return []

    if not states:
        states = [None]

    inferred = infer_deal_date_from_block(block, date_range)
    if inferred is not None and inferred != deal_date:
        log.info("DATE INFER: %s → %s (post=%s) %.80s",
                 deal_date, inferred, source_url, block)
        deal_date = inferred

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
    date_range = extract_post_date_range(page_title)
    if not deal_date:
        log.warning("Could not determine date for %s, using 2020-01-01", url)
        deal_date = date(2020, 1, 1)

    log.info("Post: %s  →  date=%s range=%s", page_title, deal_date, date_range)

    blocks = extract_deal_blocks(soup)
    log.info("Found %d content blocks on %s", len(blocks), url)

    deals = []
    parse_failures = 0
    no_entity_drops = 0
    inferred_deals = 0
    for block in blocks:
        try:
            parsed = parse_deal_block(block, deal_date, url, date_range=date_range)
            if is_deal_block(block) and not is_international(block) and not is_credit_news(block) and not parsed:
                # Block looked like a deal but was dropped (no platform/sponsor/target)
                no_entity_drops += 1
            for d in parsed:
                if d["deal_date"] != deal_date:
                    inferred_deals += 1
            deals.extend(parsed)
        except Exception as e:
            log.warning("PARSE ERROR: %.200s — %s", block, e)
            parse_failures += 1

    total_drops = parse_failures + no_entity_drops
    log.info("Parsed %d deals from %s (parse failures: %d, no-entity drops: %d, total dropped: %d, date-inferred: %d)",
             len(deals), url, parse_failures, no_entity_drops, total_drops, inferred_deals)
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
        log_scrape_complete("gdn_scraper", _t0, new_records=0, summary="GDN: No roundup posts found")
        return

    # Step 2: Scrape each post
    if not dry_run:
        init_db()
    session = get_session() if not dry_run else None

    all_deals = []
    pages_success = 0
    pages_failed = 0
    failed_urls = []

    try:
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
            _log_coverage_warning(session)
            log_scrape_complete("gdn_scraper", _t0, new_records=new_inserted,
                                summary=f"GDN: {new_inserted} new deals, {duplicates} dupes ({pages_success} pages scraped)",
                                extra={"duplicates": duplicates, "pages_scraped": pages_success, "pages_failed": pages_failed})
        log.info("=" * 60)
    finally:
        if session:
            session.close()


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
