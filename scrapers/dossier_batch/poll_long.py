"""
Long-poll variant of poll.py — same retrieve+validate+store path, but waits up
to 6 hours instead of 90 min. Anthropic batch service was deeply queued on
2026-04-26 (msgbatch_011x71o8JZbwdtsBiBudWJ3D sat at 0/2000 succeeded for 96+
min before the original poll.py hit its 90-min cap). Use this when the batch
is genuinely stuck in queue rather than failing — `request_counts.errored`
must be 0 before launching this.

Skips the embedded sync_to_supabase.py call. Run upsert_practice_intel.py
manually after this finishes — the full sync has been timing out on 14k row
batches.
"""
import json
import os
import sys
import time
from datetime import datetime

ROOT = "/Users/suleman/dental-pe-tracker"
sys.path.insert(0, ROOT)
for raw in open(os.path.join(ROOT, ".env")):
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import requests as req
from scrapers.research_engine import ResearchEngine
from scrapers.weekly_research import validate_dossier
from scrapers.intel_database import store_practice_intel


BATCH_ID = open("/tmp/full_batch_id.txt").read().strip()
SUMMARY_PATH = "/tmp/full_batch_summary.json"
MAX_POLLS = 720  # 6 hours @ 30s


def main():
    eng = ResearchEngine()
    summary = {
        "batch_id": BATCH_ID,
        "started_polling": datetime.now().isoformat(),
        "polls": 0,
        "stored": 0,
        "rejected": 0,
        "errored": 0,
        "rejection_reasons": {},
        "completed": False,
        "items": [],
    }

    print(f"Polling {BATCH_ID} (max {MAX_POLLS * 30 / 60:.0f} min)...", flush=True)
    for i in range(MAX_POLLS):
        summary["polls"] = i + 1
        st = eng.check_batch(BATCH_ID)
        if "error" in st:
            summary["error"] = st["error"]
            break
        proc = st.get("processing_status", "unknown")
        rc = st.get("request_counts", {})
        if proc == "ended":
            summary["completed"] = True
            summary["request_counts"] = rc
            break
        if i % 5 == 0:
            print(
                f"[poll {i+1}] status={proc} "
                f"succeeded={rc.get('succeeded',0)}/{sum(rc.values())} "
                f"errored={rc.get('errored',0)}",
                flush=True,
            )
        time.sleep(30)
    else:
        summary["error"] = f"timeout after {MAX_POLLS * 30 / 60:.0f} min"

    if not summary["completed"]:
        with open(SUMMARY_PATH, "w") as f:
            json.dump(summary, f, indent=2)
        print("FAILED to complete:", summary.get("error"))
        return

    print("Batch ended. Pulling results...", flush=True)
    key = os.environ["ANTHROPIC_API_KEY"]
    resp = req.get(
        f"https://api.anthropic.com/v1/messages/batches/{BATCH_ID}/results",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        stream=True, timeout=600,
    )
    total_in = total_out = total_cache_r = total_cache_c = total_search = 0
    for raw in resp.iter_lines():
        if not raw:
            continue
        j = json.loads(raw)
        cid = j.get("custom_id", "")
        npi = cid.replace("practice_", "")
        msg = j.get("result", {}).get("message", {})
        u = msg.get("usage", {}) or {}
        inp = u.get("input_tokens", 0)
        out = u.get("output_tokens", 0)
        cr = u.get("cache_read_input_tokens", 0)
        cc = u.get("cache_creation_input_tokens", 0)
        sr = (u.get("server_tool_use", {}) or {}).get("web_search_requests", 0)
        total_in += inp
        total_out += out
        total_cache_r += cr
        total_cache_c += cc
        total_search += sr

        text_parts = [b["text"] for b in msg.get("content", []) if b.get("type") == "text"]
        text = "\n".join(text_parts).strip()
        data = eng._parse_json(text) or {}
        if "_meta" not in data:
            data["_meta"] = {
                "model": msg.get("model", "claude-haiku-4-5-20251001"),
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read": cr,
                "cost_usd": ((inp * 0.50 + out * 2.50 + cr * 0.05) / 1e6) + sr * 0.01,
            }

        entry = {
            "npi": npi,
            "searches": sr,
            "tokens_in": inp,
            "tokens_out": out,
            "cache_read": cr,
            "verification_quality": (data.get("verification") or {}).get("evidence_quality"),
        }

        if not data or "error" in data:
            summary["errored"] += 1
            entry["error"] = (data or {}).get("error", "no_parse")
            summary["items"].append(entry)
            continue

        ok, reason = validate_dossier(npi, data)
        entry["validation"] = "pass" if ok else reason
        if not ok:
            summary["rejected"] += 1
            summary["rejection_reasons"][reason] = summary["rejection_reasons"].get(reason, 0) + 1
            summary["items"].append(entry)
            continue

        try:
            store_practice_intel(npi, data)
            summary["stored"] += 1
        except Exception as e:
            summary["errored"] += 1
            entry["storage_error"] = str(e)[:200]
        summary["items"].append(entry)

    token_cost = (total_in * 0.50 + total_out * 2.50 +
                  total_cache_r * 0.05 + total_cache_c * 0.625) / 1e6
    search_cost = total_search * 0.01
    summary["totals"] = {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cache_read_tokens": total_cache_r,
        "cache_create_tokens": total_cache_c,
        "web_searches": total_search,
        "token_cost_usd": round(token_cost, 4),
        "search_cost_usd": round(search_cost, 4),
        "total_cost_usd": round(token_cost + search_cost, 4),
    }
    summary["finished"] = datetime.now().isoformat()

    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(
        f"DONE. stored={summary['stored']} rejected={summary['rejected']} "
        f"errored={summary['errored']} cost=${summary['totals']['total_cost_usd']:.2f}"
    )
    print("NOTE: skipped embedded sync_to_supabase.py — run upsert_practice_intel.py manually.")


if __name__ == "__main__":
    main()
