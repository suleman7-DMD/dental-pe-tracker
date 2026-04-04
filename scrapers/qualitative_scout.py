#!/usr/bin/env python3
"""
ZIP-Level Qualitative Scout

Researches a ZIP code (or list of ZIPs) for dental market intelligence using
Claude API + web search. Stores structured results in the database.

Usage:
  python3 scrapers/qualitative_scout.py --zip 60491
  python3 scrapers/qualitative_scout.py --zip 60491,60439,60441
  python3 scrapers/qualitative_scout.py --metro chicagoland --top 10
  python3 scrapers/qualitative_scout.py --metro boston --refresh
  python3 scrapers/qualitative_scout.py --batch --metro chicagoland  (batch API, 50% off)
  python3 scrapers/qualitative_scout.py --status
  python3 scrapers/qualitative_scout.py --report 60491

Cost estimates (Haiku 4.5, March 2026):
  Single ZIP:     ~$0.04-0.06
  10 ZIPs:        ~$0.50
  All 290 ZIPs:   ~$15 (batch mode recommended)
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
    ensure_intel_tables, store_zip_intel, get_zip_intel,
    is_cache_fresh, get_db_path, DEFAULT_CACHE_TTL_DAYS
)
from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

logger = get_logger("qualitative_scout")


def get_watched_zips(metro=None, db_path=None):
    """Fetch watched ZIPs from database, optionally filtered by metro."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    
    if metro:
        metro_map = {
            "chicagoland": "%Chicagoland%",
            "chi-all": "%Chicagoland%",
            "boston": "%Boston%",
            "all": "%",
        }
        pattern = metro_map.get(metro.lower(), f"%{metro}%")
        rows = conn.execute(
            "SELECT zip_code, city, state, metro_area FROM watched_zips "
            "WHERE metro_area LIKE ? ORDER BY zip_code", (pattern,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT zip_code, city, state, metro_area FROM watched_zips "
            "ORDER BY zip_code"
        ).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


def get_top_priority_zips(n=10, metro=None, db_path=None):
    """
    Get highest-priority ZIPs for research — those with highest buyability scores
    or most consolidation activity but no qualitative intel yet.
    """
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    
    # ZIPs with zip_scores but no qualitative intel, sorted by interest
    params = []
    query = """
    SELECT wz.zip_code, wz.city, wz.state, wz.metro_area,
           zs.total_practices, zs.consolidation_pct
    FROM watched_zips wz
    LEFT JOIN zip_scores zs ON wz.zip_code = zs.zip_code
    LEFT JOIN zip_qualitative_intel qi ON wz.zip_code = qi.zip_code
    WHERE qi.zip_code IS NULL
    """
    if metro:
        metro_map = {"chicagoland": "%Chicagoland%", "boston": "%Boston%", "all": "%"}
        pattern = metro_map.get(metro.lower(), f"%{metro}%")
        query += " AND wz.metro_area LIKE ?"
        params.append(pattern)

    query += " ORDER BY zs.total_practices DESC NULLS LAST LIMIT ?"
    params.append(n)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def research_single_zip(engine, tracker, zip_info, force=False, model=None):
    """Research one ZIP code. Respects cache unless force=True."""
    zc = zip_info["zip_code"]
    
    if not force:
        existing = get_zip_intel(zc)
        if existing and is_cache_fresh(existing.get("research_date")):
            days = (datetime.now() - datetime.fromisoformat(existing["research_date"])).days
            print(f"  ⏭  {zc} ({zip_info.get('city','')}) — cached {days}d ago. Use --refresh to force.")
            return existing
    
    print(f"  🔍 Researching {zc} ({zip_info.get('city','')}, {zip_info.get('state','')})...")
    
    result = engine.research_zip(zc, zip_info.get("city", ""), 
                                  zip_info.get("state", ""), model=model)
    
    if "error" in result and "_meta" not in result:
        print(f"  ❌ Error: {result['error']}")
        return result
    
    # Store results
    store_zip_intel(zc, result)
    
    # Track cost
    cost = result.get("_meta", {}).get("cost_usd", 0)
    tracker.record("zip", cost, result.get("_meta", {}).get("model", ""), zc)
    
    # Quick summary
    thesis = result.get("investment_thesis", "No thesis generated")
    conf = result.get("confidence", "?")
    print(f"  ✅ Done (${cost:.4f}) [{conf}] — {thesis[:100]}...")
    
    return result


def show_status(db_path=None):
    """Show research coverage status."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    
    total_watched = conn.execute("SELECT COUNT(*) FROM watched_zips").fetchone()[0]
    total_researched = conn.execute(
        "SELECT COUNT(*) FROM zip_qualitative_intel").fetchone()[0]
    
    fresh = conn.execute(
        "SELECT COUNT(*) FROM zip_qualitative_intel WHERE research_date > ?",
        ((datetime.now() - timedelta(days=DEFAULT_CACHE_TTL_DAYS)).isoformat(),)
    ).fetchone()[0]
    
    stale = total_researched - fresh
    unresearched = total_watched - total_researched
    
    # Cost info
    tracker = CostTracker()
    
    print("\n📊 ZIP Qualitative Research Status")
    print("=" * 50)
    print(f"  Watched ZIPs:     {total_watched}")
    print(f"  Researched:       {total_researched} ({100*total_researched/max(total_watched,1):.0f}%)")
    print(f"  Fresh (<{DEFAULT_CACHE_TTL_DAYS}d):     {fresh}")
    print(f"  Stale:            {stale}")
    print(f"  Not researched:   {unresearched}")
    print(f"\n  💰 {tracker.summary()}")
    
    # By metro
    rows = conn.execute("""
        SELECT wz.metro_area, COUNT(DISTINCT wz.zip_code) as total,
               COUNT(DISTINCT qi.zip_code) as researched
        FROM watched_zips wz
        LEFT JOIN zip_qualitative_intel qi ON wz.zip_code = qi.zip_code
        GROUP BY wz.metro_area
        ORDER BY total DESC
    """).fetchall()
    
    if rows:
        print("\n  By metro:")
        for r in rows:
            pct = 100 * r[2] / max(r[1], 1)
            print(f"    {r[0]:30} {r[2]:3}/{r[1]:3} ({pct:.0f}%)")
    
    conn.close()


def show_report(zip_code, db_path=None):
    """Display stored research report for a ZIP."""
    data = get_zip_intel(zip_code, db_path)
    if not data:
        print(f"No research found for ZIP {zip_code}. Run: python3 scrapers/qualitative_scout.py --zip {zip_code}")
        return
    
    age = ""
    if data.get("research_date"):
        days = (datetime.now() - datetime.fromisoformat(data["research_date"])).days
        age = f" ({days} days ago)"
    
    print(f"\n{'='*60}")
    print(f"  QUALITATIVE INTELLIGENCE: ZIP {zip_code}")
    print(f"  Researched: {data.get('research_date','?')}{age}")
    print(f"  Model: {data.get('model_used','?')} | Cost: ${data.get('cost_usd',0):.4f}")
    print(f"  Confidence: {data.get('confidence','?')}")
    print(f"{'='*60}")
    
    sections = [
        ("🏗  Housing", [("Status", "housing_status"), ("Developments", "housing_developments"), ("", "housing_summary")]),
        ("🏫 Schools", [("District", "school_district"), ("Rating", "school_rating"), ("", "school_note")]),
        ("🛒 Retail", [("Premium", "retail_premium"), ("Mass", "retail_mass"), ("", "retail_income_signal")]),
        ("🏢 Commercial", [("Status", "commercial_status"), ("", "commercial_note")]),
        ("🦷 Dental News", [("New offices", "dental_new_offices"), ("DSO moves", "dental_dso_moves"), ("", "dental_note")]),
        ("🏠 Real Estate", [("Median", "median_home_price"), ("Trend", "home_price_trend"), ("YoY", "home_price_yoy_pct")]),
        ("👥 Population", [("Growth", "pop_growth_signals"), ("Demographics", "pop_demographics")]),
        ("🏭 Employers", [("Major", "major_employers"), ("Insurance", "insurance_signal")]),
        ("⚔  Competition", [("New", "competitor_new"), ("Closures", "competitor_closures")]),
    ]
    
    for title, fields in sections:
        print(f"\n{title}")
        for label, key in fields:
            val = data.get(key)
            if val:
                if label:
                    print(f"  {label}: {val}")
                else:
                    print(f"  {val}")
    
    print(f"\n📈 DEMAND: {data.get('demand_outlook','N/A')}")
    print(f"📉 SUPPLY: {data.get('supply_outlook','N/A')}")
    print(f"\n💡 THESIS: {data.get('investment_thesis','N/A')}")
    
    sources = data.get("sources")
    if sources:
        try:
            src_list = json.loads(sources) if isinstance(sources, str) else sources
            print(f"\n📎 Sources: {len(src_list)} consulted")
        except Exception:
            pass
    print()


def main():
    parser = argparse.ArgumentParser(
        description="ZIP-Level Qualitative Scout — dental market intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --zip 60491                    Research Homer Glen
  %(prog)s --zip 60491,60439,60441        Research multiple ZIPs
  %(prog)s --metro boston --top 5          Research top 5 unresearched Boston ZIPs
  %(prog)s --metro chicagoland --refresh  Re-research all Chicagoland ZIPs
  %(prog)s --batch --metro boston          Use batch API (50%% off, async)
  %(prog)s --status                       Show research coverage
  %(prog)s --report 60491                 Display stored report
  %(prog)s --model sonnet --zip 60491     Use Sonnet for premium analysis
        """
    )
    
    parser.add_argument("--zip", help="ZIP code(s) to research (comma-separated)")
    parser.add_argument("--metro", help="Metro area: chicagoland, boston, chi-north, etc.")
    parser.add_argument("--top", type=int, default=0, help="Research top N unresearched ZIPs")
    parser.add_argument("--refresh", action="store_true", help="Force re-research even if cached")
    parser.add_argument("--batch", action="store_true", help="Use Batch API (50%% off, async)")
    parser.add_argument("--status", action="store_true", help="Show research coverage status")
    parser.add_argument("--report", metavar="ZIP", help="Display stored report for a ZIP")
    parser.add_argument("--model", choices=["haiku", "sonnet"], default="haiku",
                       help="Model to use (default: haiku — cheapest)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be researched")
    parser.add_argument("--db", help="Override database path")
    
    args = parser.parse_args()
    
    # Ensure tables exist
    ensure_intel_tables(args.db)
    
    if args.status:
        show_status(args.db)
        return
    
    if args.report:
        show_report(args.report, args.db)
        return
    
    # Determine which ZIPs to research
    zips_to_research = []
    
    if args.zip:
        # Explicit ZIP list
        zip_codes = [z.strip() for z in args.zip.split(",")]
        db = args.db or get_db_path()
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        for zc in zip_codes:
            row = conn.execute(
                "SELECT zip_code, city, state, metro_area FROM watched_zips WHERE zip_code = ?",
                (zc,)
            ).fetchone()
            if row:
                zips_to_research.append(dict(row))
            else:
                # Not in watched_zips — research anyway with minimal info
                zips_to_research.append({"zip_code": zc, "city": "Unknown", "state": "??"})
        conn.close()
    
    elif args.top and args.metro:
        zips_to_research = get_top_priority_zips(args.top, args.metro, args.db)
    
    elif args.metro:
        zips_to_research = get_watched_zips(args.metro, args.db)
    
    if not zips_to_research and not (args.status or args.report):
        parser.print_help()
        print("\nSpecify --zip, --metro, or --status")
        return
    
    model = MODEL_SONNET if args.model == "sonnet" else MODEL_HAIKU
    
    # Show plan
    print(f"\n🎯 ZIP Qualitative Scout")
    print(f"   ZIPs to research: {len(zips_to_research)}")
    print(f"   Model: {args.model} ({'~$0.04-0.06' if args.model == 'haiku' else '~$0.12-0.15'}/ZIP)")
    est = len(zips_to_research) * (0.05 if args.model == "haiku" else 0.14)
    if args.batch:
        est *= 0.5
        print(f"   Mode: Batch API (50% discount)")
    print(f"   Estimated cost: ${est:.2f}")
    
    if args.dry_run:
        print("\n   DRY RUN — ZIPs that would be researched:")
        for z in zips_to_research[:20]:
            cached = get_zip_intel(z["zip_code"], args.db)
            status = "cached" if cached and is_cache_fresh(cached.get("research_date")) else "needs research"
            print(f"     {z['zip_code']} {z.get('city',''):20} [{status}]")
        if len(zips_to_research) > 20:
            print(f"     ... and {len(zips_to_research)-20} more")
        return
    
    # Confirm
    if len(zips_to_research) > 5:
        resp = input(f"\n   Proceed with {len(zips_to_research)} ZIPs (~${est:.2f})? [y/N] ")
        if resp.lower() != 'y':
            print("   Cancelled.")
            return
    
    engine = ResearchEngine(model=model)
    tracker = CostTracker()
    start_time = log_scrape_start("qualitative_scout")

    try:
        if args.batch:
            # Batch mode — submit all at once, retrieve later
            items = [{"zip_code": z["zip_code"], "city": z.get("city",""),
                      "state": z.get("state","")} for z in zips_to_research]
            reqs = engine.build_batch_requests(items, "zip")
            print(f"\n   Submitting batch of {len(reqs)} requests...")
            result = engine.submit_batch(reqs)
            if "error" in result:
                print(f"   ❌ Batch failed: {result['error']}")
                log_scrape_error("qualitative_scout", str(result["error"]), start_time)
            else:
                print(f"   ✅ Batch submitted: {result.get('batch_id')}")
                print(f"   Check status: python3 scrapers/qualitative_scout.py --batch-status {result.get('batch_id')}")
                log_scrape_complete("qualitative_scout", start_time,
                                   summary=f"Batch submitted: {result.get('batch_id')} ({len(reqs)} ZIPs)")
            return

        # Synchronous mode — research one at a time
        print()
        success = 0
        total_cost = 0

        for i, z in enumerate(zips_to_research, 1):
            print(f"[{i}/{len(zips_to_research)}]", end="")
            result = research_single_zip(engine, tracker, z, force=args.refresh, model=model)
            if result and "error" not in result:
                success += 1
                total_cost += result.get("_meta", {}).get("cost_usd", 0)

        print(f"\n{'='*50}")
        print(f"  ✅ Researched: {success}/{len(zips_to_research)} ZIPs")
        print(f"  💰 Cost: ${total_cost:.4f}")
        print(f"  📊 {tracker.summary()}")
        log_scrape_complete("qualitative_scout", start_time, new_records=success,
                           summary=f"Researched {success}/{len(zips_to_research)} ZIPs, cost ${total_cost:.4f}")
    except Exception as e:
        log_scrape_error("qualitative_scout", str(e), start_time)
        raise


if __name__ == "__main__":
    main()
