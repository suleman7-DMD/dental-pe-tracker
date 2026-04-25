#!/usr/bin/env python3
"""
poll_zip_batches.py — Wait for ZIP re-research batches to complete, then auto-retrieve.

Usage:
    python3 scrapers/dossier_batch/poll_zip_batches.py

Batches:
    msgbatch_01NcU3qqdVtcke3jejbiriCC  (Chicagoland, 269 ZIPs)
    msgbatch_01GNMztDwMRitSAqtXpvDeRq  (Boston, 21 ZIPs)

Writes results to data/dental_pe_tracker.db via validate_zip_dossier + store_zip_intel.
Writes summary to /tmp/zip_batch_summary.json when done.
"""
import json
import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests

BATCHES = [
    ("msgbatch_01NcU3qqdVtcke3jejbiriCC", "Chicagoland", 269),
    ("msgbatch_01GNMztDwMRitSAqtXpvDeRq", "Boston", 21),
]

POLL_INTERVAL_SECS = 60
MAX_POLLS = 90  # 90 minutes max

SUMMARY_PATH = "/tmp/zip_batch_summary.json"
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "dental_pe_tracker.db")


def get_batch_status(batch_id: str, api_key: str) -> dict:
    r = requests.get(
        f"https://api.anthropic.com/v1/messages/batches/{batch_id}",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "message-batches-2024-09-24",
        },
        timeout=30,
    )
    return r.json()


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    print(f"[zip-batch-poller] Starting. Will poll every {POLL_INTERVAL_SECS}s up to {MAX_POLLS} times.")
    print(f"[zip-batch-poller] DB: {DB_PATH}")
    print()

    for poll_num in range(1, MAX_POLLS + 1):
        all_ended = True
        for batch_id, label, expected in BATCHES:
            status = get_batch_status(batch_id, api_key)
            proc = status.get("processing_status", "unknown")
            counts = status.get("request_counts", {})
            print(f"[{poll_num}] {label} ({batch_id[:24]}...): {proc} | proc={counts.get('processing', '?')} ok={counts.get('succeeded', '?')} err={counts.get('errored', '?')}")
            if proc != "ended":
                all_ended = False

        if all_ended:
            print("\n[zip-batch-poller] Both batches ENDED. Starting retrieval...")
            break

        if poll_num < MAX_POLLS:
            time.sleep(POLL_INTERVAL_SECS)
    else:
        print(f"\n[zip-batch-poller] Timeout after {MAX_POLLS} polls ({MAX_POLLS * POLL_INTERVAL_SECS / 60:.0f} min). Check status manually:")
        for batch_id, label, _ in BATCHES:
            print(f"  python3 scrapers/qualitative_scout.py --retrieve {batch_id}")
        sys.exit(1)

    # Both batches ended — retrieve them
    summary = {"batches": {}, "total_stored": 0, "total_rejected": 0, "total_failed": 0}

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    for batch_id, label, _ in BATCHES:
        print(f"\n[zip-batch-poller] Retrieving {label} ({batch_id})...")
        result = subprocess.run(
            [sys.executable, "scrapers/qualitative_scout.py", "--retrieve", batch_id, "--db", DB_PATH],
            capture_output=True, text=True, cwd=repo_root
        )
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr[:500])
        summary["batches"][label] = {
            "batch_id": batch_id,
            "return_code": result.returncode,
            "stdout_tail": result.stdout[-2000:],
        }

    # Post-retrieval count
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM zip_qualitative_intel WHERE cost_usd > 0")
        total_stored = cur.fetchone()[0]
        conn.close()
        summary["zip_qualitative_intel_with_cost"] = total_stored
        print(f"\n[zip-batch-poller] zip_qualitative_intel rows with cost_usd > 0: {total_stored}")
    except Exception as e:
        print(f"[zip-batch-poller] Could not query DB post-retrieval: {e}")

    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[zip-batch-poller] Summary written to {SUMMARY_PATH}")

    # Sync to Supabase
    print("\n[zip-batch-poller] Running sync_to_supabase.py...")
    sync_result = subprocess.run(
        [sys.executable, "scrapers/sync_to_supabase.py"],
        capture_output=True, text=True, cwd=repo_root, timeout=300
    )
    if sync_result.returncode == 0:
        print("[zip-batch-poller] Sync succeeded.")
    else:
        print(f"[zip-batch-poller] Sync exit code {sync_result.returncode}. Check DNS/Supabase connectivity.")
        print("  STDERR tail:", sync_result.stderr[-500:])
        print("  Run manually: python3 scrapers/sync_to_supabase.py")


if __name__ == "__main__":
    main()
