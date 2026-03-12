#!/usr/bin/env python3
"""Import hand-researched dental practice analyses from the HTML directory file.

Parses analysisData from dental-directory.html, matches practices against
the existing NPPES-sourced practices table, and enriches with verdict
classifications, provider info, and full analysis notes.
"""

import os
import re
import sys
from datetime import date

from rapidfuzz import fuzz

from scrapers.database import (
    Base, Practice, WatchedZip, ZipOverview,
    get_engine, get_session, init_db,
)
from scrapers.logger_config import get_logger

log = get_logger("directory_importer")

HTML_PATH = os.path.expanduser(
    "~/dental-pe-tracker/data/data-axle/dental-directory.html"
)

# ZIPs from directory with city names (for watched_zips insertion)
ZIP_CITIES = {
    "60440": "Bolingbrook", "60517": "Woodridge", "60439": "Lemont",
    "60465": "Worth/Palos Heights", "60441": "Lockport",
    "60516": "Downers Grove", "60491": "Homer Glen", "60448": "Mokena",
    "60526": "La Grange", "60451": "New Lenox", "60446": "Romeoville",
    "60464": "Palos Park",
    "02116": "Boston-South End", "02115": "Boston-Back Bay", "02110": "Boston-Financial District",
    "02118": "Boston-South End", "02127": "South Boston", "02128": "East Boston",
    "02129": "Charlestown", "02130": "Jamaica Plain", "02131": "Roslindale",
    "02132": "West Roxbury", "02134": "Allston", "02135": "Brighton",
    "02138": "Cambridge", "02139": "Cambridge", "02140": "Cambridge",
    "02141": "East Cambridge", "02143": "Somerville", "02144": "Somerville",
    "02445": "Brookline", "02446": "Brookline", "02148": "Malden",
}

ZIP_TO_META = {
    # Chicagoland
    "60491": {"state": "IL", "metro_area": "Chicagoland"},
    "60439": {"state": "IL", "metro_area": "Chicagoland"},
    "60441": {"state": "IL", "metro_area": "Chicagoland"},
    "60540": {"state": "IL", "metro_area": "Chicagoland"},
    "60564": {"state": "IL", "metro_area": "Chicagoland"},
    "60565": {"state": "IL", "metro_area": "Chicagoland"},
    "60563": {"state": "IL", "metro_area": "Chicagoland"},
    "60527": {"state": "IL", "metro_area": "Chicagoland"},
    "60515": {"state": "IL", "metro_area": "Chicagoland"},
    "60516": {"state": "IL", "metro_area": "Chicagoland"},
    "60532": {"state": "IL", "metro_area": "Chicagoland"},
    "60559": {"state": "IL", "metro_area": "Chicagoland"},
    "60514": {"state": "IL", "metro_area": "Chicagoland"},
    "60521": {"state": "IL", "metro_area": "Chicagoland"},
    "60523": {"state": "IL", "metro_area": "Chicagoland"},
    "60148": {"state": "IL", "metro_area": "Chicagoland"},
    "60440": {"state": "IL", "metro_area": "Chicagoland"},
    "60490": {"state": "IL", "metro_area": "Chicagoland"},
    "60504": {"state": "IL", "metro_area": "Chicagoland"},
    "60502": {"state": "IL", "metro_area": "Chicagoland"},
    "60431": {"state": "IL", "metro_area": "Chicagoland"},
    "60435": {"state": "IL", "metro_area": "Chicagoland"},
    "60586": {"state": "IL", "metro_area": "Chicagoland"},
    "60585": {"state": "IL", "metro_area": "Chicagoland"},
    "60503": {"state": "IL", "metro_area": "Chicagoland"},
    "60554": {"state": "IL", "metro_area": "Chicagoland"},
    "60543": {"state": "IL", "metro_area": "Chicagoland"},
    "60560": {"state": "IL", "metro_area": "Chicagoland"},
    # Extra Chicagoland from ZIP_CITIES
    "60517": {"state": "IL", "metro_area": "Chicagoland"},
    "60465": {"state": "IL", "metro_area": "Chicagoland"},
    "60448": {"state": "IL", "metro_area": "Chicagoland"},
    "60526": {"state": "IL", "metro_area": "Chicagoland"},
    "60451": {"state": "IL", "metro_area": "Chicagoland"},
    "60446": {"state": "IL", "metro_area": "Chicagoland"},
    "60464": {"state": "IL", "metro_area": "Chicagoland"},
    # Boston Metro
    "02116": {"state": "MA", "metro_area": "Boston Metro"},
    "02115": {"state": "MA", "metro_area": "Boston Metro"},
    "02110": {"state": "MA", "metro_area": "Boston Metro"},
    "02118": {"state": "MA", "metro_area": "Boston Metro"},
    "02119": {"state": "MA", "metro_area": "Boston Metro"},
    "02120": {"state": "MA", "metro_area": "Boston Metro"},
    "02215": {"state": "MA", "metro_area": "Boston Metro"},
    "02127": {"state": "MA", "metro_area": "Boston Metro"},
    "02128": {"state": "MA", "metro_area": "Boston Metro"},
    "02129": {"state": "MA", "metro_area": "Boston Metro"},
    "02130": {"state": "MA", "metro_area": "Boston Metro"},
    "02131": {"state": "MA", "metro_area": "Boston Metro"},
    "02132": {"state": "MA", "metro_area": "Boston Metro"},
    "02134": {"state": "MA", "metro_area": "Boston Metro"},
    "02135": {"state": "MA", "metro_area": "Boston Metro"},
    "02138": {"state": "MA", "metro_area": "Boston Metro"},
    "02139": {"state": "MA", "metro_area": "Boston Metro"},
    "02140": {"state": "MA", "metro_area": "Boston Metro"},
    "02141": {"state": "MA", "metro_area": "Boston Metro"},
    "02142": {"state": "MA", "metro_area": "Boston Metro"},
    "02143": {"state": "MA", "metro_area": "Boston Metro"},
    "02144": {"state": "MA", "metro_area": "Boston Metro"},
    "02445": {"state": "MA", "metro_area": "Boston Metro"},
    "02446": {"state": "MA", "metro_area": "Boston Metro"},
    "02467": {"state": "MA", "metro_area": "Boston Metro"},
    "02459": {"state": "MA", "metro_area": "Boston Metro"},
    "02458": {"state": "MA", "metro_area": "Boston Metro"},
    "02453": {"state": "MA", "metro_area": "Boston Metro"},
    "02451": {"state": "MA", "metro_area": "Boston Metro"},
    "02148": {"state": "MA", "metro_area": "Boston Metro"},
}


# ── Verdict Classification ────────────────────────────────────────────────


def classify_verdict(verdict_text):
    """Map a VERDICT string to (ownership_status, buyability_tag).

    Returns:
        (ownership_status, buyability_tag) where:
        - ownership_status: independent, dso_affiliated, likely_independent, unknown
        - buyability_tag: acquisition_target, job_target, dead_end, specialist, unknown
    """
    v = verdict_text.lower()

    # DSO / Corporate
    if any(k in v for k in ["corporate dso", "corporate/no equity", "corporate/high-volume",
                             "corporate associate", "mini-chain"]):
        return "dso_affiliated", "dead_end"

    # Dead ends (various)
    if "dead end" in v:
        if any(k in v for k in ["dynasty", "family-locked", "locked dynasty",
                                 "locked family", "family succession",
                                 "internal succession", "succession likely locked"]):
            return "independent", "dead_end"
        if any(k in v for k in ["ghost", "retired", "inactive", "satellite",
                                 "administrative", "non-profit", "public health"]):
            return "unknown", "dead_end"
        if "corporate" in v or "ownership" in v:
            return "dso_affiliated", "dead_end"
        if "specialty" in v or "for gp" in v or "for dental" in v:
            return "independent", "dead_end"
        return "unknown", "dead_end"

    # Acquisition targets
    if any(k in v for k in ["acquisition target", "solo practice target",
                             "primary acquisition", "private practice target",
                             "high-value acquisition", "buyability",
                             "buy-out", "buy-in"]):
        return "likely_independent", "acquisition_target"

    # Specialist
    if "specialist" in v and "referral" in v:
        return "independent", "specialist"
    if "specialist target" in v:
        return "independent", "specialist"

    # Job targets
    if "job target" in v:
        if "dead end" in v or "no equity" in v:
            return "dso_affiliated", "job_target"
        return "likely_independent", "job_target"

    # Private practice peer
    if "peer" in v or "stable private" in v:
        return "independent", "dead_end"

    # Potential corporate
    if "potential corporate" in v:
        return "unknown", "job_target"

    return "unknown", "unknown"


# ── HTML/JS Parsing ───────────────────────────────────────────────────────


def extract_backtick_string(text, start_pos):
    """Extract a backtick-delimited template literal starting at start_pos.
    Returns (content, end_pos) where end_pos is after the closing backtick."""
    if text[start_pos] != '`':
        return None, start_pos
    pos = start_pos + 1
    content = []
    while pos < len(text):
        if text[pos] == '`':
            return ''.join(content), pos + 1
        content.append(text[pos])
        pos += 1
    return ''.join(content), pos


def parse_analysis_data(html_content):
    """Parse the analysisData JavaScript object from HTML.

    Returns: dict of zip_code -> {overview: str, practices: [{name, address, analysis}]}
    """
    # Find the analysisData object
    start_marker = "const analysisData = {"
    start = html_content.find(start_marker)
    if start == -1:
        log.error("Could not find analysisData in HTML")
        return {}

    # Find the end — it's closed by `};` before `const dentalData`
    end_marker = "const dentalData = {"
    end = html_content.find(end_marker, start)
    if end == -1:
        # Try finding closing brace + semicolon after ANALYSIS_PLACEHOLDER
        end = html_content.find("// ANALYSIS_PLACEHOLDER", start)
        if end == -1:
            end = len(html_content)

    js_block = html_content[start + len(start_marker):end]

    result = {}
    pos = 0

    while pos < len(js_block):
        # Find next ZIP key: "60440":
        zip_match = re.search(r'"(\d{5})"\s*:\s*\{', js_block[pos:])
        if not zip_match:
            break

        zip_code = zip_match.group(1)
        block_start = pos + zip_match.end()

        # Find overview backtick string
        overview_idx = js_block.find("overview:", block_start)
        if overview_idx == -1:
            pos = block_start
            continue

        # Find the backtick after "overview:"
        bt_start = js_block.find("`", overview_idx)
        if bt_start == -1:
            pos = block_start
            continue

        overview, after_overview = extract_backtick_string(js_block, bt_start)

        # Find practices array
        practices_idx = js_block.find("practices:", after_overview)
        if practices_idx == -1:
            # ZIP has overview but no practices array — store overview only
            result[zip_code] = {"overview": overview.strip(), "practices": []}
            pos = after_overview
            continue

        # Parse practice entries: {name: "...", address: "...", analysis: `...`}
        practices = []
        scan = practices_idx

        while True:
            # Find next {name:
            name_match = re.search(r'\{name:\s*"([^"]*)"', js_block[scan:])
            if not name_match:
                break

            entry_start = scan + name_match.start()

            # Check we haven't gone past this ZIP's practices block
            # Look for the closing ] of the practices array
            next_zip = re.search(r'"(\d{5})"\s*:\s*\{', js_block[scan + name_match.end():])

            name = name_match.group(1)

            # Find address
            addr_match = re.search(r'address:\s*"([^"]*)"', js_block[scan + name_match.end():])
            if not addr_match:
                break
            address = addr_match.group(1)
            after_addr = scan + name_match.end() + addr_match.end()

            # Find analysis backtick
            analysis_bt = js_block.find("`", after_addr)
            if analysis_bt == -1:
                break

            analysis, after_analysis = extract_backtick_string(js_block, analysis_bt)

            practices.append({
                "name": name,
                "address": address,
                "analysis": analysis.strip() if analysis else "",
            })
            scan = after_analysis

            # Check if we've hit the end of this ZIP's practices array
            # Look ahead for `]` or next ZIP
            remainder = js_block[scan:scan + 50].strip()
            if remainder.startswith('}') or remainder.startswith(']'):
                # Might be end of practices array
                bracket_pos = js_block.find(']', scan)
                if bracket_pos != -1 and bracket_pos < scan + 20:
                    scan = bracket_pos + 1
                    break

        result[zip_code] = {"overview": overview.strip(), "practices": practices}
        pos = scan

    return result


# ── Practice Extraction ───────────────────────────────────────────────────


def extract_providers(analysis_html):
    """Extract provider names from the analysis HTML."""
    match = re.search(r'<strong>Providers?:</strong>\s*(.*?)(?:</p>|<br)', analysis_html)
    if not match:
        return []
    raw = match.group(1)
    # Strip HTML tags
    raw = re.sub(r'<[^>]+>', '', raw)
    # Split on commas, strip counts like "(3 listed)"
    raw = re.sub(r'\(\d+\s*listed\)', '', raw)
    providers = [p.strip() for p in raw.split(',') if p.strip()]
    return providers


def extract_verdict(analysis_html):
    """Extract the VERDICT text from the analysis HTML."""
    match = re.search(r'VERDICT:\s*(.*?)(?:</p>|</strong>)', analysis_html)
    if match:
        # Clean HTML tags
        verdict = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        # Remove trailing " —" and everything after
        if ' — ' in verdict:
            verdict = verdict.split(' — ')[0].strip()
        return verdict
    return None


# ── DB Matching ───────────────────────────────────────────────────────────


def fuzzy_match_practice(practice_entry, db_practices, zip_code):
    """Try to match a directory practice against existing DB practices in the same ZIP.

    Returns: matched Practice object or None.
    """
    name = practice_entry["name"]
    address = practice_entry["address"]

    best_match = None
    best_score = 0

    for p in db_practices:
        # Address match (most reliable)
        if p.address and address:
            addr_score = fuzz.token_sort_ratio(
                address.lower(), p.address.lower()
            )
            if addr_score >= 80:
                # Good address match — boost with name if available
                name_score = 0
                if p.practice_name:
                    name_score = fuzz.token_sort_ratio(name.lower(), p.practice_name.lower())
                elif p.doing_business_as:
                    name_score = fuzz.token_sort_ratio(name.lower(), p.doing_business_as.lower())

                combined = addr_score * 0.6 + name_score * 0.4
                if combined > best_score:
                    best_score = combined
                    best_match = p
                continue

        # Name-only match (fallback)
        for db_name in [p.practice_name, p.doing_business_as]:
            if db_name:
                score = fuzz.token_sort_ratio(name.lower(), db_name.lower())
                if score >= 75 and score > best_score:
                    best_score = score
                    best_match = p

    return best_match if best_score >= 50 else None


# ── Main Import ───────────────────────────────────────────────────────────


def run(html_path=None, dry_run=False):
    html_path = html_path or HTML_PATH

    if not os.path.exists(html_path):
        log.error("HTML file not found: %s", html_path)
        print(f"ERROR: File not found: {html_path}")
        return

    log.info("=" * 60)
    log.info("Directory Importer starting")
    log.info("=" * 60)

    # Read and parse
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    data = parse_analysis_data(html)
    if not data:
        print("ERROR: No analysisData found in HTML file.")
        return

    total_practices_parsed = sum(len(d["practices"]) for d in data.values())
    print(f"Parsed {len(data)} ZIP codes, {total_practices_parsed} practice analyses")

    init_db()
    session = get_session()

    # Ensure new columns/tables exist
    engine = get_engine()
    Base.metadata.create_all(engine)

    # Also add notes column if it doesn't exist (ALTER TABLE for existing DBs)
    with engine.connect() as conn:
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE practices ADD COLUMN notes TEXT"
            ))
            conn.commit()
            log.info("Added 'notes' column to practices table")
        except Exception:
            pass  # Column already exists

    stats = {
        "matched": 0, "new": 0, "verdicts": 0,
        "overviews": 0, "zips_added": 0,
    }

    try:
        # ── 1. Store ZIP overviews ──
        for zip_code, zdata in data.items():
            if zdata.get("overview"):
                existing = session.query(ZipOverview).filter_by(zip_code=zip_code).first()
                if existing:
                    existing.overview_html = zdata["overview"]
                else:
                    session.add(ZipOverview(
                        zip_code=zip_code,
                        overview_html=zdata["overview"],
                    ))
                stats["overviews"] += 1

        session.commit()
        print(f"Stored {stats['overviews']} ZIP overviews")

        # ── 2. Add missing ZIPs to watched_zips ──
        existing_zips = {z.zip_code for z in session.query(WatchedZip).all()}
        for zip_code in data.keys():
            if zip_code not in existing_zips:
                city = ZIP_CITIES.get(zip_code, "")
                session.add(WatchedZip(
                    zip_code=zip_code,
                    city=city,
                    state=ZIP_TO_META.get(zip_code, {"state": "IL"})["state"],
                    metro_area=ZIP_TO_META.get(zip_code, {"metro_area": "Chicago"})["metro_area"],
                    notes="Added by directory importer",
                ))
                stats["zips_added"] += 1
                log.info("Added ZIP %s (%s) to watched_zips", zip_code, city)

        session.commit()
        if stats["zips_added"]:
            print(f"Added {stats['zips_added']} new ZIPs to watched_zips")

        # ── 3. Process practices per ZIP ──
        for zip_code, zdata in data.items():
            if not zdata.get("practices"):
                continue

            # Load existing practices for this ZIP
            db_practices = session.query(Practice).filter(Practice.zip == zip_code).all()

            for entry in zdata["practices"]:
                verdict_text = extract_verdict(entry["analysis"])
                providers = extract_providers(entry["analysis"])

                ownership = None
                buyability = None
                if verdict_text:
                    ownership, buyability = classify_verdict(verdict_text)
                    stats["verdicts"] += 1

                # Build notes
                notes_parts = []
                if verdict_text:
                    notes_parts.append(f"VERDICT: {verdict_text}")
                if buyability:
                    notes_parts.append(f"Buyability: {buyability}")
                if providers:
                    notes_parts.append(f"Providers: {', '.join(providers)}")
                notes_parts.append(f"---\n{entry['analysis']}")
                notes_text = "\n".join(notes_parts)

                # Try to match
                match = fuzzy_match_practice(entry, db_practices, zip_code)

                if match:
                    # Update existing practice
                    match.notes = notes_text

                    # Update ownership if our verdict is more specific
                    if ownership and ownership != "unknown":
                        if match.ownership_status in (None, "unknown"):
                            match.ownership_status = ownership
                        elif match.ownership_status == "independent" and ownership == "likely_independent":
                            pass  # Keep more specific "independent"
                        elif match.ownership_status == "likely_independent" and ownership == "dso_affiliated":
                            match.ownership_status = ownership

                    stats["matched"] += 1
                    log.info("Matched: %s -> %s (NPI: %s)", entry["name"], match.practice_name, match.npi)
                else:
                    if dry_run:
                        stats["new"] += 1
                        continue

                    # Insert new practice
                    # Generate a synthetic NPI for non-NPPES practices
                    import hashlib
                    synthetic_npi = "DIR_" + hashlib.md5(
                        f"{zip_code}_{entry['name']}_{entry['address']}".encode()
                    ).hexdigest()[:10]

                    new_practice = Practice(
                        npi=synthetic_npi,
                        practice_name=entry["name"],
                        address=entry["address"],
                        city=ZIP_CITIES.get(zip_code, ""),
                        state=ZIP_TO_META.get(zip_code, {"state": "IL"})["state"],
                        zip=zip_code,
                        ownership_status=ownership or "unknown",
                        notes=notes_text,
                        data_source="manual",
                    )
                    session.add(new_practice)
                    stats["new"] += 1
                    log.info("New practice: %s at %s (%s)", entry["name"], entry["address"], zip_code)

        if not dry_run:
            session.commit()

    finally:
        session.close()

    # Summary
    print()
    print("=" * 50)
    print("DIRECTORY IMPORT SUMMARY")
    print("=" * 50)
    print(f"  ZIP overviews stored:  {stats['overviews']}")
    print(f"  ZIPs added to watch:   {stats['zips_added']}")
    print(f"  Practices matched:     {stats['matched']}")
    print(f"  New practices added:   {stats['new']}")
    print(f"  Verdicts imported:     {stats['verdicts']}")
    print("=" * 50)

    if dry_run:
        print("(DRY RUN — no changes committed)")

    return stats


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
