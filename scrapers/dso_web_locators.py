"""Scrape REAL Illinois DSO office addresses from each DSO's own public locator.

Zero-fabrication: every address comes from the DSO's own website (or its
store-locator JSON API). This catches the corporate locations that NPPES
brand-matching misses — the friendly-named practices a DSO operates under a
local brand (Heartland, Great Lakes, Elite, etc.) still list real addresses on
the parent's "our locations" page, and the brand-forward chains (Aspen,
Affordable Dentures, Dental Dreams, Midwest) publish their full office list.

Three generic extraction prongs, unioned per site:
  A. store-locator JSON API captured off the network (Aspen BFF, Affordable API)
  B. schema.org JSON-LD  Dentist / LocalBusiness / PostalAddress blocks
  C. rendered-DOM regex for "<street>, <City>, IL <zip>" address cards

Per-DSO config lists brand + pe_sponsor + entry URL(s) + method. Results are
deduped within a DSO by normalized address, filtered to Illinois, and written
to data/dso_research/il_dso_web_locations.json for the downstream seeder.

Honesty rules:
  - pe_sponsor is only set when the research evidence file confirms it.
  - approx counts from research are NOT used — only addresses we actually parse.
  - per-DSO failures are logged, never silently dropped (no fake coverage).
"""
import json
import re
import sys
import time
from collections import defaultdict

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

OUT = "data/dso_research/il_dso_web_locations.json"

# IL ZIP range is 60001-62999.
# Combined single-line "<street>, <City>, IL <zip>" (commas present).
IL_ADDR_RE = re.compile(
    r"(\d{2,6}\s+[A-Za-z0-9 .'#&/-]{3,55}?),\s*"   # street
    r"([A-Za-z .'-]{2,30}),\s*"                      # city
    r"(?:IL|Illinois)\.?\s+"                          # state
    r"(6[0-2]\d{3})(?:-\d{4})?",                      # IL zip5
)
# Comma-free single line "<street> <City> IL <zip>" (Dental Dreams style):
# grab the whole "<number> ... " blob before " IL <zip>", split street/city after.
IL_BLOB_RE = re.compile(
    r"(\d{1,6}\s+[A-Za-z0-9 .,'#&/-]{5,75}?)\s+"
    r"(?:IL|Illinois)\.?\s+(6[0-2]\d{3})(?:-\d{4})?\b",
)
# A "City, IL zip" line whose street sits on the PRECEDING line (Midwest style).
IL_CITYLINE_RE = re.compile(r"^([A-Za-z .'-]{2,30}),\s*(?:IL|Illinois)\.?\s+(6[0-2]\d{3})\b")
STREET_LINE_RE = re.compile(r"^\d{2,6}\s+[A-Za-z0-9][A-Za-z0-9 .'#&/-]{3,55}$")

# Street-type words: city peeling stops when it hits one of these (e.g. the
# token before "Rockford" in "... State Street Rockford" is "Street" -> stop).
_STREET_SUFFIX = {
    "st", "street", "ave", "avenue", "av", "rd", "road", "blvd", "boulevard",
    "dr", "drive", "ln", "lane", "ct", "court", "pl", "place", "pkwy", "parkway",
    "hwy", "highway", "way", "cir", "circle", "ter", "terrace", "trl", "trail",
    "route", "rte", "sq", "square", "loop", "pike", "plaza", "crossing",
    "commons", "expressway", "expy", "row", "run", "path", "walk", "bend",
}


def _split_blob_city(blob):
    """Split a comma-free '<number> <street words> <City>' blob into
    (street, city) by walking capitalized words off the END until we hit a
    token with a digit (e.g. 'Route 50') or a street-type word (e.g. 'Street').
    Handles multi-word cities (Blue Island, Elk Grove Village) without needing
    to know where the street ends. Caps city at 3 words."""
    blob = re.sub(r"\s+", " ", (blob or "")).strip(" ,.")
    # drop inline unit designators ("Suite B", "Ste 200", "#108", "Fl 2") — they
    # sit between street and city and aren't needed for dedup (NPPES omits them).
    blob = re.sub(
        r"\b(?:suite|ste|unit|apt|apartment|fl|floor|bldg|building|room|rm)\b\.?\s*[A-Za-z0-9-]{0,5}",
        " ", blob, flags=re.I)
    blob = re.sub(r"#\s*\w+", " ", blob)
    blob = re.sub(r"\s+", " ", blob).strip(" ,.")
    toks = blob.split(" ")
    city_toks = []
    while toks and len(city_toks) < 3:
        t = toks[-1]
        tl = t.strip(".,").lower()
        if any(ch.isdigit() for ch in t):          # 'Route 50', '#108' -> part of street
            break
        if tl in _STREET_SUFFIX:                     # 'Street', 'Avenue' -> street ends here
            break
        if not re.match(r"^[A-Za-z][A-Za-z.'-]*$", t):
            break
        city_toks.insert(0, toks.pop())
    street = " ".join(toks).strip(" ,.")
    city = " ".join(city_toks).strip(" ,.")
    if not street:                                   # all-words-were-city safety
        return blob, ""
    return street, city


def norm_addr(addr, zip_):
    if not addr:
        return None
    a = addr.lower().strip()
    a = re.sub(r"\b(suite|ste|unit|apt|#|fl|floor|bldg|room|rm)\b.*$", "", a)
    a = re.sub(r"[^\w\s]", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    z = (zip_ or "")[:5]
    return f"{a}|{z}" if a else None


def is_il(rec):
    st = (rec.get("state") or "").upper()
    z = (rec.get("zip") or "")[:5]
    if st in ("IL", "ILLINOIS"):
        return True
    return bool(z) and z.startswith("6") and "60000" <= z <= "62999"


# ---------- Prong B: JSON-LD ----------
def _jsonld_records(html):
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
                         html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue

        def walk(o):
            if isinstance(o, dict):
                t = o.get("@type", "")
                ts = t if isinstance(t, str) else " ".join(t) if isinstance(t, list) else ""
                addr = o.get("address")
                if isinstance(addr, dict) and addr.get("streetAddress"):
                    out.append({
                        "name": o.get("name"),
                        "street": addr.get("streetAddress"),
                        "city": addr.get("addressLocality"),
                        "state": addr.get("addressRegion"),
                        "zip": addr.get("postalCode"),
                        "phone": o.get("telephone") or addr.get("telephone"),
                    })
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
    return out


# ---------- Prong C: DOM regex (3 layouts) ----------
def _dom_records(text):
    out = []
    seen = set()

    def add(street, city, z):
        street = re.sub(r"\s+", " ", (street or "")).strip(" ,.")
        city = re.sub(r"\s+", " ", (city or "")).strip(" ,.")
        if not street or not z:
            return
        key = (street.lower(), z)
        if key in seen:
            return
        seen.add(key)
        out.append({"name": None, "street": street, "city": city,
                    "state": "IL", "zip": z, "phone": None})

    # 1. combined "<street>, <City>, IL <zip>"
    for street, city, z in IL_ADDR_RE.findall(text):
        add(street, city, z)
    # 2. comma-free "<street> <City> IL <zip>" (whole blob, then peel city)
    for blob, z in IL_BLOB_RE.findall(text):
        s, ci = _split_blob_city(blob)
        add(s, ci, z)
    # 3. two-line: street on line N, "City, IL zip" on line N+1
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        m = IL_CITYLINE_RE.match(ln)
        if m and i > 0 and STREET_LINE_RE.match(lines[i - 1]):
            add(lines[i - 1], m.group(1), m.group(2))
    return out


# ---------- Prong A: special API handlers ----------
# Aspen's locator pages call a geolocation-parameterized GraphQL BFF; in a
# headless browser geolocation is denied so it defaults to Fort Myers FL,
# returning 0 IL offices. Fix: POST the same query directly across an IL
# coordinate grid (50-mi radius circles blanketing the state), dedup by id.
ASPEN_BFF_QUERY = (
    "query bffNearByFacilitiesByLocation($brand: BffBrandType!, $latitude: Float!, "
    "$longitude: Float!, $fetchAllIfNoResults: Boolean, $radiusMiles: Int, "
    "$maxItems: Int) {\n  facilityByLocation(brand: $brand, latitude: $latitude, "
    "longitude: $longitude, fetchAllIfNoResults: $fetchAllIfNoResults, "
    "radiusMiles: $radiusMiles, maxItems: $maxItems) {\n    name\n    displayName\n"
    "    id\n    phoneNumber\n    address { address1 address2 city stateCode zipCode }\n"
    "  }\n}"
)
# ~22 points × 50-mi radius blanket all of Illinois (dense in Chicagoland).
IL_GRID = [
    (41.8781, -87.6298), (42.36, -87.84), (42.03, -88.08), (41.76, -88.15),
    (41.52, -88.08), (41.51, -87.63), (41.93, -88.75), (41.12, -87.86),
    (42.27, -89.09), (41.51, -90.52), (40.95, -90.37), (40.69, -89.59),
    (40.48, -88.99), (40.11, -88.24), (39.84, -88.95), (39.80, -89.64),
    (39.94, -91.41), (39.12, -88.55), (38.52, -89.98), (38.32, -88.90),
    (37.73, -89.22), (37.00, -89.18),
]


def _aspen(page, ctx, cfg):
    """POST the facility-by-location BFF query across an IL coordinate grid."""
    # establish session/cookies on the real domain first
    page.goto(cfg["entry"][0], wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
    recs, seen_ids = [], set()
    for lat, lng in IL_GRID:
        payload = {"operationName": "bffNearByFacilitiesByLocation",
                   "query": ASPEN_BFF_QUERY,
                   "variables": {"brand": "ASPEN_DENTAL", "latitude": lat,
                                 "longitude": lng, "fetchAllIfNoResults": False,
                                 "radiusMiles": 50, "maxItems": 1000}}
        try:
            resp = ctx.request.post(
                "https://www.aspendental.com/api/bff", data=payload,
                headers={"content-type": "application/json",
                         "referer": "https://www.aspendental.com/dentist/il/"},
                timeout=30000)
            fac = (resp.json().get("data", {}) or {}).get("facilityByLocation", []) or []
        except Exception as e:
            print(f"    [aspen grid {lat},{lng}] {type(e).__name__}")
            continue
        for f in fac:
            a = f.get("address") or {}
            if (a.get("stateCode") or "").upper() != "IL":
                continue
            fid = f.get("id")
            if fid and fid in seen_ids:
                continue
            if fid:
                seen_ids.add(fid)
            recs.append({"name": f.get("displayName") or f.get("name"),
                         "street": a.get("address1"), "city": a.get("city"),
                         "state": "IL", "zip": a.get("zipCode"),
                         "phone": f.get("phoneNumber")})
    return recs


def _affordable(page, ctx, cfg):
    bodies = []
    page.on("response",
            lambda r: bodies.append(r) if "affordabledentures.com/api/practices/details" in r.url else None)
    try:
        page.goto(cfg["entry"][0], wait_until="networkidle", timeout=40000)
    except Exception:
        page.wait_for_timeout(3000)
    page.wait_for_timeout(1500)
    recs = []
    for r in bodies:
        try:
            det = json.loads(r.text()).get("details", [])
        except Exception:
            continue
        for o in det:
            recs.append({"name": o.get("name"), "street": o.get("streetAddress"),
                         "city": o.get("city"),
                         "state": o.get("state") or o.get("stateCode"),
                         "zip": o.get("zipCode"), "phone": o.get("phoneNumber")})
    return recs


SPECIAL = {"aspen_bff": _aspen, "affordable_api": _affordable}


# ---------- per-DSO config ----------
# pe_sponsor verified from data/dso_research/il_dso_enumeration + cluster files.
DSOS = [
    {"brand": "Aspen Dental", "pe_sponsor": "American Securities / Ares / Leonard Green",
     "method": "aspen_bff", "entry": ["https://www.aspendental.com/dentist/il/"]},
    {"brand": "Affordable Dentures & Implants", "pe_sponsor": "Harvest Partners",
     "method": "affordable_api", "entry": ["https://www.affordabledentures.com/locations/il"]},
    {"brand": "Dental Dreams", "pe_sponsor": None, "method": "generic",
     "entry": ["https://www.dentaldreams.com/location_group/illinois/"]},
    {"brand": "Familia Dental", "pe_sponsor": "Halifax Group", "method": "generic",
     "entry": ["https://www.familiadental.com/locations/illinois/",
               "https://familiadental.com/locations/"]},
    {"brand": "Midwest Dental", "pe_sponsor": "Gryphon Investors", "method": "generic",
     "entry": ["https://midwest-dental.com/dentist-near-me/find-office/state/il/"]},
    {"brand": "1st Family Dental", "pe_sponsor": None, "method": "generic",
     "entry": ["https://1stfamilydental.com/locations/"]},
    {"brand": "Webster Dental Care", "pe_sponsor": None, "method": "generic",
     "entry": ["https://www.webdentalchicago.com/locations/"]},
    {"brand": "Dentologie", "pe_sponsor": "Beringea / Flyover (growth equity)", "method": "generic",
     "entry": ["https://dentologie.com/our-locations/chicago"]},
    {"brand": "Grand Dental Group", "pe_sponsor": None, "method": "generic",
     "entry": ["https://www.granddentalgroup.com/locations/",
               "https://www.granddentalgroup.com/"]},
    {"brand": "Dental 360", "pe_sponsor": None, "method": "generic",
     "entry": ["https://dental360grp.com/illinois-locations/",
               "https://dental360grp.com/locations/"]},
    {"brand": "Great Lakes Dental Partners", "pe_sponsor": "Shore Capital Partners", "method": "generic",
     "entry": ["https://www.greatlakesdentalpartners.com/company/locations/"]},
    {"brand": "Elite Dental Partners", "pe_sponsor": "Cressey & Company", "method": "generic",
     "entry": ["https://www.elitedentalpartners.com/practice-directory/illinois/"]},
    {"brand": "All Family Dental & Braces (United Dental Partners)", "pe_sponsor": "Calera Capital",
     "method": "generic", "entry": ["https://www.uniteddentalpartners.com/locations/",
                                     "https://allfamilydental.com/locations/"]},
    {"brand": "Destiny Dental (ProSmile)", "pe_sponsor": "TriSpan LLP", "method": "generic",
     "entry": ["https://destinydentalcare.com/illinois/"]},
    {"brand": "Smile Doctors", "pe_sponsor": "Thomas H. Lee / Linden Capital", "method": "generic",
     "entry": ["https://smiledoctors.com/united-states/il/"]},
    {"brand": "Specialized Dental Partners", "pe_sponsor": "Quad-C Management", "method": "generic",
     "entry": ["https://specializeddental.com/locations/"]},
]


SUBPAGE_HREF_RE = re.compile(
    r'/(?:location|locations|office|dental-office|dentist|our-locations|find-office)/[a-z0-9][a-z0-9\-/]{2,}',
    re.I)
MAX_SUBPAGES = 80


def _extract_page(page, url, wait=2800):
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(wait)
    html = page.content()
    try:
        body_txt = page.inner_text("body")
    except Exception:
        body_txt = re.sub(r"<[^>]+>", " ", html)
    recs = _jsonld_records(html) + _dom_records(body_txt) + _dom_records(html)
    return recs, html


def _generic(page, ctx, cfg):
    recs, index_html = [], ""
    for url in cfg["entry"]:
        try:
            r, index_html = _extract_page(page, url)
            recs += r
            if recs:
                break  # first entry URL that yields index-level data wins
        except Exception as e:
            print(f"    [{cfg['brand']}] {url} -> {type(e).__name__}: {str(e)[:60]}")
            try:
                index_html = page.content()
            except Exception:
                index_html = ""

    # If the index page is sparse (JS map widget / streets on sub-pages),
    # crawl per-office sub-pages and extract each one's address.
    if len(recs) < 4 and index_html:
        host = re.match(r'(https?://[^/]+)', cfg["entry"][0]).group(1)
        links = []
        for h in dict.fromkeys(re.findall(r'href="([^"]+)"', index_html)):
            if SUBPAGE_HREF_RE.search(h or ""):
                full = h if h.startswith("http") else host + h
                if full.startswith(host) and full not in links:
                    links.append(full)
        # drop obvious non-office pages
        links = [l for l in links if not re.search(
            r'/(book|appointment|service|es|reviews|about|careers|blog)/', l, re.I)]
        if links:
            print(f"    [{cfg['brand']}] index sparse — drilling {min(len(links), MAX_SUBPAGES)} "
                  f"of {len(links)} sub-pages")
        for link in links[:MAX_SUBPAGES]:
            sp = ctx.new_page()
            try:
                r, _ = _extract_page(sp, link, wait=2000)
                recs += r
            except Exception:
                pass
            finally:
                sp.close()
        if len(links) > MAX_SUBPAGES:
            print(f"    [{cfg['brand']}] NOTE capped at {MAX_SUBPAGES} sub-pages "
                  f"({len(links) - MAX_SUBPAGES} not visited)")
    return recs


def scrape_dso(ctx, cfg):
    page = ctx.new_page()
    try:
        handler = SPECIAL.get(cfg["method"], _generic)
        raw = handler(page, ctx, cfg)
    finally:
        page.close()
    # filter IL + dedup by normalized address
    seen = {}
    for r in raw:
        if not r.get("street") or not is_il(r):
            continue
        k = norm_addr(r["street"], r.get("zip"))
        if not k or k in seen:
            continue
        seen[k] = {
            "dso_name": cfg["brand"], "pe_sponsor": cfg["pe_sponsor"],
            "office_name": r.get("name"), "address": r["street"].strip(),
            "city": (r.get("city") or "").strip(), "state": "IL",
            "zip": (r.get("zip") or "")[:5], "phone": r.get("phone"),
            "source": f"web_locator:{cfg['method']}",
        }
    return list(seen.values())


def main():
    only = set(sys.argv[1:])  # optional: brands to limit to (substring match)
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=UA, locale="en-US", timezone_id="America/Chicago",
            viewport={"width": 1366, "height": 900},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                           "image/avif,image/webp,*/*;q=0.8"),
                "Upgrade-Insecure-Requests": "1",
            })
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        for cfg in DSOS:
            if only and not any(o.lower() in cfg["brand"].lower() for o in only):
                continue
            t0 = time.time()
            try:
                locs = scrape_dso(ctx, cfg)
            except Exception as e:
                print(f"[{cfg['brand']:42}] FAILED {type(e).__name__}: {str(e)[:70]}")
                results[cfg["brand"]] = []
                continue
            results[cfg["brand"]] = locs
            print(f"[{cfg['brand']:42}] {len(locs):>3} IL locations  ({time.time()-t0:.0f}s)")
        browser.close()

    flat = [loc for locs in results.values() for loc in locs]
    with open(OUT, "w") as f:
        json.dump(flat, f, indent=2)
    print(f"\nTotal: {len(flat)} IL DSO web locations from {sum(1 for v in results.values() if v)} "
          f"DSOs -> {OUT}")
    empties = [b for b, v in results.items() if not v]
    if empties:
        print(f"NO DATA (locator changed / anti-bot / no IL): {', '.join(empties)}")


if __name__ == "__main__":
    main()
