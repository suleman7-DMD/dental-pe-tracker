#!/usr/bin/env python3
"""
Practice-Level Deep Dive

Researches individual dental practices for PE-style due diligence using
Claude API + web search. Stores structured results in the database.

Supports three research modes:
  1. Standard (Haiku) — ~$0.08-0.12/practice, good for screening
  2. Deep (Haiku scan → Sonnet escalation) — ~$0.28/practice for top targets
  3. Batch — 50% off, queue overnight

Usage:
  python3 scrapers/practice_deep_dive.py --npi 1234567890
  python3 scrapers/practice_deep_dive.py --zip 60491 --top 10
  python3 scrapers/practice_deep_dive.py --zip 60491 --solo-established
  python3 scrapers/practice_deep_dive.py --zip 60491 --deep  (two-pass for top targets)
  python3 scrapers/practice_deep_dive.py --batch --metro chicagoland --solo-high-volume
  python3 scrapers/practice_deep_dive.py --status
  python3 scrapers/practice_deep_dive.py --report 1234567890
  python3 scrapers/practice_deep_dive.py --dossier 60491  (all researched practices in ZIP)
"""

import argparse
import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.research_engine import ResearchEngine, CostTracker, MODEL_HAIKU, MODEL_SONNET
from scrapers.intel_database import (
    ensure_intel_tables, store_practice_intel, get_practice_intel,
    is_cache_fresh, get_db_path, DEFAULT_CACHE_TTL_DAYS
)
from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

logger = get_logger("practice_deep_dive")


def get_practices_for_research(db_path=None, zip_code=None, metro=None,
                                entity_types=None, top_n=None,
                                exclude_researched=True):
    """
    Fetch practices from the database for research, with smart prioritization.
    
    Priority order:
    1. solo_high_volume (need associates → job opportunity)
    2. solo_established (retirement risk → buyability)
    3. solo_inactive (possible transition)
    4. family_practice (succession intel)
    
    By default excludes already-researched practices.
    """
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    
    conditions = ["p.ownership_status IN ('independent', 'likely_independent', 'unknown')"]
    params = []
    
    if zip_code:
        zips = [z.strip() for z in zip_code.split(",")]
        placeholders = ",".join("?" * len(zips))
        conditions.append(f"p.zip IN ({placeholders})")
        params.extend(zips)
    
    if metro:
        metro_map = {"chicagoland": "%Chicagoland%", "boston": "%Boston%", "all": "%"}
        pattern = metro_map.get(metro.lower(), f"%{metro}%")
        conditions.append("p.zip IN (SELECT zip_code FROM watched_zips WHERE metro_area LIKE ?)")
        params.append(pattern)
    
    if entity_types:
        placeholders = ",".join("?" * len(entity_types))
        conditions.append(f"p.entity_classification IN ({placeholders})")
        params.extend(entity_types)
    
    if exclude_researched:
        conditions.append("p.npi NOT IN (SELECT npi FROM practice_intel)")
    
    where = " AND ".join(conditions)
    
    # Priority ordering: high-value targets first
    query = f"""
    SELECT p.npi, p.practice_name, p.doing_business_as, p.address, p.city, 
           p.state, p.zip, p.entity_type, p.taxonomy_code,
           p.ownership_status, p.entity_classification,
           p.buyability_score, p.year_established, p.employee_count,
           p.estimated_revenue, p.provider_last_name, p.phone, p.website
    FROM practices p
    WHERE {where}
    ORDER BY 
        CASE p.entity_classification
            WHEN 'solo_high_volume' THEN 1
            WHEN 'solo_established' THEN 2
            WHEN 'solo_inactive' THEN 3
            WHEN 'family_practice' THEN 4
            WHEN 'small_group' THEN 5
            WHEN 'large_group' THEN 6
            ELSE 7
        END,
        p.buyability_score DESC NULLS LAST,
        p.year_established ASC NULLS LAST
    """
    
    if top_n:
        query += f" LIMIT {top_n}"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_extra_context(practice):
    """Build context string from existing database fields to enrich the research prompt."""
    parts = []
    if practice.get("year_established"):
        age = datetime.now().year - practice["year_established"]
        parts.append(f"Established {practice['year_established']} ({age} years old)")
    if practice.get("employee_count"):
        parts.append(f"{practice['employee_count']} employees")
    if practice.get("estimated_revenue"):
        parts.append(f"Est. revenue ${practice['estimated_revenue']:,.0f}")
    if practice.get("entity_classification"):
        parts.append(f"Classification: {practice['entity_classification']}")
    if practice.get("buyability_score"):
        parts.append(f"Buyability score: {practice['buyability_score']}")
    if practice.get("ownership_status"):
        parts.append(f"Ownership: {practice['ownership_status']}")
    if practice.get("doing_business_as"):
        parts.append(f"DBA: {practice['doing_business_as']}")
    return ". ".join(parts)


def research_single_practice(engine, tracker, practice, force=False, 
                              deep=False, model=None):
    """Research one practice. Returns result dict."""
    npi = practice["npi"]
    name = practice.get("practice_name", "Unknown")
    
    if not force:
        existing = get_practice_intel(npi)
        if existing and is_cache_fresh(existing.get("research_date")):
            days = (datetime.now() - datetime.fromisoformat(existing["research_date"])).days
            print(f"  ⏭  {name[:40]:40} — cached {days}d ago")
            return existing
    
    print(f"  🔍 {name[:50]:50}", end=" ", flush=True)
    
    doctor_name = None
    if practice.get("entity_type") == "1":
        doctor_name = practice.get("practice_name", "")
    elif practice.get("provider_last_name"):
        doctor_name = f"Dr. {practice['provider_last_name']}"
    
    extra = build_extra_context(practice)
    
    if deep:
        result = engine.research_practice_deep(
            npi, name, practice.get("address", ""),
            practice.get("city", ""), practice.get("state", ""),
            practice.get("zip", ""), doctor_name, extra)
    else:
        result = engine.research_practice(
            npi, name, practice.get("address", ""),
            practice.get("city", ""), practice.get("state", ""),
            practice.get("zip", ""), doctor_name, extra, model=model)
    
    if "error" in result and "_meta" not in result:
        print(f"❌ {result['error'][:60]}")
        return result
    
    store_practice_intel(npi, result)
    
    cost = result.get("_meta", {}).get("cost_usd", 0)
    tracker.record("practice", cost, result.get("_meta", {}).get("model", ""), npi)
    
    readiness = result.get("readiness", result.get("acquisition_readiness", "?"))
    conf = result.get("confidence", "?")
    esc = " [ESCALATED]" if result.get("_escalated") else ""
    reviews = result.get("google", {}).get("reviews", "?")
    rating = result.get("google", {}).get("rating", "?")
    
    print(f"✅ ${cost:.3f} | ready={readiness} | G:{rating}★({reviews}r){esc}")
    
    return result


def show_status(db_path=None):
    """Show practice research coverage."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    
    total = conn.execute(
        "SELECT COUNT(*) FROM practices WHERE zip IN (SELECT zip_code FROM watched_zips)"
    ).fetchone()[0]
    
    researched = conn.execute("SELECT COUNT(*) FROM practice_intel").fetchone()[0]
    
    fresh = conn.execute(
        "SELECT COUNT(*) FROM practice_intel WHERE research_date > ?",
        ((datetime.now() - timedelta(days=DEFAULT_CACHE_TTL_DAYS)).isoformat(),)
    ).fetchone()[0]
    
    tracker = CostTracker()
    
    print("\n📊 Practice Deep Dive Status")
    print("=" * 50)
    print(f"  Practices in watched ZIPs:  {total:,}")
    print(f"  Researched:                 {researched:,} ({100*researched/max(total,1):.1f}%)")
    print(f"  Fresh (<{DEFAULT_CACHE_TTL_DAYS}d):              {fresh:,}")
    print(f"\n  💰 {tracker.summary()}")
    
    # By readiness
    rows = conn.execute("""
        SELECT acquisition_readiness, COUNT(*) as cnt
        FROM practice_intel
        GROUP BY acquisition_readiness
        ORDER BY cnt DESC
    """).fetchall()
    
    if rows:
        print("\n  By acquisition readiness:")
        for r in rows:
            print(f"    {r[0] or 'unknown':20} {r[1]:4}")
    
    # By entity classification
    rows = conn.execute("""
        SELECT p.entity_classification, COUNT(DISTINCT pi.npi) as researched,
               COUNT(DISTINCT p.npi) as total
        FROM practices p
        LEFT JOIN practice_intel pi ON p.npi = pi.npi
        WHERE p.zip IN (SELECT zip_code FROM watched_zips)
          AND p.entity_classification IS NOT NULL
        GROUP BY p.entity_classification
        ORDER BY total DESC
    """).fetchall()
    
    if rows:
        print("\n  Coverage by entity type:")
        for r in rows:
            pct = 100 * r[1] / max(r[2], 1)
            print(f"    {r[0] or 'null':25} {r[1]:4}/{r[2]:5} ({pct:.0f}%)")
    
    conn.close()


def show_report(npi, db_path=None):
    """Display stored practice dossier."""
    data = get_practice_intel(npi, db_path)
    if not data:
        print(f"No research for NPI {npi}. Run: python3 scrapers/practice_deep_dive.py --npi {npi}")
        return
    
    # Get practice info from main table
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    prac = conn.execute("SELECT * FROM practices WHERE npi = ?", (npi,)).fetchone()
    conn.close()
    
    age = ""
    if data.get("research_date"):
        days = (datetime.now() - datetime.fromisoformat(data["research_date"])).days
        age = f" ({days}d ago)"
    
    print(f"\n{'='*65}")
    print(f"  PRACTICE INTELLIGENCE DOSSIER")
    if prac:
        print(f"  {prac['practice_name']}")
        print(f"  {prac['address']}, {prac['city']}, {prac['state']} {prac['zip']}")
    print(f"  NPI: {npi}")
    print(f"  Researched: {data.get('research_date','?')}{age}")
    print(f"  Model: {data.get('model_used','?')} | Cost: ${data.get('cost_usd',0):.4f}")
    esc = " | ESCALATED (2-pass)" if data.get("escalated") else ""
    print(f"  Confidence: {data.get('confidence','?')}{esc}")
    print(f"{'='*65}")
    
    # Database intel
    if prac:
        print(f"\n📋 DATABASE INTEL")
        print(f"  Classification: {prac.get('entity_classification', 'N/A')}")
        print(f"  Ownership: {prac.get('ownership_status', 'N/A')}")
        print(f"  Buyability: {prac.get('buyability_score', 'N/A')}")
        if prac.get("year_established"):
            print(f"  Year Est.: {prac['year_established']} ({datetime.now().year - prac['year_established']}yr)")
        if prac.get("employee_count"):
            print(f"  Employees: {prac['employee_count']}")
        if prac.get("estimated_revenue"):
            print(f"  Revenue: ${prac['estimated_revenue']:,.0f}")
    
    # Web research
    print(f"\n🌐 WEBSITE")
    print(f"  URL: {data.get('website_url', 'N/A')}")
    print(f"  Era: {data.get('website_era', 'N/A')}")
    if data.get("website_analysis"):
        print(f"  {data['website_analysis']}")
    
    print(f"\n🦷 SERVICES")
    if data.get("services_listed"):
        try:
            svcs = json.loads(data["services_listed"]) if isinstance(data["services_listed"], str) else data["services_listed"]
            print(f"  {', '.join(svcs)}")
        except: print(f"  {data['services_listed']}")
    if data.get("services_high_rev"):
        try:
            hr = json.loads(data["services_high_rev"]) if isinstance(data["services_high_rev"], str) else data["services_high_rev"]
            print(f"  💰 High-revenue: {', '.join(hr)}")
        except: pass
    
    print(f"\n⚙️  TECHNOLOGY")
    if data.get("technology_listed"):
        try:
            tech = json.loads(data["technology_listed"]) if isinstance(data["technology_listed"], str) else data["technology_listed"]
            print(f"  {', '.join(tech)}")
        except: print(f"  {data['technology_listed']}")
    print(f"  Investment level: {data.get('technology_level', 'N/A')}")
    
    print(f"\n⭐ GOOGLE REVIEWS")
    print(f"  Rating: {data.get('google_rating', 'N/A')} | Count: {data.get('google_review_count', 'N/A')}")
    print(f"  Velocity: {data.get('google_velocity', 'N/A')}")
    if data.get("google_sentiment"):
        print(f"  Sentiment: {data['google_sentiment']}")
    
    print(f"\n👤 PROVIDERS")
    print(f"  Web count: {data.get('provider_count_web', 'N/A')}")
    print(f"  Owner stage: {data.get('owner_career_stage', 'N/A')}")
    if data.get("provider_notes"):
        print(f"  {data['provider_notes']}")
    
    print(f"\n📢 HIRING: {'YES' if data.get('hiring_active') else 'No signals found'}")
    if data.get("hiring_positions"):
        try:
            pos = json.loads(data["hiring_positions"])
            print(f"  Positions: {', '.join(pos)}")
        except: pass
    
    print(f"\n📰 ACQUISITION NEWS: {'YES — ' + data.get('acquisition_details','') if data.get('acquisition_found') else 'None found'}")
    
    print(f"\n📱 SOCIAL MEDIA")
    print(f"  Facebook: {data.get('social_facebook', 'N/A')}")
    print(f"  Instagram: {data.get('social_instagram', 'N/A')}")
    
    # Flags
    if data.get("red_flags"):
        try:
            flags = json.loads(data["red_flags"]) if isinstance(data["red_flags"], str) else data["red_flags"]
            print(f"\n🚩 RED FLAGS")
            for f in flags:
                print(f"  • {f}")
        except: pass
    
    if data.get("green_flags"):
        try:
            flags = json.loads(data["green_flags"]) if isinstance(data["green_flags"], str) else data["green_flags"]
            print(f"\n✅ GREEN FLAGS")
            for f in flags:
                print(f"  • {f}")
        except: pass
    
    print(f"\n{'='*65}")
    readiness = data.get("acquisition_readiness", "N/A")
    emoji = {"high": "🟢", "medium": "🟡", "low": "🟠", "unlikely": "🔴"}.get(readiness, "⚪")
    print(f"  {emoji} ACQUISITION READINESS: {readiness.upper()}")
    print(f"\n  {data.get('overall_assessment', 'No assessment generated')}")
    print(f"{'='*65}\n")


def show_dossier_zip(zip_code, db_path=None):
    """Show all researched practices in a ZIP."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute("""
        SELECT pi.npi, p.practice_name, pi.acquisition_readiness, pi.google_rating,
               pi.google_review_count, pi.website_era, pi.technology_level,
               pi.hiring_active, pi.confidence, pi.cost_usd
        FROM practice_intel pi
        JOIN practices p ON pi.npi = p.npi
        WHERE p.zip = ?
        ORDER BY 
            CASE pi.acquisition_readiness 
                WHEN 'high' THEN 1 WHEN 'medium' THEN 2 
                WHEN 'low' THEN 3 ELSE 4 END
    """, (zip_code,)).fetchall()
    
    conn.close()
    
    if not rows:
        print(f"No researched practices in ZIP {zip_code}")
        return
    
    print(f"\n📋 PRACTICE DOSSIERS — ZIP {zip_code} ({len(rows)} researched)")
    print(f"{'Practice':<40} {'Ready':>6} {'G★':>4} {'Rev':>5} {'Web':>8} {'Tech':>8} {'Hire':>5}")
    print("─" * 90)
    for r in rows:
        emoji = {"high":"🟢","medium":"🟡","low":"🟠","unlikely":"🔴"}.get(r["acquisition_readiness"],"⚪")
        hire = "YES" if r["hiring_active"] else ""
        print(f"{r['practice_name'][:39]:<40} {emoji}{r['acquisition_readiness'] or '?':>5} "
              f"{r['google_rating'] or '':>4} {r['google_review_count'] or '':>5} "
              f"{r['website_era'] or '':>8} {r['technology_level'] or '':>8} {hire:>5}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Practice-Level Deep Dive — dental practice due diligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --npi 1234567890                   Research one practice
  %(prog)s --zip 60491 --top 5                Top 5 targets in Homer Glen
  %(prog)s --zip 60491 --solo-established     All established solos in ZIP
  %(prog)s --zip 60491 --deep                 Two-pass (Haiku→Sonnet) for top targets
  %(prog)s --metro boston --solo-high-volume   High-volume solos across Boston
  %(prog)s --batch --metro chicagoland        Batch API (50%% off)
  %(prog)s --status                           Coverage stats
  %(prog)s --report 1234567890                Full dossier for one practice
  %(prog)s --dossier 60491                    All dossiers in a ZIP
        """
    )
    
    parser.add_argument("--npi", help="Research specific NPI(s) (comma-separated)")
    parser.add_argument("--zip", help="Research practices in ZIP(s)")
    parser.add_argument("--metro", help="Metro area filter")
    parser.add_argument("--top", type=int, default=0, help="Limit to top N targets")
    parser.add_argument("--deep", action="store_true", help="Two-pass: Haiku scan → Sonnet escalation")
    parser.add_argument("--refresh", action="store_true", help="Force re-research")
    parser.add_argument("--batch", action="store_true", help="Batch API (50%% off)")
    
    # Entity type filters
    parser.add_argument("--solo-established", action="store_true")
    parser.add_argument("--solo-high-volume", action="store_true")
    parser.add_argument("--solo-inactive", action="store_true")
    parser.add_argument("--family-practice", action="store_true")
    parser.add_argument("--all-independent", action="store_true", 
                       help="All non-DSO entity types")
    
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--report", metavar="NPI")
    parser.add_argument("--dossier", metavar="ZIP", help="All dossiers in a ZIP")
    parser.add_argument("--model", choices=["haiku", "sonnet"], default="haiku")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db", help="Override database path")
    
    args = parser.parse_args()
    ensure_intel_tables(args.db)
    
    if args.status:
        show_status(args.db)
        return
    if args.report:
        show_report(args.report, args.db)
        return
    if args.dossier:
        show_dossier_zip(args.dossier, args.db)
        return
    
    # Build entity type filter
    entity_types = []
    if args.solo_established: entity_types.append("solo_established")
    if args.solo_high_volume: entity_types.append("solo_high_volume")
    if args.solo_inactive: entity_types.append("solo_inactive")
    if args.family_practice: entity_types.append("family_practice")
    if args.all_independent:
        entity_types = ["solo_established", "solo_new", "solo_inactive", 
                       "solo_high_volume", "family_practice", "small_group", "large_group"]
    
    # Determine practices to research
    practices = []
    
    if args.npi:
        npis = [n.strip() for n in args.npi.split(",")]
        db = args.db or get_db_path()
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        for npi in npis:
            row = conn.execute("SELECT * FROM practices WHERE npi = ?", (npi,)).fetchone()
            if row:
                practices.append(dict(row))
            else:
                print(f"  ⚠️  NPI {npi} not found in database")
        conn.close()
    else:
        practices = get_practices_for_research(
            db_path=args.db,
            zip_code=args.zip,
            metro=args.metro,
            entity_types=entity_types or None,
            top_n=args.top or (20 if not args.zip else None),
            exclude_researched=not args.refresh
        )
    
    if not practices:
        print("No practices found matching criteria.")
        if not entity_types:
            print("Tip: Try --solo-established or --all-independent to filter by entity type")
        return
    
    model = MODEL_SONNET if args.model == "sonnet" else MODEL_HAIKU
    cost_per = 0.10 if args.model == "haiku" else 0.22
    if args.deep:
        cost_per = 0.28
    
    print(f"\n🎯 Practice Deep Dive")
    print(f"   Practices: {len(practices)}")
    print(f"   Mode: {'Two-pass (Haiku→Sonnet)' if args.deep else args.model}")
    est = len(practices) * cost_per * (0.5 if args.batch else 1)
    if args.batch:
        print(f"   Batch API: 50% discount")
    print(f"   Estimated cost: ${est:.2f}")
    
    if args.dry_run:
        print(f"\n   DRY RUN — practices that would be researched:")
        for p in practices[:15]:
            ec = p.get("entity_classification", "?")
            bs = p.get("buyability_score", "?")
            print(f"     {p['npi']} {p.get('practice_name','?')[:35]:35} [{ec}] buyability={bs}")
        if len(practices) > 15:
            print(f"     ... and {len(practices)-15} more")
        return
    
    if len(practices) > 3:
        resp = input(f"\n   Proceed with {len(practices)} practices (~${est:.2f})? [y/N] ")
        if resp.lower() != 'y':
            print("   Cancelled.")
            return
    
    engine = ResearchEngine(model=model)
    tracker = CostTracker()
    start_time = log_scrape_start("practice_deep_dive")

    try:
        if args.batch:
            items = []
            for p in practices:
                items.append({
                    "npi": p["npi"], "name": p.get("practice_name",""),
                    "address": p.get("address",""), "city": p.get("city",""),
                    "state": p.get("state",""), "zip": p.get("zip",""),
                    "doctor_name": p.get("practice_name","") if p.get("entity_type")=="1" else "",
                    "extra_context": build_extra_context(p)
                })
            reqs = engine.build_batch_requests(items, "practice")
            print(f"\n   Submitting batch of {len(reqs)} requests...")
            result = engine.submit_batch(reqs)
            if "error" in result:
                print(f"   ❌ {result['error']}")
                log_scrape_error("practice_deep_dive", start_time, str(result["error"]))
            else:
                print(f"   ✅ Batch: {result.get('batch_id')}")
                log_scrape_complete("practice_deep_dive", start_time,
                                   summary=f"Batch submitted: {result.get('batch_id')} ({len(reqs)} practices)")
            return

        # Synchronous
        print()
        success = 0
        total_cost = 0

        for i, p in enumerate(practices, 1):
            print(f"[{i}/{len(practices)}]", end="")
            result = research_single_practice(
                engine, tracker, p, force=args.refresh,
                deep=args.deep, model=model)
            if result and "error" not in result:
                success += 1
                total_cost += result.get("_meta", {}).get("cost_usd", 0)

        print(f"\n{'='*50}")
        print(f"  ✅ Researched: {success}/{len(practices)}")
        print(f"  💰 Cost: ${total_cost:.4f}")
        print(f"  📊 {tracker.summary()}")
        log_scrape_complete("practice_deep_dive", start_time, new_records=success,
                           summary=f"Researched {success}/{len(practices)} practices, cost ${total_cost:.4f}")
    except Exception as e:
        log_scrape_error("practice_deep_dive", start_time, str(e))
        raise


if __name__ == "__main__":
    main()
