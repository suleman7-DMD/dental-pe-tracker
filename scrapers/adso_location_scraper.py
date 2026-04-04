"""
ADSO Location Scraper — scrapes DSO member websites for office locations,
then matches against NPPES practice data.

Usage:
    python3 scrapers/adso_location_scraper.py                    # scrape all DSOs
    python3 scrapers/adso_location_scraper.py --dso-name "Tend"  # scrape one DSO
    python3 scrapers/adso_location_scraper.py --dry-run           # parse only, no DB writes
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.logger_config import get_logger
from scrapers.database import (
    init_db, get_session, DSOLocation, Practice, PracticeChange,
    insert_or_update_practice, log_practice_change,
)
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

log = get_logger("adso_location_scraper")

HEADERS = {
    "User-Agent": "DentalPETracker/1.0 (academic research)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
JSON_HEADERS = {
    "User-Agent": "DentalPETracker/1.0 (academic research)",
    "Accept": "application/json",
}
RATE_LIMIT_SECS = 3

# ── DSO Registry ───────────────────────────────────────────────────────────
# Each entry: (name, location_url, scrape_method, pe_sponsor, api_url_or_notes)
# scrape_method: "html", "json_api", "needs_browser"

DSO_REGISTRY = [
    {
        "name": "Aspen Dental",
        "url": "https://www.aspendental.com/locations",
        "method": "needs_browser",
        "pe_sponsor": "Ares Management",
        "notes": "JS-rendered location search, API endpoints require session cookies",
    },
    {
        "name": "Heartland Dental",
        "url": "https://www.heartland.com/find-a-dentist",
        "method": "needs_browser",
        "pe_sponsor": "KKR",
        "notes": "JS-rendered location finder, requires Playwright",
    },
    {
        "name": "Pacific Dental Services",
        "url": "https://www.pacificdentalservices.com/our-practices/",
        "method": "needs_browser",
        "pe_sponsor": None,
        "notes": "JS-rendered map, no static location list",
    },
    {
        "name": "MB2 Dental",
        "url": "https://www.mb2dental.com/locations/",
        "method": "needs_browser",
        "pe_sponsor": "Charlesbank Capital Partners",
        "notes": "Location finder uses JS/iframe",
    },
    {
        "name": "Dental365",
        "url": "https://www.dental365.com/locations/",
        "method": "needs_browser",
        "pe_sponsor": "The Jordan Company",
        "notes": "Connection timeout — likely Cloudflare-protected",
    },
    {
        "name": "Specialized Dental Partners",
        "url": "https://www.specializeddental.com/partnership/",
        "method": "needs_browser",
        "pe_sponsor": "Quad-C Management",
        "notes": "Previously html — now returns 404",
    },
    {
        "name": "Great Expressions",
        "url": "https://www.greatexpressions.com/find-a-location/",
        "method": "needs_browser",
        "pe_sponsor": None,
        "notes": "JS-rendered location search",
    },
    {
        "name": "Affordable Care",
        "url": "https://www.affordabledentures.com/find-a-location/",
        "method": "needs_browser",
        "pe_sponsor": None,
        "notes": "API returns 403, needs browser or different auth",
    },
    {
        "name": "Western Dental",
        "url": "https://www.westerndental.com/en-us/find-an-office",
        "method": "needs_browser",
        "pe_sponsor": None,
        "notes": "Sonrava Health — JS search widget",
    },
    {
        "name": "42 North Dental",
        "url": "https://www.42northdental.com/practices/",
        "method": "needs_browser",
        "pe_sponsor": None,
        "notes": "Previously html_subpages — now returns 404",
    },
    {
        "name": "Gentle Dental",
        "url": "https://www.gentledental.com/locations/",
        "method": "html_subpages",
        "pe_sponsor": None,
        "index_url": "https://www.gentledental.com/locations/",
        "link_pattern": r'/dental-offices/',
    },
    {
        "name": "Benevis",
        "url": "https://www.bfranchise.com/locations/",
        "method": "needs_browser",
        "pe_sponsor": None,
        "notes": "Kool Smiles rebranded, location finder is JS",
    },
    {
        "name": "Tend",
        "url": "https://www.hellotend.com/studios",
        "method": "html_subpages",
        "pe_sponsor": None,
        "index_url": "https://www.hellotend.com/studios",
        "link_pattern": r'/studios/',
    },
    {
        "name": "Sage Dental",
        "url": "https://www.mysagedentist.com/locations/",
        "method": "needs_browser",
        "pe_sponsor": "Linden Capital Partners",
        "notes": "Cloudflare 521 error — needs browser",
    },
    {
        "name": "Community Dental Partners",
        "url": "https://www.communitydentalpartners.com/locations/",
        "method": "needs_browser",
        "pe_sponsor": None,
        "notes": "Previously html — now returns 404",
    },
    {
        "name": "Mortenson Dental Partners",
        "url": "https://www.mortensondental.com/our-offices/",
        "method": "needs_browser",
        "pe_sponsor": None,
        "notes": "Previously html — now returns 404",
    },
    {
        "name": "Ideal Dental",
        "url": "https://myidealdental.com/locations/",
        "method": "needs_browser",
        "pe_sponsor": None,
        "notes": "JS-rendered location search",
    },
    {
        "name": "Risas Dental",
        "url": "https://risasdental.com/locations/",
        "method": "html_subpages",
        "pe_sponsor": None,
        "index_url": "https://risasdental.com/locations/",
        "link_pattern": r'/dental-offices/|/locations/[a-z]',
    },
]

# ── Utility ─────────────────────────────────────────────────────────────────


def normalize_zip(z):
    """Extract 5-digit ZIP from various formats."""
    if not z:
        return None
    m = re.search(r'(\d{5})', str(z))
    return m.group(1) if m else None


def normalize_state(s):
    """Normalize state to 2-letter code."""
    if not s:
        return None
    s = s.strip().upper()
    if len(s) == 2:
        return s
    # Try full name
    from scrapers.database import Practice  # avoid circular
    state_map = {
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
    return state_map.get(s.lower())


def parse_address_block(text):
    """Parse a combined address string into components."""
    # Try to match "City, ST ZIP" at the end
    m = re.search(r'([A-Za-z\s\.]+),\s*([A-Z]{2})\s+(\d{5})', text)
    if m:
        city = m.group(1).strip()
        state = m.group(2)
        zipcode = m.group(3)
        # Address is everything before the city match
        addr = text[:m.start()].strip().rstrip(",")
        return addr, city, state, zipcode
    return text, None, None, None


# ── Per-DSO Scrapers ────────────────────────────────────────────────────────


def scrape_html_generic(dso_entry):
    """Generic HTML scraper — tries to find address patterns on a static page."""
    url = dso_entry["url"]
    name = dso_entry["name"]
    locations = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("[%s] Failed to fetch %s: %s", name, url, e)
        return locations

    soup = BeautifulSoup(resp.text, "lxml")

    # Strategy 1: Look for structured location data (schema.org, microdata)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            locs = _extract_from_jsonld(data, name, url)
            if locs:
                locations.extend(locs)
        except (json.JSONDecodeError, TypeError):
            continue

    if locations:
        return locations

    # Strategy 2: Find address elements
    addr_elements = soup.find_all(["address"]) or soup.find_all(class_=re.compile(r'address|location', re.I))
    for el in addr_elements:
        text = re.sub(r'\s+', ' ', el.get_text(separator=" ")).strip()
        if len(text) < 10:
            continue
        addr, city, state, zipcode = parse_address_block(text)
        if state and zipcode:
            locations.append({
                "dso_name": name,
                "location_name": None,
                "address": addr,
                "city": city,
                "state": state,
                "zip": zipcode,
                "phone": None,
                "source_url": url,
            })

    if locations:
        return locations

    # Strategy 3: Regex scan full page text for "City, ST ZIP" patterns
    full_text = soup.get_text(separator="\n")
    for m in re.finditer(r'(\d{1,5}\s+[A-Za-z][^,\n]{3,50}),\s*([A-Za-z\s\.]+),\s*([A-Z]{2})\s+(\d{5})', full_text):
        locations.append({
            "dso_name": name,
            "location_name": None,
            "address": m.group(1).strip(),
            "city": m.group(2).strip(),
            "state": m.group(3),
            "zip": m.group(4),
            "phone": None,
            "source_url": url,
        })

    # Strategy 4: Look for links to individual location pages
    if not locations:
        loc_links = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if re.search(r'/location|/office|/practice|/dentist', href, re.I) and len(text) > 3:
                full_url = urljoin(url, href)
                if full_url not in loc_links:
                    loc_links.append(full_url)

        # Scrape up to 5 location sub-pages to find address patterns
        for sub_url in loc_links[:5]:
            time.sleep(1)
            try:
                sub_resp = requests.get(sub_url, headers=HEADERS, timeout=15)
                sub_soup = BeautifulSoup(sub_resp.text, "lxml")
                sub_text = sub_soup.get_text(separator="\n")
                for m in re.finditer(r'(\d{1,5}\s+[A-Za-z][^,\n]{3,50}),\s*([A-Za-z\s\.]+),\s*([A-Z]{2})\s+(\d{5})', sub_text):
                    locations.append({
                        "dso_name": name,
                        "location_name": None,
                        "address": m.group(1).strip(),
                        "city": m.group(2).strip(),
                        "state": m.group(3),
                        "zip": m.group(4),
                        "phone": None,
                        "source_url": sub_url,
                    })
            except requests.RequestException:
                continue

        if loc_links and not locations:
            log.info("[%s] Found %d location sub-page links but no parseable addresses", name, len(loc_links))

    return locations


def _extract_from_jsonld(data, dso_name, source_url):
    """Extract locations from JSON-LD structured data."""
    locations = []

    if isinstance(data, list):
        for item in data:
            locations.extend(_extract_from_jsonld(item, dso_name, source_url))
        return locations

    if not isinstance(data, dict):
        return locations

    dtype = data.get("@type", "")
    if dtype in ("Dentist", "LocalBusiness", "MedicalBusiness", "DentalClinic", "Place"):
        addr = data.get("address", {})
        if isinstance(addr, dict):
            locations.append({
                "dso_name": dso_name,
                "location_name": data.get("name"),
                "address": addr.get("streetAddress"),
                "city": addr.get("addressLocality"),
                "state": normalize_state(addr.get("addressRegion")),
                "zip": normalize_zip(addr.get("postalCode")),
                "phone": data.get("telephone"),
                "source_url": source_url,
            })

    # Check for nested items (e.g., @graph, itemListElement)
    for key in ("@graph", "itemListElement", "department", "subOrganization"):
        if key in data:
            sub = data[key]
            if isinstance(sub, list):
                for item in sub:
                    if isinstance(item, dict):
                        inner = item.get("item", item)
                        locations.extend(_extract_from_jsonld(inner, dso_name, source_url))

    return locations


def scrape_html_subpages(dso_entry):
    """Scrape by first finding location sub-page links, then visiting each."""
    name = dso_entry["name"]
    index_url = dso_entry.get("index_url", dso_entry["url"])
    link_pattern = dso_entry.get("link_pattern", r'/location')
    locations = []

    try:
        resp = requests.get(index_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("[%s] Failed to fetch index %s: %s", name, index_url, e)
        return locations

    soup = BeautifulSoup(resp.text, "lxml")

    # Collect location sub-page links
    sub_urls = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if re.search(link_pattern, href, re.I):
            full = urljoin(index_url, href)
            # Skip the index page itself and anchors
            if full.rstrip("/") != index_url.rstrip("/") and "#" not in full:
                sub_urls.add(full)

    log.info("[%s] Found %d location sub-page links", name, len(sub_urls))

    # Visit each sub-page (up to 200)
    for i, sub_url in enumerate(sorted(sub_urls)[:200]):
        if i > 0 and i % 10 == 0:
            log.info("[%s] Scraped %d/%d sub-pages...", name, i, len(sub_urls))
        try:
            sub_resp = requests.get(sub_url, headers=HEADERS, timeout=15)
            sub_resp.raise_for_status()
        except requests.RequestException:
            continue

        sub_soup = BeautifulSoup(sub_resp.text, "lxml")

        # Try JSON-LD first
        for script in sub_soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                locs = _extract_from_jsonld(data, name, sub_url)
                if locs:
                    locations.extend(locs)
            except (json.JSONDecodeError, TypeError):
                continue

        # If no JSON-LD, regex for addresses
        if not any(l["source_url"] == sub_url for l in locations):
            text = sub_soup.get_text(separator="\n")
            for m in re.finditer(r'(\d{1,5}\s+[A-Za-z][^,\n]{3,60}),\s*([A-Za-z\s\.]+),\s*([A-Z]{2})\s+(\d{5})', text):
                locations.append({
                    "dso_name": name,
                    "location_name": None,
                    "address": m.group(1).strip(),
                    "city": m.group(2).strip(),
                    "state": m.group(3),
                    "zip": m.group(4),
                    "phone": None,
                    "source_url": sub_url,
                })

            # Also try to find phone
            phone_m = re.search(r'\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}', text)
            if phone_m and locations and locations[-1]["source_url"] == sub_url:
                locations[-1]["phone"] = phone_m.group(0)

        time.sleep(1)  # polite rate limit for sub-pages

    # Deduplicate by address+zip
    seen = set()
    deduped = []
    for loc in locations:
        key = (loc.get("address", ""), loc.get("zip", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(loc)

    return deduped


def scrape_json_api(dso_entry):
    """Scrape from a known JSON API endpoint."""
    name = dso_entry["name"]
    api_url = dso_entry.get("api_url")
    if not api_url:
        log.warning("[%s] No API URL configured", name)
        return []

    locations = []
    try:
        resp = requests.get(api_url, headers=JSON_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        log.warning("[%s] API request failed: %s", name, e)
        return locations
    except json.JSONDecodeError as e:
        log.warning("[%s] Invalid JSON from API: %s", name, e)
        return locations

    # Handle various JSON structures
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Try common wrapper keys
        for key in ("locations", "offices", "results", "data", "practices", "items"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        if not items and "features" in data:
            # GeoJSON format
            items = [f.get("properties", f) for f in data["features"]]

    for item in items:
        if not isinstance(item, dict):
            continue
        # Try multiple field name conventions
        loc = {
            "dso_name": name,
            "location_name": item.get("name") or item.get("title") or item.get("officeName") or item.get("locationName"),
            "address": item.get("address") or item.get("streetAddress") or item.get("address1") or item.get("street"),
            "city": item.get("city") or item.get("addressLocality"),
            "state": normalize_state(item.get("state") or item.get("addressRegion") or item.get("stateCode")),
            "zip": normalize_zip(item.get("zip") or item.get("zipCode") or item.get("postalCode")),
            "phone": item.get("phone") or item.get("telephone") or item.get("phoneNumber"),
            "source_url": api_url,
        }
        # Only add if we have at least state + zip or city
        if loc["state"] and (loc["zip"] or loc["city"]):
            locations.append(loc)

    return locations


# ── Matching Engine ─────────────────────────────────────────────────────────


def match_locations_to_practices(session, locations, dso_entry, dry_run=False):
    """Match scraped DSO locations to NPPES practices."""
    from rapidfuzz import fuzz

    pe_sponsor = dso_entry.get("pe_sponsor")
    dso_name = dso_entry["name"]
    matched = 0
    new_affiliations = 0

    for loc in locations:
        if not loc.get("zip"):
            continue

        # Find practices in the same ZIP
        practices = session.query(Practice).filter_by(zip=loc["zip"]).all()
        if not practices:
            continue

        best_match = None
        best_score = 0

        for practice in practices:
            # Score by address similarity
            if loc.get("address") and practice.address:
                addr_score = fuzz.token_sort_ratio(
                    loc["address"].lower(),
                    practice.address.lower()
                )
                if addr_score >= 80 and addr_score > best_score:
                    # Validate leading street numbers match (different number = different building)
                    p_num = re.match(r'(\d+)', practice.address or '')
                    d_num = re.match(r'(\d+)', loc["address"] or '')
                    if p_num and d_num and p_num.group(1) != d_num.group(1):
                        continue  # Different street number = different building
                    best_match = practice
                    best_score = addr_score

            # Score by name similarity
            if loc.get("location_name") and practice.practice_name:
                name_score = fuzz.token_sort_ratio(
                    loc["location_name"].lower(),
                    practice.practice_name.lower()
                )
                if name_score >= 75 and name_score > best_score:
                    # Validate street numbers match (same check as address path)
                    if loc.get("address") and practice.address:
                        p_num = re.match(r'(\d+)', practice.address or '')
                        d_num = re.match(r'(\d+)', loc["address"] or '')
                        if p_num and d_num and p_num.group(1) != d_num.group(1):
                            continue  # Different street number = different building
                    best_match = practice
                    best_score = name_score

        if best_match:
            matched += 1
            old_status = best_match.ownership_status

            if not dry_run:
                new_status = "pe_backed" if pe_sponsor else "dso_affiliated"
                if old_status in ("independent", "unknown", None):
                    # Check for existing recent change to avoid duplicates on re-runs
                    from scrapers.database import PracticeChange
                    recent_dup = session.query(PracticeChange).filter(
                        PracticeChange.npi == best_match.npi,
                        PracticeChange.field_changed == "ownership_status",
                        PracticeChange.new_value == new_status,
                        PracticeChange.change_date >= date.today() - __import__('datetime').timedelta(days=30),
                    ).first()
                    if not recent_dup:
                        new_affiliations += 1
                        log_practice_change(
                            session,
                            npi=best_match.npi,
                            change_date=date.today(),
                            field_changed="ownership_status",
                            old_value=old_status or "unknown",
                            new_value=new_status,
                            change_type="acquisition",
                            notes=f"Matched to {dso_name} location via address/name (score={best_score})",
                        )

                best_match.ownership_status = new_status
                best_match.affiliated_dso = dso_name
                if pe_sponsor:
                    best_match.affiliated_pe_sponsor = pe_sponsor
                best_match.updated_at = datetime.now()
                session.commit()

            log.debug("MATCH: %s ↔ NPI %s (score=%d)", loc.get("location_name") or loc.get("address"), best_match.npi, best_score)

    return matched, new_affiliations


# ── Main Orchestration ──────────────────────────────────────────────────────


def scrape_dso(dso_entry):
    """Scrape a single DSO. Returns (locations_list, method_used)."""
    name = dso_entry["name"]
    method = dso_entry.get("method", "html")

    if method == "needs_browser":
        log.info("[%s] Needs browser rendering — skipping (add Playwright later)", name)
        return None, "needs_browser"

    log.info("[%s] Scraping via %s: %s", name, method, dso_entry["url"])

    if method == "json_api":
        locations = scrape_json_api(dso_entry)
    elif method == "html_subpages":
        locations = scrape_html_subpages(dso_entry)
    else:
        locations = scrape_html_generic(dso_entry)

    log.info("[%s] Found %d locations", name, len(locations))
    return locations, method


def run(dry_run=False, dso_name_filter=None):
    """Main entry point."""
    _t0 = log_scrape_start("adso_scraper")
    log.info("=" * 60)
    log.info("ADSO Location Scraper starting (dry_run=%s)", dry_run)
    log.info("=" * 60)

    if not dry_run:
        init_db()
    session = get_session() if not dry_run else None

    # Filter DSOs if requested
    dsos_to_scrape = DSO_REGISTRY
    if dso_name_filter:
        dsos_to_scrape = [d for d in DSO_REGISTRY if dso_name_filter.lower() in d["name"].lower()]
        if not dsos_to_scrape:
            log.error("No DSO found matching '%s'", dso_name_filter)
            print(f"Available DSOs: {', '.join(d['name'] for d in DSO_REGISTRY)}")
            return

    # Stats
    total_scraped = 0
    total_skipped = 0
    total_locations = 0
    total_matched = 0
    total_new_affiliations = 0
    needs_browser_list = []

    for dso_entry in dsos_to_scrape:
        locations, method = scrape_dso(dso_entry)

        if method == "needs_browser":
            total_skipped += 1
            needs_browser_list.append(dso_entry)
            continue

        if locations is None:
            locations = []

        total_scraped += 1
        total_locations += len(locations)

        # Store locations in DB (delete existing rows for this DSO first to prevent duplication)
        if not dry_run and locations:
            session.query(DSOLocation).filter_by(dso_name=dso_entry["name"]).delete()
            for loc in locations:
                dso_loc = DSOLocation(
                    dso_name=loc["dso_name"],
                    location_name=loc.get("location_name"),
                    address=loc.get("address"),
                    city=loc.get("city"),
                    state=loc.get("state"),
                    zip=loc.get("zip"),
                    phone=loc.get("phone"),
                    source_url=loc.get("source_url"),
                )
                session.add(dso_loc)
            session.commit()

        # Match against practices
        if not dry_run and locations:
            matched, new_aff = match_locations_to_practices(session, locations, dso_entry, dry_run)
            total_matched += matched
            total_new_affiliations += new_aff
        elif dry_run and locations:
            # Print sample in dry run
            print(f"\n--- {dso_entry['name']} ({len(locations)} locations) ---")
            for loc in locations[:5]:
                print(f"  {loc.get('location_name') or '—':30}  "
                      f"{loc.get('address') or '—':35}  "
                      f"{loc.get('city') or '—':15}  "
                      f"{loc.get('state') or '??':2}  "
                      f"{loc.get('zip') or '—':5}")
            if len(locations) > 5:
                print(f"  ... and {len(locations) - 5} more")

        time.sleep(RATE_LIMIT_SECS)

    # Summary
    print()
    log.info("=" * 60)
    log.info("ADSO LOCATION SCRAPER SUMMARY")
    log.info("=" * 60)
    log.info("DSOs scraped:                 %d/%d", total_scraped, len(dsos_to_scrape))
    log.info("Locations found:              %d total", total_locations)
    if not dry_run:
        log.info("Matched to NPPES practices:   %d", total_matched)
        log.info("New DSO affiliations detected: %d", total_new_affiliations)
    log.info("Skipped (needs browser):      %d DSOs", total_skipped)
    log.info("=" * 60)

    if not dry_run:
        log_scrape_complete("adso_scraper", _t0, new_records=total_locations,
                            updated_records=total_new_affiliations,
                            summary=f"ADSO: {total_locations} locations from {total_scraped} DSOs, {total_new_affiliations} new affiliations, {total_skipped} skipped (needs browser)",
                            extra={"dsos_scraped": total_scraped, "dsos_skipped": total_skipped,
                                   "locations_matched": total_matched})

    if needs_browser_list:
        print("\nDSOs requiring Playwright/browser scraping:")
        for d in needs_browser_list:
            print(f"  - {d['name']:30} {d['url']}")
            if d.get("notes"):
                print(f"    Note: {d['notes']}")

    if session:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape DSO websites for office locations")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    parser.add_argument("--dso-name", type=str, help="Scrape only this DSO (partial name match)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, dso_name_filter=args.dso_name)
