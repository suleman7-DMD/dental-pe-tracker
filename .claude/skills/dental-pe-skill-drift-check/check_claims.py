#!/usr/bin/env python3
"""Verify every volatile claim in the dental-pe-* skills against the live repo.

Read-only by construction: the DB is opened with a mode=ro URI; filesystem
checks only glob/read. Exit 0 = all claims hold; exit 1 = drift found.
"""
import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(__file__).with_name("claims.json")


def check(db, c):
    kind = c["kind"]
    if kind == "sql":
        row = db.execute(c["arg"]).fetchone()
        return row[0] if row else None
    if kind == "glob":
        return len(glob.glob(str(ROOT / c["arg"])))
    if kind == "grep":
        text = (ROOT / c["path"]).read_text(errors="replace")
        return len(re.findall(c["arg"], text))
    raise ValueError(f"unknown claim kind: {kind}")


def main():
    m = json.loads(MANIFEST.read_text())
    db = sqlite3.connect(f"file:{ROOT / m['db']}?mode=ro", uri=True)
    drifted = []
    print(f"{'CLAIM':30} {'EXPECTED':>10} {'ACTUAL':>10}  STATUS")
    for c in m["claims"]:
        try:
            actual = check(db, c)
        except Exception as e:  # noqa: BLE001 - a broken check IS a drift signal
            actual = f"ERR:{e}"
        if c.get("report_only"):
            status = "REPORT"
        elif isinstance(actual, str):
            status = "DRIFT"
        elif "expected_min" in c:
            status = "PASS" if actual >= c["expected_min"] else "DRIFT"
        else:
            status = "PASS" if actual == c["expected"] else "DRIFT"
        if status == "DRIFT":
            drifted.append(c["id"])
        exp = c.get("expected", c.get("expected_min", "-"))
        print(f"{c['id']:30} {str(exp):>10} {str(actual):>10}  {status}")
    if drifted:
        print(f"\nDRIFT in {len(drifted)} claim(s): {', '.join(drifted)}")
        print("Consult each claim's on_drift note in claims.json before touching anything.")
        print("Guarded invariants dropping = incident (load dental-pe-failure-archaeology), not doc debt.")
        return 1
    print(f"\nAll {len(m['claims'])} claims verified against the live repo ({m['last_verified']} baseline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
