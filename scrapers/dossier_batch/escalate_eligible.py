"""
escalate_eligible.py — Pass-2 Sonnet escalation for existing Pass-1 dossiers.

Closes the gap that audit B3 found: every dossier landed via the batch path
has `escalated=0` because `build_batch_requests()` is Pass-1 only and never
fires the conditional Sonnet step in `research_practice_deep()`.

This script:
  1. Reads existing rows from `practice_intel` in SQLite
  2. Re-runs `_should_escalate()` on each row's stored Pass-1 result
  3. Builds a Sonnet escalation batch for the qualifying subset
  4. Prints cost estimate and waits for confirmation (unless --yes)
  5. Submits the batch and writes the batch_id to /tmp/escalate_batch_id.txt

Usage:
    python3 scrapers/dossier_batch/escalate_eligible.py --dry-run
    python3 scrapers/dossier_batch/escalate_eligible.py --max 100
    python3 scrapers/dossier_batch/escalate_eligible.py --yes
"""
import argparse
import json
import os
import sys

ROOT = "/Users/suleman/dental-pe-tracker"
sys.path.insert(0, ROOT)
for raw in open(os.path.join(ROOT, ".env")):
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import sqlite3
from scrapers.research_engine import (
    ResearchEngine, MODEL_SONNET, ESCALATION_SYSTEM, MAX_TOKENS_SONNET,
)
from scrapers.database import DB_PATH


# Sonnet 4.6 batch rate ≈ $1.50 input / $7.50 output per Mtok (50% batch discount)
# Empirical Pass-2 cost from prior Sonnet runs: ~$0.27/practice
SONNET_COST_PER_PRACTICE = 0.27


def _should_escalate(r: dict) -> bool:
    """Mirror of ResearchEngine._should_escalate() — tightened 2026-04-26."""
    readiness = r.get("readiness", r.get("acquisition_readiness", "unknown"))
    if readiness in ("unlikely", "unknown", "low"):
        return False
    confidence = r.get("confidence", "low")
    if readiness in ("high", "medium") and confidence != "high":
        return True
    greens = r.get("green_flags") or []
    verification = r.get("verification") or {}
    evidence = (verification.get("evidence_quality") or "").lower()
    if (isinstance(greens, list) and len(greens) >= 5
            and evidence in ("partial", "insufficient")):
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="List candidates without submitting")
    ap.add_argument("--max", type=int, default=None,
                    help="Cap number of escalations submitted")
    ap.add_argument("--yes", action="store_true",
                    help="Skip cost confirmation prompt")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT pi.npi, pi.raw_json, pi.escalated,
               p.practice_name, p.address, p.city, p.state, p.zip
          FROM practice_intel pi
          JOIN practices p ON p.npi = pi.npi
         WHERE pi.escalated = 0
    """).fetchall()
    conn.close()

    candidates = []
    for r in rows:
        try:
            data = json.loads(r["raw_json"]) if r["raw_json"] else {}
        except Exception:
            continue
        if _should_escalate(data):
            candidates.append({
                "npi": r["npi"],
                "name": r["practice_name"] or "",
                "address": r["address"] or "",
                "city": r["city"] or "",
                "state": r["state"] or "",
                "zip": r["zip"] or "",
                "pass1": data,
            })

    print(f"Pool: {len(rows)} Pass-1 dossiers in SQLite (escalated=0)")
    print(f"Eligible for escalation: {len(candidates)}")

    if args.max:
        candidates = candidates[: args.max]
        print(f"Capped at --max {args.max}")

    est = len(candidates) * SONNET_COST_PER_PRACTICE
    print(f"Estimated Sonnet cost: ${est:.2f} (@ ${SONNET_COST_PER_PRACTICE}/practice)")

    if args.dry_run:
        print("\n--dry-run: first 10 candidates ↓")
        for c in candidates[:10]:
            print(f"  {c['npi']:>10} | {c['zip']} | "
                  f"readiness={c['pass1'].get('readiness') or c['pass1'].get('acquisition_readiness')} | "
                  f"conf={c['pass1'].get('confidence')} | "
                  f"greens={len(c['pass1'].get('green_flags') or [])}")
        return

    if not candidates:
        print("Nothing to escalate. Exit.")
        return

    if not args.yes:
        ans = input(f"\nSubmit {len(candidates)} Sonnet escalations (~${est:.2f})? [y/N]: ").strip().lower()
        if ans != "y":
            print("Cancelled.")
            return

    eng = ResearchEngine(model=MODEL_SONNET, max_tokens=MAX_TOKENS_SONNET)
    reqs = []
    for c in candidates:
        msg = (f"Initial scan for {c['name']} at {c['address']}, "
               f"{c['city']} {c['state']} {c['zip']}:\n"
               f"{json.dumps(c['pass1'], default=str)[:3000]}\n\n"
               "Deeper research needed. Verify Google reviews, search for hiring "
               "signals, news, technology investments, real estate at this address. "
               "Return same JSON structure with verified/deeper data.")
        reqs.append({
            "custom_id": f"esc_{c['npi']}",
            "params": {
                "model": MODEL_SONNET,
                "max_tokens": MAX_TOKENS_SONNET,
                "system": [{"type": "text", "text": ESCALATION_SYSTEM,
                            "cache_control": {"type": "ephemeral"}}],
                "tools": [{"type": "web_search_20250305",
                           "name": "web_search", "max_uses": 5}],
                "messages": [{"role": "user", "content": msg}],
                "tool_choice": {"type": "tool", "name": "web_search"},
            },
        })

    print(f"\nSubmitting {len(reqs)} Sonnet escalation requests...")
    result = eng.submit_batch(reqs)
    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    batch_id = result.get("batch_id")
    print(f"\n✅ ESCALATION BATCH SUBMITTED: {batch_id}")
    print(f"   {result.get('count')} requests, status={result.get('status')}")
    with open("/tmp/escalate_batch_id.txt", "w") as f:
        f.write(batch_id)
    print(f"   batch_id saved to /tmp/escalate_batch_id.txt")
    print("\nNext: poll with `python3 scrapers/dossier_batch/poll.py` "
          "after updating it to read /tmp/escalate_batch_id.txt and merge "
          "the Sonnet result into the existing Pass-1 row "
          "(set escalated=1 in practice_intel).")


if __name__ == "__main__":
    main()
