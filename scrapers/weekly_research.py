#!/usr/bin/env python3
"""
Weekly Qualitative Research Runner

Designed to run as part of the weekly refresh pipeline (refresh.sh).
Uses Batch API for 50% cost savings on non-urgent research.

Strategy:
  1. Research any new/unresearched ZIPs (added since last run)
  2. Re-research stale ZIPs (>90 days old)
  3. Research top 20 unresearched high-priority practices
  4. Re-research practices flagged as "high readiness" (verify if still true)

Budget cap: Stops if estimated spend exceeds $5 per weekly run.

Usage:
  python3 scrapers/weekly_research.py              # Normal weekly run
  python3 scrapers/weekly_research.py --budget 10   # Higher budget cap
  python3 scrapers/weekly_research.py --dry-run     # Show what would run
  python3 scrapers/weekly_research.py --sync        # Immediate (no batch)
"""

import argparse
import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.expanduser("~/dental-pe-tracker"))

from scrapers.research_engine import ResearchEngine, CostTracker, MODEL_HAIKU
from scrapers.intel_database import (
    ensure_intel_tables, store_zip_intel, store_practice_intel,
    get_db_path, DEFAULT_CACHE_TTL_DAYS
)
from scrapers.logger_config import get_logger
from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

logger = get_logger("weekly_research")

DEFAULT_BUDGET = 5.00  # Max $ per weekly run
PRACTICE_BATCH_SIZE = 20  # Practices per week


def get_research_queue(db_path=None):
    """Build the weekly research queue with cost estimates."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    
    stale_cutoff = (datetime.now() - timedelta(days=DEFAULT_CACHE_TTL_DAYS)).isoformat()
    
    # New/unresearched ZIPs
    new_zips = conn.execute("""
        SELECT wz.zip_code, wz.city, wz.state
        FROM watched_zips wz
        LEFT JOIN zip_qualitative_intel qi ON wz.zip_code = qi.zip_code
        WHERE qi.zip_code IS NULL
    """).fetchall()
    
    # Stale ZIPs
    stale_zips = conn.execute("""
        SELECT qi.zip_code, wz.city, wz.state
        FROM zip_qualitative_intel qi
        JOIN watched_zips wz ON qi.zip_code = wz.zip_code
        WHERE qi.research_date < ?
    """, (stale_cutoff,)).fetchall()
    
    # Unresearched high-priority practices
    new_practices = conn.execute(f"""
        SELECT p.npi, p.practice_name, p.address, p.city, p.state, p.zip,
               p.entity_classification, p.buyability_score
        FROM practices p
        WHERE p.zip IN (SELECT zip_code FROM watched_zips)
          AND p.npi NOT IN (SELECT npi FROM practice_intel)
          AND p.ownership_status IN ('independent', 'likely_independent')
          AND p.entity_classification IN ('solo_high_volume', 'solo_established')
        ORDER BY p.buyability_score DESC NULLS LAST
        LIMIT {PRACTICE_BATCH_SIZE}
    """).fetchall()
    
    # High-readiness practices needing refresh
    stale_practices = conn.execute("""
        SELECT pi.npi, p.practice_name, p.address, p.city, p.state, p.zip
        FROM practice_intel pi
        JOIN practices p ON pi.npi = p.npi
        WHERE pi.acquisition_readiness = 'high'
          AND pi.research_date < ?
        LIMIT 10
    """, (stale_cutoff,)).fetchall()
    
    conn.close()
    
    return {
        "new_zips": [dict(zip(["zip_code","city","state"], r)) for r in new_zips],
        "stale_zips": [dict(zip(["zip_code","city","state"], r)) for r in stale_zips],
        "new_practices": [dict(zip(
            ["npi","practice_name","address","city","state","zip",
             "entity_classification","buyability_score"], r)) for r in new_practices],
        "stale_practices": [dict(zip(
            ["npi","practice_name","address","city","state","zip"], r)) for r in stale_practices],
    }


def estimate_cost(queue):
    """Estimate total cost for the queue."""
    zip_cost = (len(queue["new_zips"]) + len(queue["stale_zips"])) * 0.05
    prac_cost = (len(queue["new_practices"]) + len(queue["stale_practices"])) * 0.10
    # Batch discount
    return (zip_cost + prac_cost) * 0.5


def validate_dossier(npi: str, data: dict) -> tuple[bool, str]:
    """Anti-hallucination gate. Reject practice dossiers that fail evidence requirements.

    Returns (is_valid, reason). reason is empty on pass; populated on rejection.
    Rules:
      1. verification block must exist
      2. searches_executed must be >= 1 (we forced at least 1 via tool_choice)
      3. evidence_quality must not be 'insufficient'
         NOTE: model occasionally returns 'high' outside the spec (verified|partial|insufficient).
         We coerce 'high' -> 'partial' with a warning instead of quarantining (audit §10.5/#16).
      4. If website.url is set non-null, website._source_url must also be set
         (means: any cited website needs a citation URL)
      5. If google.reviews or google.rating is set, google._source_url must be set
    """
    ver = data.get("verification") or {}
    if not ver:
        return False, "missing_verification_block"

    searches = ver.get("searches_executed")
    try:
        searches_n = int(searches) if searches is not None else 0
    except (TypeError, ValueError):
        searches_n = 0
    if searches_n < 1:
        return False, f"insufficient_searches({searches_n})"

    quality = (ver.get("evidence_quality") or "").lower()
    if quality == "high":
        # Enum drift: model returned "high" instead of "verified|partial|insufficient".
        # Coerce to "partial" in-place so the dossier is stored but flagged. Audit §10.5/#16.
        logger.warning("NPI %s: evidence_quality='high' is outside spec — coercing to 'partial'", npi)
        ver["evidence_quality"] = "partial"
        quality = "partial"
    if quality == "insufficient":
        return False, "evidence_quality=insufficient"

    web = data.get("website") or {}
    if web.get("url") and not web.get("_source_url"):
        return False, "website.url_without_source"

    goog = data.get("google") or {}
    if (goog.get("reviews") is not None or goog.get("rating") is not None) and not goog.get("_source_url"):
        return False, "google.metrics_without_source"

    return True, ""


def validate_zip_dossier(zip_code: str, data: dict) -> tuple[bool, str]:
    """Anti-hallucination gate for ZIP intel dossiers. Parallel to validate_dossier().

    Returns (is_valid, reason). reason is empty on pass; populated on rejection.
    Rules:
      1. verification block must exist
      2. searches_executed must be >= 1 (we force at least 1 via tool_choice)
      3. evidence_quality must not be 'insufficient'
         NOTE: coerces 'high' -> 'partial' with warning (same as practice path, audit §10.5/#16).
      4. If real_estate.median_price or home_price_trend is set, real_estate._source_url must be set
      5. If dental_news.new_offices or dso_moves is non-empty, dental_news._source_url must be set
    """
    ver = data.get("verification") or {}
    if not ver:
        return False, "missing_verification_block"

    searches = ver.get("searches_executed")
    try:
        searches_n = int(searches) if searches is not None else 0
    except (TypeError, ValueError):
        searches_n = 0
    if searches_n < 1:
        return False, f"insufficient_searches({searches_n})"

    quality = (ver.get("evidence_quality") or "").lower()
    if quality == "high":
        logger.warning("ZIP %s: evidence_quality='high' is outside spec — coercing to 'partial'", zip_code)
        ver["evidence_quality"] = "partial"
        quality = "partial"
    if quality == "insufficient":
        return False, "evidence_quality=insufficient"

    re_data = data.get("real_estate") or {}
    if (re_data.get("median_price") is not None or re_data.get("trend")) and not re_data.get("_source_url"):
        return False, "real_estate.data_without_source"

    dental = data.get("dental_news") or {}
    if (dental.get("new_offices") or dental.get("dso_moves")) and not dental.get("_source_url"):
        return False, "dental_news.data_without_source"

    return True, ""


def retrieve_batch(batch_id):
    """Retrieve completed batch results and store them. Practice dossiers pass
    through validate_dossier() — failures are quarantined, not stored."""
    engine = ResearchEngine(model=MODEL_HAIKU)
    tracker = CostTracker()

    print(f"\n📦 Retrieving batch {batch_id}...")
    status = engine.check_batch(batch_id)

    if "error" in status:
        print(f"  ❌ Error checking batch: {status['error']}")
        return

    proc_status = status.get("processing_status", "unknown")
    print(f"  Status: {proc_status}")

    if proc_status != "ended":
        counts = status.get("request_counts", {})
        print(f"  Processing: {counts.get('processing', '?')}")
        print(f"  Succeeded: {counts.get('succeeded', '?')}")
        print(f"  Check again later.")
        return

    results = engine.get_batch_results(batch_id)
    if not results:
        print("  No results returned.")
        return

    stored = 0
    failed = 0
    rejected = 0
    rejection_reasons = {}
    for item in results:
        cid = item.get("id", "")
        data = item.get("data", {})
        if not data or "error" in data:
            logger.warning("Batch item %s failed: %s", cid, data.get("error", "unknown"))
            failed += 1
            continue

        try:
            if cid.startswith("zip_"):
                zip_code = cid[4:]
                ok, reason = validate_zip_dossier(zip_code, data)
                if not ok:
                    rejected += 1
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    logger.warning("Quarantined ZIP %s: %s", zip_code, reason)
                    print(f"  🚫 ZIP {zip_code} REJECTED ({reason})")
                    continue
                store_zip_intel(zip_code, data)
                tracker.record("zip", 0, "batch", zip_code)
                stored += 1
                print(f"  ✅ ZIP {zip_code}")
            elif cid.startswith("practice_"):
                npi = cid[9:]
                ok, reason = validate_dossier(npi, data)
                if not ok:
                    rejected += 1
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    logger.warning("Quarantined practice %s: %s", npi, reason)
                    print(f"  🚫 Practice {npi} REJECTED ({reason})")
                    continue
                store_practice_intel(npi, data)
                tracker.record("practice", 0, "batch", npi)
                stored += 1
                print(f"  ✅ Practice {npi}")
        except Exception as e:
            failed += 1
            logger.error("Skipping %s due to storage error: %s", cid, e)
            print(f"  ⚠️  Skipped {cid}: {str(e)[:120]}")

    print(f"\n  Stored {stored}/{len(results)} results "
          f"({failed} errored, {rejected} quarantined).")
    if rejection_reasons:
        print(f"  Rejection breakdown: {dict(rejection_reasons)}")


def retrieve_zip_batch(batch_id: str, db_path=None):
    """Retrieve completed ZIP batch results and store them through validate_zip_dossier gate."""
    engine = ResearchEngine(model=MODEL_HAIKU)
    tracker = CostTracker()

    print(f"\n📦 Retrieving ZIP batch {batch_id}...")
    status = engine.check_batch(batch_id)

    if "error" in status:
        print(f"  ❌ Error checking batch: {status['error']}")
        return

    proc_status = status.get("processing_status", "unknown")
    print(f"  Status: {proc_status}")

    if proc_status != "ended":
        counts = status.get("request_counts", {})
        print(f"  Processing: {counts.get('processing', '?')}")
        print(f"  Succeeded: {counts.get('succeeded', '?')}")
        print(f"  Check again later.")
        return

    results = engine.get_batch_results(batch_id)
    if not results:
        print("  No results returned.")
        return

    from scrapers.intel_database import store_zip_intel

    stored = 0
    failed = 0
    rejected = 0
    rejection_reasons = {}
    for item in results:
        cid = item.get("id", "")
        data = item.get("data", {})
        if not data or "error" in data:
            logger.warning("Batch item %s failed: %s", cid, data.get("error", "unknown"))
            failed += 1
            continue

        try:
            if cid.startswith("zip_"):
                zip_code = cid[4:]
                ok, reason = validate_zip_dossier(zip_code, data)
                if not ok:
                    rejected += 1
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    logger.warning("Quarantined ZIP %s: %s", zip_code, reason)
                    print(f"  🚫 ZIP {zip_code} REJECTED ({reason})")
                    continue
                store_zip_intel(zip_code, data)
                tracker.record("zip", 0, "batch", zip_code)
                stored += 1
                print(f"  ✅ ZIP {zip_code}")
        except Exception as e:
            failed += 1
            logger.error("Skipping %s due to storage error: %s", cid, e)
            print(f"  ⚠️  Skipped {cid}: {str(e)[:120]}")

    print(f"\n  Stored {stored}/{len(results)} results "
          f"({failed} errored, {rejected} quarantined).")
    if rejection_reasons:
        print(f"  Rejection breakdown: {dict(rejection_reasons)}")


def main():
    parser = argparse.ArgumentParser(description="Weekly qualitative research automation")
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET,
                       help=f"Max spend per run (default: ${DEFAULT_BUDGET})")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sync", action="store_true", help="Synchronous (no batch)")
    parser.add_argument("--retrieve", metavar="BATCH_ID",
                       help="Retrieve results from a completed batch")
    parser.add_argument("--db", help="Database path override")
    args = parser.parse_args()

    ensure_intel_tables(args.db)

    if args.retrieve:
        retrieve_batch(args.retrieve)
        return

    queue = get_research_queue(args.db)
    est = estimate_cost(queue)

    print(f"\n📅 Weekly Qualitative Research")
    print(f"{'='*50}")
    print(f"  New ZIPs to research:      {len(queue['new_zips'])}")
    print(f"  Stale ZIPs to refresh:     {len(queue['stale_zips'])}")
    print(f"  New practices to research:  {len(queue['new_practices'])}")
    print(f"  Stale practices to refresh: {len(queue['stale_practices'])}")
    print(f"  Estimated cost:             ${est:.2f} (batch pricing)")
    print(f"  Budget cap:                 ${args.budget:.2f}")

    if est > args.budget:
        print(f"\n  ⚠️  Over budget — trimming queue")
        queue["stale_practices"] = []
        queue["stale_zips"] = queue["stale_zips"][:5]
        est = estimate_cost(queue)
        if est > args.budget:
            queue["new_practices"] = queue["new_practices"][:10]
            est = estimate_cost(queue)
        print(f"  Trimmed estimate: ${est:.2f}")

    total_items = (len(queue["new_zips"]) + len(queue["stale_zips"]) +
                   len(queue["new_practices"]) + len(queue["stale_practices"]))

    if total_items == 0:
        print(f"\n  ✅ Nothing to research — all data is fresh!")
        return

    if args.dry_run:
        print(f"\n  DRY RUN — would research:")
        for z in queue["new_zips"][:5]:
            print(f"    ZIP {z['zip_code']} {z.get('city','')} (new)")
        for z in queue["stale_zips"][:5]:
            print(f"    ZIP {z['zip_code']} {z.get('city','')} (stale)")
        for p in queue["new_practices"][:10]:
            print(f"    Practice {p['npi']} {p.get('practice_name','')[:30]} (new)")
        return

    engine = ResearchEngine(model=MODEL_HAIKU)
    tracker = CostTracker()
    start_time = log_scrape_start("weekly_research")

    try:
        if args.sync:
            total_cost = 0
            success = 0

            all_zips = queue["new_zips"] + queue["stale_zips"]
            all_pracs = queue["new_practices"] + queue["stale_practices"]

            for z in all_zips:
                print(f"  🔍 ZIP {z['zip_code']}...", end=" ", flush=True)
                r = engine.research_zip(z["zip_code"], z.get("city",""), z.get("state",""))
                if "error" not in r or "_meta" in r:
                    # Validate before storing — same gate as batch path (audit §10.4 / §15 #5)
                    ok, reason = validate_zip_dossier(z["zip_code"], r)
                    if not ok:
                        logger.warning("Sync quarantined ZIP %s: %s", z["zip_code"], reason)
                        print(f"❌ REJECTED ({reason})")
                        continue
                    store_zip_intel(z["zip_code"], r)
                    cost = r.get("_meta",{}).get("cost_usd", 0)
                    tracker.record("zip", cost, r.get("_meta",{}).get("model",""), z["zip_code"])
                    total_cost += cost
                    success += 1
                    print(f"✅ ${cost:.3f}")
                else:
                    print(f"❌")

            for p in all_pracs:
                name = p.get("practice_name","?")[:30]
                print(f"  🔍 {name}...", end=" ", flush=True)
                r = engine.research_practice(
                    p["npi"], p.get("practice_name",""), p.get("address",""),
                    p.get("city",""), p.get("state",""), p.get("zip",""))
                if "error" not in r or "_meta" in r:
                    # Validate before storing — same gate as batch path (audit §10.4 / §15 #5)
                    ok, reason = validate_dossier(p["npi"], r)
                    if not ok:
                        logger.warning("Sync quarantined practice %s: %s", p["npi"], reason)
                        print(f"❌ REJECTED ({reason})")
                        continue
                    store_practice_intel(p["npi"], r)
                    cost = r.get("_meta",{}).get("cost_usd", 0)
                    tracker.record("practice", cost, r.get("_meta",{}).get("model",""), p["npi"])
                    total_cost += cost
                    success += 1
                    print(f"✅ ${cost:.3f}")
                else:
                    print(f"❌")

            print(f"\n  Done: {success}/{total_items} | Cost: ${total_cost:.4f}")
            log_scrape_complete("weekly_research", start_time, new_records=success,
                               summary=f"Sync: {success}/{total_items} items, cost ${total_cost:.4f}")
        else:
            # Batch mode (recommended — 50% off)
            all_zip_items = [{"zip_code": z["zip_code"], "city": z.get("city",""),
                             "state": z.get("state","")}
                            for z in queue["new_zips"] + queue["stale_zips"]]

            all_prac_items = [{
                "npi": p["npi"], "name": p.get("practice_name",""),
                "address": p.get("address",""), "city": p.get("city",""),
                "state": p.get("state",""), "zip": p.get("zip",""),
                "doctor_name": "", "extra_context": ""
            } for p in queue["new_practices"] + queue["stale_practices"]]

            batch_ids = []
            if all_zip_items:
                zip_reqs = engine.build_batch_requests(all_zip_items, "zip")
                result = engine.submit_batch(zip_reqs)
                if "error" not in result:
                    print(f"  ✅ ZIP batch submitted: {result.get('batch_id')} ({len(zip_reqs)} ZIPs)")
                    batch_ids.append(result.get("batch_id"))
                else:
                    print(f"  ❌ ZIP batch failed: {result['error'][:100]}")

            if all_prac_items:
                prac_reqs = engine.build_batch_requests(all_prac_items, "practice")
                result = engine.submit_batch(prac_reqs)
                if "error" not in result:
                    print(f"  ✅ Practice batch submitted: {result.get('batch_id')} ({len(prac_reqs)} practices)")
                    batch_ids.append(result.get("batch_id"))
                else:
                    print(f"  ❌ Practice batch failed: {result['error'][:100]}")

            print(f"\n  Batches submitted. Results available in ~30 min.")
            for bid in batch_ids:
                print(f"  Retrieve with: python3 scrapers/weekly_research.py --retrieve {bid}")
            log_scrape_complete("weekly_research", start_time,
                               summary=f"Batch mode: {len(batch_ids)} batches submitted, {total_items} items")

        print(f"\n  💰 {tracker.summary()}")
    except Exception as e:
        log_scrape_error("weekly_research", str(e), start_time)
        raise


if __name__ == "__main__":
    main()
