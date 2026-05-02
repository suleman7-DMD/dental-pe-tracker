"""
Becker's Dental Review Scraper — scrapes beckersdental.com for dental DSO/PE
acquisition and affiliation deal articles, supplementing GDN and PESP.

Becker's publishes individual deal articles (not monthly roundups), so this
scraper crawls category pages for deal-relevant titles, then extracts structured
deal data from each matching article.

Usage:
    python3 scrapers/beckers_scraper.py              # scrape and insert into DB
    python3 scrapers/beckers_scraper.py --dry-run     # parse only, print table
    python3 scrapers/beckers_scraper.py --limit 50    # cap article fetches
    python3 scrapers/beckers_scraper.py --since 2025-01-01  # only articles on/after date
"""

import argparse
import re
import sys
import os
import time
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.database import init_db, get_session, insert_deal, normalize_punctuation, Deal
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

log = get_logger("beckers_scraper")

# ── Constants ────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Category pages to crawl — these contain DSO / dental business news
CATEGORY_URLS = [
    "https://www.beckersdental.com/dso-dpms/",
    "https://www.beckersdental.com/dentists/",
]

MAX_PAGES_PER_CATEGORY = 15   # safety cap per category
MAX_RETRIES = 3
RETRY_BACKOFF = [3, 8, 20]    # seconds between retry attempts
RATE_LIMIT_SECS = 2           # between article fetches
HEAD_RATE_LIMIT_SECS = 0.4    # between HEAD checks on category pages

# Title keywords that signal a deal article (case-insensitive)
DEAL_TITLE_KEYWORDS = [
    "acqui",        # acquires, acquisition, acquired
    "affilia",      # affiliates, affiliated, affiliation
    "partner",      # partners, partnership, partnered
    "merge",        # merges, merged, merger
    "join",         # joins, joined
    "invest",       # invests, investment
    "add",          # adds, adding (for "adds X to network" patterns)
    "expan",        # expands, expansion
    "recapital",    # recapitalization
    "buyout",
    "backed",
    "pe-backed",
    "dso deal",
    "practice deal",
    "dental deal",
    "adds location",
    "adds practice",
    "adds office",
    "grows ",
    "growth",
    "platform",
]

# Title keywords that definitively mean this is NOT a named deal article
# (aggregate count articles, listicles, executive moves, etc.)
SKIP_TITLE_KEYWORDS = [
    " deals in q",
    " deals in 20",
    " deals this ",
    " acquisitions in q",
    " acquisitions in 20",
    " things to know",
    "what to know",
    " reasons ",
    " tips ",
    " trends ",
    " statistics",
    " stats ",
    "top dental companies",
    "top dso",
    "top dental",
    "dental iq",
    "podcast",
    "webinar",
    "sponsored content",
    "survey says",
    " survey:",
    "hire",
    " hired",
    " hires",
    "appoints",
    "appointed",
    " ceo",
    " coo",
    " cfo",
    " cmo",
    "chief ",
    "president",
    "executive director",
    "board of directors",
    "director of",
    "vice president",
    "conference",
    "event ",
    "award",
    "revenue cycle",
    "billing ",
    "dental school",
    "dental student",
    "dental education",
    "research finds",
    " study ",
    "according to",
    " survey ",
    "product launch",
    "technology",
    "new software",
    "app launch",
    "ai tool",
    "new tool",
    " podcast",
    "webcast",
    # Listicle / recap articles with numbered deal summaries (not single deal articles)
    " recap",
    "growth recap",
    "-year growth",
    " year growth",
    "3 moves",
    "5 moves",
    "6 moves",
    "updates:",
    "5 updates",
    "6 updates",
    # Technology / vendor integrations -- not practice acquisitions
    "adds rcm",
    "adds ai",
    "adds software",
    "integration with",
    "adds overjet",
    "adds eaglesoft",
    "adds dentrix",
    "adds carestream",
    # State-by-state / breakdown aggregate articles
    "state-by-state",
    "breakdown",
    "by state",
]

# Heuristic-platform names that are too generic/fragment-like to be reliable.
# The fallback entity extractor can produce these from article section headers.
_HEURISTIC_PLATFORM_REJECTS = frozenset({
    "emerging dso", "new dso", "regional dso", "local dso", "startup dso",
    "dental group", "dental practice", "dental office", "the practice",
    "dental center", "a dental", "independent dental", "private dental",
    "the dso", "the company", "the group",
    "dentist-founded dso", "dentist founded dso",
    "physician-led dso", "physician led dso",
})

# Platforms known to Becker's that may not appear in GDN/PESP lists
KNOWN_PLATFORMS = [
    # From GDN / PESP lists
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
    "Gen4 Dental Partners",
    "Dental Whale", "Shore Dental",
    "Image Specialty Partners", "Mosaic Dental", "Dental Haus",
    "DCA", "Enable Dental", "Great Orthodontics", "Pinnacle Dental Partners",
    "Harmony Dental Partners", "Ascend Dental Solutions",
    "Ideal Dental Management Partners", "Ideal Dental",
    # Additional platforms common in Becker's coverage
    "Dental Power", "Dental Works", "DentalWorks",
    "Aspen Dental Management", "Gentle Dental", "ClearChoice",
    "Dental Care Plus", "Dental Partners",
    "Dental Depot", "Dental Innovations",
    "Smiles Dental", "Smiles for Life", "Smiles4Life",
    "Premier Dental Partners", "Premier Dental Group",
    "Pacific Dental", "Pacific Specialty",
    "Castle Dental", "Coast Dental",
    "Quality Dental", "Quality Care Dental",
    "Dental One", "Dental One Partners",
    "Advanced Dental", "Advanced Dental Specialists",
    "Affordable Dentures", "Affordable Dentures & Implants",
    "Envision Dental", "Envision Oral Care",
    "Greenbrier Dental", "Greenbrier Dental Partners",
    "Nuvia Dental Implant Center", "Nuvia",
    "OrthoFi", "Orthodontic Partners",
    "OrthoAlliance", "Ortho Alliance",
    "Specialty Dental Brands",
    "Western Dental & Orthodontics",
    "Bright Now! Dental", "Bright Now Dental",
    "Kool Smiles", "Kool Smiles Dental",
    "DentaQuest",
    "Dental Care Alliance",
    "NovaBay", "NovaRx",
    "Spring Dental Partners", "Summit Dental Partners",
    "Toothio",
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
    "toronto",
]

CREDIT_KEYWORDS = [
    "s&p global", "s&p rated", "moody's", "fitch", "credit rating",
    "credit facility", "term loan", "revolver",
    "refinanc", "debt ", "bond offering",
    "leverage ratio", "ebitda multiple was",
    "provided financing", "arranging financing",
    "capital structure",
]

# Aggregate count articles — skip these even if they contain a deal verb
AGGREGATE_COUNT_RE = re.compile(
    r'(?:^\d+\+?\s+(?:DSO|dental|practice|acquisition|deal|M&A)|'
    r'^\d+\s+things\s+to\s+know|'
    r'^\d+\s+(?:biggest|top|key|notable|major)\s)',
    re.IGNORECASE,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_text(el):
    """Extract text with spaces between tags, then collapse whitespace."""
    raw = el.get_text(separator=" ")
    return re.sub(r'\s+', ' ', raw).strip()


def _is_deal_title(title):
    """Return True if an article title likely describes a named deal.

    Conservative: requires at least one deal keyword AND no skip keyword.
    The goal is to avoid fetching listicles, executive-hire news, product
    launches, etc. Better to miss 5% of deals than to insert junk.
    """
    t = title.lower()

    # Hard skip: aggregate count format or known non-deal patterns
    if AGGREGATE_COUNT_RE.match(title.strip()):
        return False
    for kw in SKIP_TITLE_KEYWORDS:
        if kw in t:
            return False

    # Require at least one deal-signal keyword
    for kw in DEAL_TITLE_KEYWORDS:
        if kw in t:
            return True

    return False


def is_international(text):
    """Check if article text is about an international (non-US) deal."""
    t = text.lower()
    for kw in INTERNATIONAL_KEYWORDS:
        if kw in t:
            return True
    if re.search(r'\buk\b', t):
        return True
    return False


def is_credit_news(text):
    """Check if article is about financing/credit rather than an actual deal."""
    t = text.lower()
    for kw in CREDIT_KEYWORDS:
        if kw in t:
            return True
    return False


# ── Retry / Fetch ────────────────────────────────────────────────────────────


def _request_with_retry(method, url, **kwargs):
    """Wrap requests with retry logic for transient DNS/connection errors."""
    dns_retry_delays = [1, 3, 10]
    last_exc = None
    for attempt, delay in enumerate([0] + dns_retry_delays):
        if delay:
            log.debug("Retry %d for %s (sleeping %ds)", attempt, url, delay)
            time.sleep(delay)
        try:
            fn = requests.head if method == "head" else requests.get
            return fn(url, **kwargs)
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            err_str = str(e)
            if ("NameResolutionError" in err_str or "Failed to resolve" in err_str
                    or "ConnectionReset" in err_str):
                log.debug("Transient error attempt %d: %s", attempt + 1, err_str[:120])
                continue
            raise
        except requests.RequestException:
            raise
    raise last_exc


def fetch_page(url):
    """Fetch and parse a page. Returns BeautifulSoup or None on failure."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = _request_with_retry("get", url, headers=HEADERS, timeout=(10, 30))
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[attempt]
                log.warning("Fetch attempt %d/%d failed for %s: %s — retrying in %ds",
                            attempt + 1, MAX_RETRIES, url, e, wait)
                time.sleep(wait)
            else:
                log.warning("Failed to fetch %s after %d attempts: %s",
                            url, MAX_RETRIES + 1, e)
    return None


# ── Category Crawl ───────────────────────────────────────────────────────────


def discover_article_urls(since_date=None):
    """Crawl Becker's category pages and return deal-relevant article URLs.

    Returns a list of (url, title, article_date) tuples. ``article_date`` is
    the parsed publish date from the category listing, or None when
    unavailable. ``since_date`` prunes articles published before that date
    to avoid re-processing old articles on incremental runs.
    """
    discovered = []   # list of (url, title, pub_date)
    seen_urls = set()

    for cat_url in CATEGORY_URLS:
        log.info("Crawling category: %s", cat_url)
        page_num = 1

        while page_num <= MAX_PAGES_PER_CATEGORY:
            if page_num == 1:
                page_url = cat_url
            else:
                page_url = f"{cat_url}page/{page_num}/"

            soup = fetch_page(page_url)
            if not soup:
                log.info("Could not fetch %s — stopping pagination", page_url)
                break

            # Becker's uses standard WordPress-style article listing
            articles_on_page = _extract_article_links(soup)
            if not articles_on_page:
                log.info("No articles found on page %d of %s — done", page_num, cat_url)
                break

            new_on_page = 0
            stop_pagination = False

            for url, title, pub_date in articles_on_page:
                if url in seen_urls:
                    continue

                # Date-based pruning for incremental runs
                if since_date and pub_date and pub_date < since_date:
                    log.debug("Stopping pagination: article %s (%s) before since_date %s",
                              url, pub_date, since_date)
                    stop_pagination = True
                    break

                if not _is_deal_title(title):
                    log.debug("SKIP title: %s", title[:80])
                    continue

                seen_urls.add(url)
                discovered.append((url, title, pub_date))
                new_on_page += 1

            log.info("Category page %d: %d candidate articles (+%d new)",
                     page_num, len(articles_on_page), new_on_page)

            if stop_pagination or new_on_page == 0:
                break

            page_num += 1
            time.sleep(RATE_LIMIT_SECS)

    log.info("Total deal-candidate articles discovered: %d", len(discovered))
    return discovered


def _extract_article_links(soup):
    """Extract (url, title, pub_date) tuples from a Becker's category page.

    Becker's uses a WordPress-style layout. Articles appear inside <article>
    tags or <div class="article-item"> / <div class="post"> containers.
    We try multiple selectors for resilience against template changes.
    """
    results = []

    # Strategy 1: <article> tags (standard WordPress)
    for article in soup.find_all("article"):
        link_el = (article.find("h2") or article.find("h3") or article.find("h1"))
        if link_el:
            a = link_el.find("a", href=True)
            if not a:
                a = article.find("a", href=True)
        else:
            a = article.find("a", href=True)

        if not a:
            continue
        href = a.get("href", "").strip()
        title = a.get_text(strip=True)
        if not href or not title:
            continue
        if not href.startswith("http"):
            href = "https://www.beckersdental.com" + href

        # Only accept links to beckersdental.com
        if "beckersdental.com" not in href:
            continue

        pub_date = _extract_pub_date_from_container(article)
        results.append((href, title, pub_date))

    if results:
        return results

    # Strategy 2: look for anchor tags with recognizable patterns in
    # "post" / "article" / "item" class containers
    for container in soup.find_all("div", class_=re.compile(r'post|article|item|entry', re.I)):
        a = container.find("a", href=True)
        if not a:
            continue
        href = a.get("href", "").strip()
        title = a.get_text(strip=True)
        if not href or not title or len(title) < 10:
            continue
        if not href.startswith("http"):
            href = "https://www.beckersdental.com" + href
        if "beckersdental.com" not in href:
            continue
        pub_date = _extract_pub_date_from_container(container)
        results.append((href, title, pub_date))

    return results


def _extract_pub_date_from_container(container):
    """Try to extract a publication date from an article container element."""
    # <time datetime="2025-03-15"> is the canonical source
    time_el = container.find("time")
    if time_el:
        dt_attr = time_el.get("datetime", "")
        d = _parse_date_string(dt_attr)
        if d:
            return d
        d = _parse_date_string(time_el.get_text(strip=True))
        if d:
            return d

    # <span class="date"> or <span class="published"> fallback
    for span in container.find_all("span", class_=re.compile(r'date|publish|time', re.I)):
        d = _parse_date_string(span.get_text(strip=True))
        if d:
            return d

    return None


# ── Article Date Extraction ───────────────────────────────────────────────────


# Month names for date parsing
_MONTH_NAMES = {
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

# Matches "March 15, 2025", "March 2025", "Mar. 15, 2025"
_MONTH_DAY_YEAR_RE = re.compile(
    r'\b(' + "|".join(sorted(_MONTH_NAMES.keys(), key=len, reverse=True)) +
    r')\.?\s+(?:(\d{1,2})(?:st|nd|rd|th)?,?\s+)?(\d{4})\b',
    re.IGNORECASE,
)

# Matches ISO / numeric: 2025-03-15, 2025/03/15, 03/15/2025, 03-15-2025
_ISO_DATE_RE = re.compile(r'\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b')
_US_DATE_RE = re.compile(r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b')


def _parse_date_string(s):
    """Try to parse a date string into a date object. Returns None on failure."""
    if not s:
        return None
    s = s.strip()

    # ISO format: 2025-03-15 or 2025-03-15T12:00:00 (datetime)
    # Strip time component first so the regex works cleanly
    s_date = s.split('T')[0].strip() if 'T' in s else s
    m = _ISO_DATE_RE.search(s_date)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # US format: 03/15/2025
    m = _US_DATE_RE.search(s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    # "March 15, 2025" or "March 2025"
    m = _MONTH_DAY_YEAR_RE.search(s)
    if m:
        month_name = m.group(1).lower().rstrip(".")
        month = _MONTH_NAMES.get(month_name)
        year = int(m.group(3))
        day_str = m.group(2)
        day = int(day_str) if day_str else 1
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    return None


def extract_article_date(soup):
    """Extract publication date from an article page.

    Tries multiple Becker's date locations in order of reliability.
    Returns a date or None.
    """
    # 1. <time datetime="..."> (most reliable)
    time_el = soup.find("time")
    if time_el:
        d = _parse_date_string(time_el.get("datetime", ""))
        if d:
            return d
        d = _parse_date_string(time_el.get_text(strip=True))
        if d:
            return d

    # 2. <meta property="article:published_time"> or <meta name="date">
    for attr in [("property", "article:published_time"), ("name", "date"),
                 ("name", "pubdate"), ("itemprop", "datePublished")]:
        meta = soup.find("meta", {attr[0]: attr[1]})
        if meta and meta.get("content"):
            d = _parse_date_string(meta["content"])
            if d:
                return d

    # 3. JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0] if data else {}
            pub = data.get("datePublished") or data.get("dateCreated")
            if pub:
                d = _parse_date_string(pub)
                if d:
                    return d
        except Exception:
            pass

    # 4. Visible date span / div
    for selector_cls in [r'date|publish|byline|post-date|entry-date|article-date']:
        for el in soup.find_all(class_=re.compile(selector_cls, re.I)):
            d = _parse_date_string(el.get_text(strip=True))
            if d:
                return d

    return None


# ── Field Extraction ─────────────────────────────────────────────────────────


def extract_platform(text):
    """Find a known platform/DSO company in the text.

    Priority: longest match from KNOWN_PLATFORMS first, then heuristic
    fallback for capitalized entity before a deal verb.
    """
    # Longest-first to avoid "PDS" matching before "Pacific Dental Services"
    for p in sorted(KNOWN_PLATFORMS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(p) + r'\b', text, re.IGNORECASE):
            return p

    # Heuristic: capitalized entity at the start of a sentence / block,
    # followed by a deal verb
    _DEAL_VERB_SET = {
        "acquired", "acquires", "acquiring",
        "partnered", "partnering",
        "affiliated", "affiliates",
        "announced", "announces",
        "welcomed", "welcomes",
        "opened", "opens",
        "merged", "merges",
        "expanded", "expands",
        "added", "adds",
        "invested", "invests",
        "joined", "joins",
        "formed", "forms",
        "launched", "launches",
    }
    _AUX_SET = {"has", "have", "had", "is", "are", "was", "were", "will", "would"}
    _PASS_THROUGH_SET = {"&", "and", "of"}

    words = text.split()
    entity_words = []
    i = 0
    while i < len(words):
        w = words[i]
        w_lower = w.lower().rstrip(".,;:")
        if w_lower in _DEAL_VERB_SET:
            break
        if w_lower in _AUX_SET:
            i += 1
            continue
        if entity_words and w_lower in _PASS_THROUGH_SET:
            entity_words.append(w)
            i += 1
            continue
        if w[0].isupper() or w.isupper():
            entity_words.append(w)
            i += 1
        else:
            break

    if len(entity_words) >= 2:
        candidate = " ".join(entity_words).strip()
        # Hard reject: colons or digits suggest article title fragment, not a company name
        if len(candidate) <= 60 and ":" not in candidate and not re.search(r"\d", candidate):
            if candidate.lower() not in _HEURISTIC_PLATFORM_REJECTS:
                log.debug("Fallback platform extracted: %s", candidate)
                return candidate

    return None


def extract_pe_sponsor(text):
    """Extract PE sponsor from known patterns."""
    # "(Sponsor)" in parentheses
    for m in re.finditer(r'\(([^)]{3,60})\)', text):
        candidate = m.group(1).strip()
        for s in sorted(KNOWN_PE_SPONSORS, key=len, reverse=True):
            if s.lower() in candidate.lower():
                return s

    # "owned by X", "backed by X", "portfolio company of X", "X-backed"
    for pattern in [
        r'owned by\s+([A-Z][A-Za-z\s&\-]+?)(?:[,.\)]|which|that|$)',
        r'backed by\s+([A-Z][A-Za-z\s&\-]+?)(?:[,.\)]|which|that|$)',
        r'([A-Z][A-Za-z\s&\-]+?)-backed\b',
        r'portfolio company of\s+([A-Z][A-Za-z\s&\-]+?)(?:[,.\)]|which|that|$)',
        r'a\s+([A-Z][A-Za-z\s&\-]+?)\s+portfolio\b',
    ]:
        m = re.search(pattern, text)
        if m:
            candidate = m.group(1).strip()
            for s in sorted(KNOWN_PE_SPONSORS, key=len, reverse=True):
                if s.lower() in candidate.lower():
                    return s

    # Brute force
    for s in sorted(KNOWN_PE_SPONSORS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(s) + r'\b', text, re.IGNORECASE):
            return s

    return None


def extract_target(text, platform):
    """Try to extract the target practice name from article text.

    Conservative: only extracts when a recognized acquisition pattern matches.
    Returns None rather than guessing to avoid junk insertions.
    """
    # Character class for practice names: letters, digits, spaces, apostrophe,
    # smart quote, hyphen, ampersand, period. Comma excluded (causes over-capture).
    _N = r"A-Za-z0-9\s\'’\-&\."

    _STOP_WORDS = {"which", "located", "headquartered", "based", "situated",
                   "operating", "serving", "providing", "offering", "established",
                   "positioned", "that", "where", "while", "after", "since",
                   "led", "owned", "founded", "managed", "run", "operated"}
    _AUX_WORDS = {"is", "was", "are", "were", "has", "have", "had",
                  "been", "being", "will", "would", "by", "dr", "dr.", "mr.", "ms."}
    _GENERIC = {"the", "a", "an", "its", "their", "several", "multiple",
                "two", "three", "four", "five", "dr", "new"}
    # Terminal connectors that sneak in from list-style articles ("also", "too", "then")
    _TRAILING_JUNK = {"also", "too", "then", "yet", "but", "and", "or",
                      "next", "first", "second", "third"}

    def _clean(raw):
        words = raw.strip().rstrip(".,;").split()
        for i, w in enumerate(words):
            if w.lower().rstrip(".,;") in _STOP_WORDS:
                words = words[:i]
                break
        while words and words[-1].lower().rstrip(".,;") in (_AUX_WORDS | _STOP_WORDS | _TRAILING_JUNK):
            words.pop()
        cleaned = " ".join(words).strip().rstrip(".,;")
        return cleaned if cleaned else None

    # Inverted patterns: "X was acquired by ...", "X has joined ...", "X affiliated with ..."
    inverted = [
        rf'([A-Z][{_N}]{{3,50}}?)\s+was\s+acquired\s+by\s+',
        rf'([A-Z][{_N}]{{3,50}}?)\s+has\s+joined\s+',
        rf'([A-Z][{_N}]{{3,50}}?)\s+affiliated\s+with\s+',
        rf'([A-Z][{_N}]{{3,50}}?),?\s+(?:led by|owned by|founded by).*?(?:has joined|was acquired by)\s+',
    ]
    for pattern in inverted:
        m = re.search(pattern, text)
        if m:
            t = _clean(m.group(1))
            if not t:
                continue
            if platform and t.lower() == platform.lower():
                continue
            if t.lower() in _GENERIC:
                continue
            if any(t.lower() == p.lower() for p in KNOWN_PLATFORMS):
                continue
            # Reject numbered-list artifacts ("Texas. 9. Fife") and junk targets
            if re.search(r"\d+\.", t) or t.lower() in _HEURISTIC_PLATFORM_REJECTS:
                continue
            # Reject single-word targets unless they contain a dental-practice suffix
            # (single capitalized words = city names, not practice names)
            if (len(t.split()) == 1
                    and not re.search(
                        r'dental|orthodont|endodont|periodont|surgery|smiles?|health|care|group',
                        t, re.IGNORECASE)):
                continue
            return t

    # Forward patterns: "acquired X", "partnered with X", "welcomes X", etc.
    forward = [
        rf'acqui(?:red|sition of)\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|\s+from\s|,|\.|;|\s+and\s)',
        rf'partnerships?\s+with\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|,|\.|;|\()',
        rf'affiliated with\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|,|\.|;)',
        rf'addition of\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|\s+to\s|,|\.|;)',
        rf'welcomed?\s+([A-Z][{_N}]{{3,50}}?)(?:\s+as\s|\s+to\s|\s+in\s|,|\.|;)',
        rf'merged with\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|,|\.|;)',
        rf'partnered\s+with:?\s+([A-Z][{_N}]{{3,50}}?)(?:\s+in\s|,|\.|;|\()',
        rf'adds?\s+([A-Z][{_N}]{{3,50}}?)\s+to\s+(?:its\s+)?(?:network|portfolio|platform)',
    ]
    for pattern in forward:
        m = re.search(pattern, text)
        if m:
            t = _clean(m.group(1))
            if not t:
                continue
            if platform and t.lower() == platform.lower():
                continue
            if t.lower() in _GENERIC:
                continue
            if any(t.lower() == p.lower() for p in KNOWN_PLATFORMS):
                continue
            # Reject numbered-list artifacts and junk targets
            if re.search(r"\d+\.", t) or t.lower() in _HEURISTIC_PLATFORM_REJECTS:
                continue
            # Reject single-word targets unless they contain a dental-practice suffix
            if (len(t.split()) == 1
                    and not re.search(
                        r'dental|orthodont|endodont|periodont|surgery|smiles?|health|care|group',
                        t, re.IGNORECASE)):
                continue
            return t

    return None


def extract_state(text):
    """Extract the first plausible US state from article text.

    Returns the state abbreviation string or None. Becker's typically
    mentions city, state for new locations ("in Springfield, IL").
    """
    # City, ST pattern is the most reliable signal
    city_state = re.findall(r'[A-Z][a-z]+,\s*([A-Z]{2})\b', text)
    for abbrev in city_state:
        if abbrev in VALID_STATE_ABBREVS:
            return abbrev

    # Full state name
    t_lower = text.lower()
    for name, abbrev in STATE_MAP.items():
        if re.search(r'\b' + re.escape(name) + r'\b', t_lower):
            # Exclude false-positive single-word states that appear as verbs/prepositions
            if name in ("in", "or", "me"):
                continue
            return abbrev

    # Bare 2-letter abbreviation — only when preceded by a comma
    for m in re.finditer(r',\s*([A-Z]{2})\b', text):
        abbrev = m.group(1)
        if abbrev in VALID_STATE_ABBREVS:
            return abbrev

    return None


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


def detect_deal_type(text):
    """Detect deal type from text."""
    t = text.lower()
    if re.search(r'\brecapital|\brecap\b', t):
        return "recapitalization"
    if re.search(r'\bde novo\b|\bgrand opening\b|\bnew office\b|\bnew location\b|\bopened\b', t):
        return "de_novo"
    if re.search(r'\bnew platform\b|\bbuyout\b', t):
        return "buyout"
    if re.search(r'\bgrowth\b.*\bequity\b|\bgrowth investment\b|\bgrowth capital\b', t):
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
            if 1 <= n <= 2000:
                return n
    return None


# ── Article Parsing ──────────────────────────────────────────────────────────


def _extract_article_body(soup):
    """Extract the main article body text from a Becker's article page."""
    # Try standard content containers in order of specificity
    for selector in [
        {"class": re.compile(r'article-body|article__body|entry-content|post-content|story-body', re.I)},
        {"class": re.compile(r'content-body|main-content|article-content', re.I)},
        {"itemprop": "articleBody"},
    ]:
        el = soup.find(["div", "article", "section"], selector)
        if el:
            return _normalize_text(el)

    # Fallback: collect all paragraph text inside <article> or <main>
    container = soup.find("article") or soup.find("main")
    if container:
        paras = [_normalize_text(p) for p in container.find_all("p")]
        return " ".join(p for p in paras if p)

    # Last resort: all paragraphs
    paras = [_normalize_text(p) for p in soup.find_all("p")]
    return " ".join(p for p in paras if p)


def has_deal_content(text):
    """Check if article body actually contains deal-extraction signals.

    Requires at least one deal verb AND at least one dental keyword.
    Returns False for articles that passed the title filter but whose
    body is editorial commentary without extractable deal facts.
    """
    t = text.lower()
    deal_verb = re.search(
        r'\bacquir|\baffilia|\bpartnered\b|\bmerged\b|\bjoined\b|\bwelcomed\b'
        r'|\binvested\b|\bbacked\b|\brecapital',
        t,
    )
    if not deal_verb:
        return False
    dental = re.search(
        r'\bdental\b|\borthodont|\bendodont|\bperiodont|\boral surgery\b'
        r'|\bprosthodont|\bmaxillofacial\b|\bdso\b',
        t,
    )
    return bool(dental)


def parse_article(url, soup, pub_date):
    """Parse a single Becker's article page into a deal dict (or None).

    Returns a dict with deal fields, or None when the article doesn't
    contain an extractable named deal.
    """
    body = _extract_article_body(soup)
    title_el = soup.find("h1")
    title = _normalize_text(title_el) if title_el else ""

    full_text = (title + " " + body).strip()

    if is_international(full_text):
        log.debug("SKIP international: %s", url)
        return None

    if is_credit_news(full_text):
        log.debug("SKIP credit news: %s", url)
        return None

    if not has_deal_content(full_text):
        log.debug("SKIP no deal content: %s", url)
        return None

    # Extract article date (article page is more reliable than category listing)
    article_date = extract_article_date(soup) or pub_date
    if not article_date:
        log.warning("No date found for %s — skipping", url)
        return None

    platform = normalize_punctuation(extract_platform(full_text))
    pe_sponsor = normalize_punctuation(extract_pe_sponsor(full_text))
    target = normalize_punctuation(extract_target(full_text, platform))
    state = extract_state(full_text)
    specialty = detect_specialty(full_text)
    deal_type = detect_deal_type(full_text)
    num_locations = extract_num_locations(full_text)

    # Require at least a platform OR pe_sponsor to avoid phantom rows
    if not platform and not pe_sponsor:
        log.warning("PARSE FAIL — no platform/sponsor extracted from: %s", url)
        return None

    # Skip if we only have a platform but it's "Unknown" from heuristic
    if not platform and not pe_sponsor:
        return None

    return {
        "deal_date": article_date,
        "platform_company": platform or "Unknown",
        "pe_sponsor": pe_sponsor,
        "target_name": target,
        "target_state": state,
        "deal_type": deal_type,
        "specialty": specialty,
        "num_locations": num_locations,
        "source": "beckers",
        "source_url": url,
        "raw_text": (full_text[:2000] if full_text else None),
    }


# ── Dedup Check ──────────────────────────────────────────────────────────────


def already_in_db(session, deal):
    """Check if a deal already exists from GDN or PESP (cross-source dedup).

    Becker's often reports the same deal that GDN later includes in its monthly
    roundup. We do a fuzzy check: same platform + target + date within ±60 days.
    Returns True when a likely duplicate exists in the DB.
    """
    platform = deal.get("platform_company")
    target = deal.get("target_name")
    deal_date = deal.get("deal_date")

    if not platform or not deal_date:
        return False

    from datetime import timedelta
    date_low = deal_date - timedelta(days=60)
    date_high = deal_date + timedelta(days=60)

    query = session.query(Deal).filter(
        Deal.platform_company == platform,
        Deal.deal_date >= date_low,
        Deal.deal_date <= date_high,
    )
    if target:
        query = query.filter(Deal.target_name == target)

    existing = query.first()
    if existing:
        log.debug("Cross-source duplicate: %s / %s (existing source=%s date=%s)",
                  platform, target, existing.source, existing.deal_date)
        return True
    return False


# ── Scraper Orchestration ─────────────────────────────────────────────────────


def run(dry_run=False, limit=None, since_date=None):
    """Main entry point.

    Args:
        dry_run:    If True, parse only and print — don't insert into DB.
        limit:      Max number of articles to fetch (None = no cap).
        since_date: Only process articles on or after this date (date object).
    """
    _t0 = log_scrape_start("beckers_scraper")
    log.info("=" * 60)
    log.info("Becker's Dental Scraper starting (dry_run=%s, limit=%s, since=%s)",
             dry_run, limit, since_date)
    log.info("=" * 60)

    if not dry_run:
        init_db()
    session = get_session() if not dry_run else None

    articles_fetched = 0
    articles_parsed = 0
    new_inserted = 0
    duplicates = 0
    cross_dupes = 0
    parse_failures = 0
    all_deals = []

    try:
        # Step 1: Discover article URLs
        candidates = discover_article_urls(since_date=since_date)
        if not candidates:
            log.warning("No deal-candidate articles found.")
            log_scrape_complete(
                "beckers_scraper", _t0, new_records=0,
                summary="Becker's: No candidate articles found",
            )
            return

        if limit:
            candidates = candidates[:limit]

        log.info("Processing %d candidate articles...", len(candidates))

        # Step 2: Fetch and parse each article
        for url, title, pub_date in candidates:
            log.info("Fetching: %s", url)
            soup = fetch_page(url)
            articles_fetched += 1

            if not soup:
                log.warning("Failed to fetch article: %s", url)
                parse_failures += 1
                time.sleep(RATE_LIMIT_SECS)
                continue

            try:
                deal = parse_article(url, soup, pub_date)
            except Exception as e:
                log.warning("PARSE ERROR on %s: %s", url, e)
                parse_failures += 1
                time.sleep(RATE_LIMIT_SECS)
                continue

            if deal is None:
                log.debug("No deal extracted from: %s", url)
                time.sleep(RATE_LIMIT_SECS)
                continue

            articles_parsed += 1
            all_deals.append(deal)

            log.info("PARSED: platform=%s target=%s date=%s state=%s",
                     deal.get("platform_company"),
                     deal.get("target_name") or "—",
                     deal.get("deal_date"),
                     deal.get("target_state") or "—")

            time.sleep(RATE_LIMIT_SECS)

        # Step 3: Insert or print
        if dry_run:
            _print_dry_run_table(all_deals)
        else:
            for deal in all_deals:
                # Cross-source dedup (avoid double-inserting GDN/PESP deals)
                if already_in_db(session, deal):
                    cross_dupes += 1
                    log.debug("Cross-source skip: %s / %s",
                              deal.get("platform_company"), deal.get("target_name"))
                    continue

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
                    log.error("Insert error for %s: %s", deal.get("source_url"), e)

        # Step 4: Summary
        log.info("")
        log.info("=" * 60)
        log.info("BECKER'S SCRAPER SUMMARY")
        log.info("=" * 60)
        log.info("Candidate articles:       %d", len(candidates))
        log.info("Articles fetched:         %d", articles_fetched)
        log.info("Articles with deals:      %d", articles_parsed)
        log.info("Parse failures:           %d", parse_failures)
        if not dry_run:
            log.info("Cross-source dupes:       %d", cross_dupes)
            log.info("New deals inserted:       %d", new_inserted)
            log.info("Same-source dupes:        %d", duplicates)
            log_scrape_complete(
                "beckers_scraper", _t0,
                new_records=new_inserted,
                summary=(
                    f"Becker's: {new_inserted} new deals, "
                    f"{duplicates + cross_dupes} dupes skipped "
                    f"({articles_fetched} articles fetched)"
                ),
                extra={
                    "articles_fetched": articles_fetched,
                    "articles_parsed": articles_parsed,
                    "duplicates": duplicates,
                    "cross_source_dupes": cross_dupes,
                    "parse_failures": parse_failures,
                },
            )
        log.info("=" * 60)

    except Exception as e:
        log.error("Becker's scraper fatal error: %s", e)
        log_scrape_error("beckers_scraper", str(e), _t0)
        raise
    finally:
        if session:
            session.close()


def _print_dry_run_table(deals):
    """Print parsed deals as a formatted table."""
    if not deals:
        print("\n  No deals parsed.\n")
        return

    print()
    header = (
        f"{'#':>4}  {'Date':10}  {'Platform':30}  {'PE Sponsor':24}  "
        f"{'Target':30}  {'ST':2}  {'Type':12}  {'Spec':14}  {'Locs':>4}"
    )
    print(header)
    print("-" * len(header))
    for i, d in enumerate(deals, 1):
        locs = str(d.get("num_locations") or "—")
        print(
            f"{i:>4}  "
            f"{str(d.get('deal_date', '')):10}  "
            f"{(d.get('platform_company') or '?')[:30]:30}  "
            f"{(d.get('pe_sponsor') or '—')[:24]:24}  "
            f"{(d.get('target_name') or '—')[:30]:30}  "
            f"{(d.get('target_state') or '??'):2}  "
            f"{(d.get('deal_type') or '?')[:12]:12}  "
            f"{(d.get('specialty') or '?')[:14]:14}  "
            f"{locs:>4}"
        )
    print(f"\nTotal: {len(deals)} deal(s) parsed\n")


# ── CLI ──────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Becker's Dental Review for dental PE/DSO deals"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse only, don't insert into DB")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap the number of articles to fetch")
    parser.add_argument("--since", type=str, default=None,
                        help="Only process articles on or after YYYY-MM-DD")
    args = parser.parse_args()

    since = None
    if args.since:
        try:
            since = date.fromisoformat(args.since)
        except ValueError:
            print(f"ERROR: --since must be YYYY-MM-DD, got: {args.since}")
            sys.exit(1)

    run(dry_run=args.dry_run, limit=args.limit, since_date=since)
