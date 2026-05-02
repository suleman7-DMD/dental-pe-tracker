"""
poll_name_resolve.py — Poll + store results from resolve_fabricated_names.py batch.

Reads batch_id from /tmp/name_resolve_batch_id.txt (or --batch-id flag).
When batch completes, parses each result's JSON, extracts business_name,
and writes it to practices.data_axle_raw_name for the matching NPI.

Handles the associate/employee distinction:
  - If provider_role="associate", the business_name is the practice they work AT
    (still the correct name for that address/location)
  - If practice_status="closed", name is stored but flagged in notes
  - Low-confidence results without source URLs are skipped

After this completes, re-run:
  python3 scrapers/dedup_practice_locations.py
  python3 scrapers/sync_to_supabase.py --tables practice_locations
"""
import argparse
import json
import os
import sys
import time

ROOT = "/Users/suleman/dental-pe-tracker"
sys.path.insert(0, ROOT)
for raw in open(os.path.join(ROOT, ".env")):
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import sqlite3
import requests
from scrapers.database import DB_PATH

POLL_INTERVAL = 30
MAX_POLLS = 180  # 90 minutes


def get_batch_id(args):
    if args.batch_id:
        return args.batch_id
    for path in ("/tmp/name_resolve_batch_id.txt", "data/name_resolve_batch_id.json"):
        full = os.path.join(ROOT, path) if not path.startswith("/") else path
        if os.path.exists(full):
            if full.endswith(".json"):
                return json.load(open(full))["batch_id"]
            return open(full).read().strip()
    return None


def poll_batch(batch_id, api_key):
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    for i in range(MAX_POLLS):
        resp = requests.get(
            f"https://api.anthropic.com/v1/messages/batches/{batch_id}",
            headers=headers, timeout=30,
        )
        if not resp.ok:
            print(f"  Poll error: {resp.status_code}")
            time.sleep(POLL_INTERVAL)
            continue

        data = resp.json()
        status = data.get("processing_status")
        counts = data.get("request_counts", {})
        print(f"  [{i+1}/{MAX_POLLS}] status={status} "
              f"succeeded={counts.get('succeeded',0)} "
              f"errored={counts.get('errored',0)} "
              f"processing={counts.get('processing',0)}")

        if status == "ended":
            return data
        time.sleep(POLL_INTERVAL)

    print("Timed out waiting for batch.")
    return None


def download_results(batch_id, api_key):
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    resp = requests.get(
        f"https://api.anthropic.com/v1/messages/batches/{batch_id}/results",
        headers=headers, timeout=120, stream=True,
    )
    if not resp.ok:
        print(f"Download error: {resp.status_code}")
        return []

    results = []
    for line in resp.iter_lines():
        if line:
            results.append(json.loads(line))
    return results


def extract_business_name(result_line):
    """Parse a batch result line and extract the business name JSON.

    Web-search responses split text across many content blocks, so we
    concat all text blocks first, then look for JSON anywhere in the
    combined string (```json``` fenced, bare {\"business_name\":...}, or
    the full string).
    """
    if result_line.get("result", {}).get("type") != "succeeded":
        return None, "batch_error"

    message = result_line["result"]["message"]
    all_text = ""
    for block in message.get("content", []):
        if block.get("type") == "text":
            all_text += block["text"]

    if not all_text.strip():
        return None, "no_text_in_response"

    import re

    # Method 1: fenced ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", all_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1)), None
        except json.JSONDecodeError:
            pass

    # Method 2: any {"business_name": ...} object
    m = re.search(r'\{"business_name".*?\}', all_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0)), None
        except json.JSONDecodeError:
            pass

    # Method 3: entire text as JSON
    try:
        return json.loads(all_text.strip()), None
    except json.JSONDecodeError:
        pass

    return None, "no_json_in_response"


def store_results(results):
    """Write resolved names to practices.data_axle_raw_name.

    The resolved name represents the practice AT the address, which is correct
    regardless of whether the NPI holder is the owner or an associate.
    For multi-provider locations, ALL provider NPIs at the address get the
    same resolved business name so the dedup pipeline picks it up.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    stored = 0
    skipped_low = 0
    skipped_closed = 0
    errors = 0
    null_names = 0
    confirmed_fabricated = 0
    role_counts = {"owner": 0, "associate": 0, "unknown": 0}
    detail_log = []

    # Build a map of NPI -> all NPIs at the same location, so we can propagate
    # the resolved name to co-located providers
    location_map = {}
    loc_rows = conn.execute("""
        SELECT pl.primary_npi, pl.provider_npis
        FROM practice_locations pl
        JOIN watched_zips wz ON pl.zip = wz.zip_code
        WHERE pl.practice_name LIKE '% Dental'
          AND pl.has_org_npi = 0
          AND pl.data_axle_enriched = 0
    """).fetchall()
    for lr in loc_rows:
        try:
            npis = json.loads(lr["provider_npis"]) if lr["provider_npis"] else []
        except (json.JSONDecodeError, TypeError):
            npis = []
        location_map[lr["primary_npi"]] = npis

    for line in results:
        custom_id = line.get("custom_id", "")
        npi = custom_id.replace("name_", "")

        parsed, err = extract_business_name(line)
        if err:
            errors += 1
            continue

        if not parsed or not parsed.get("business_name"):
            null_names += 1
            continue

        biz_name = parsed["business_name"].strip()
        confidence = parsed.get("confidence", "low")
        source_url = parsed.get("source_url")
        role = parsed.get("provider_role", "unknown")
        status = parsed.get("practice_status", "unknown")
        notes = parsed.get("notes", "")

        role_counts[role] = role_counts.get(role, 0) + 1

        if confidence == "low" and not source_url:
            skipped_low += 1
            continue

        if status == "closed" and not biz_name:
            skipped_closed += 1
            detail_log.append({"npi": npi, "action": "skipped_closed", "notes": notes})
            continue

        # Check if the resolved name is just the fabricated pattern back
        existing = conn.execute(
            "SELECT provider_last_name FROM practices WHERE npi = ?", (npi,)
        ).fetchone()
        is_confirmation = False
        if existing:
            last = (existing[0] or "").strip().lower()
            biz_lower = biz_name.lower()
            if last and biz_lower in (
                f"{last} dental",
                f"{last} dental office",
                f"dr. {last} dds",
                f"dr. {last}",
            ):
                is_confirmation = True
                confirmed_fabricated += 1

        # Write to ALL NPIs at this location so the dedup picks it up from any row
        all_npis = location_map.get(npi, [npi])
        if npi not in all_npis:
            all_npis.append(npi)

        for target_npi in all_npis:
            conn.execute(
                "UPDATE practices SET data_axle_raw_name = ? WHERE npi = ? AND data_axle_raw_name IS NULL",
                (biz_name, target_npi),
            )

        stored += 1
        detail_log.append({
            "npi": npi, "name": biz_name, "role": role,
            "confidence": confidence, "is_confirmation": is_confirmation,
            "propagated_to": len(all_npis),
            "action": "confirmed_fabricated" if is_confirmation else "stored",
        })

    conn.commit()
    conn.close()

    return {
        "total_results": len(results),
        "stored": stored,
        "confirmed_fabricated_was_correct": confirmed_fabricated,
        "skipped_low_confidence": skipped_low,
        "skipped_closed": skipped_closed,
        "null_name_returned": null_names,
        "errors": errors,
        "provider_roles": role_counts,
        "detail_sample": detail_log[:20],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--skip-poll", action="store_true",
                    help="Skip polling, just download results (batch already ended)")
    ap.add_argument("--from-file", default=None,
                    help="Read results from a local JSONL file instead of downloading")
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    batch_id = get_batch_id(args)
    if not batch_id:
        print("ERROR: No batch_id found. Run resolve_fabricated_names.py first.")
        sys.exit(1)

    print(f"Batch: {batch_id}")

    if not args.skip_poll:
        print(f"Polling every {POLL_INTERVAL}s (max {MAX_POLLS} polls = "
              f"{MAX_POLLS * POLL_INTERVAL // 60}min)...")
        batch_data = poll_batch(batch_id, api_key)
        if not batch_data:
            sys.exit(1)
    else:
        print("Skipping poll (--skip-poll), downloading directly...")

    if args.from_file:
        print(f"\nReading results from {args.from_file}...")
        results = [json.loads(line) for line in open(args.from_file) if line.strip()]
        print(f"Loaded {len(results)} result lines from file")
    else:
        print("\nDownloading results...")
        results = download_results(batch_id, api_key)
        print(f"Downloaded {len(results)} result lines")

    if not results:
        print("No results to process.")
        return

    print("Storing resolved names to practices.data_axle_raw_name...")
    summary = store_results(results)

    print(f"\nResults:")
    print(f"  Stored (names written):         {summary['stored']}")
    print(f"    - Confirmed fabricated OK:     {summary['confirmed_fabricated_was_correct']}")
    print(f"    - New different name:          {summary['stored'] - summary['confirmed_fabricated_was_correct']}")
    print(f"  Null (not found):               {summary['null_name_returned']}")
    print(f"  Skipped (low confidence):       {summary['skipped_low_confidence']}")
    print(f"  Skipped (practice closed):      {summary['skipped_closed']}")
    print(f"  Errors:                         {summary['errors']}")
    print(f"\nProvider role breakdown:")
    for role, cnt in sorted(summary["provider_roles"].items()):
        print(f"  {role}: {cnt}")

    with open("/tmp/name_resolve_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nFull summary written to /tmp/name_resolve_summary.json")

    new_names = summary["stored"] - summary["confirmed_fabricated_was_correct"]
    if new_names > 0:
        print(f"\n{new_names} NEW practice names discovered. Next steps:")
        print(f"  1. Re-dedup:  python3 scrapers/dedup_practice_locations.py")
        print(f"  2. Re-sync:   python3 scrapers/sync_to_supabase.py --tables practice_locations")
    elif summary["confirmed_fabricated_was_correct"] > 0:
        print(f"\n{summary['confirmed_fabricated_was_correct']} fabricated names confirmed correct "
              f"(practice really is called that). Still re-dedup to pick them up.")
    else:
        print("\nNo new names to propagate.")


if __name__ == "__main__":
    main()
