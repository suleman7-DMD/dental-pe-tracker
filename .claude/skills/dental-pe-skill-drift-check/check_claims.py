#!/usr/bin/env python3
"""Verify every volatile claim in the dental-pe-* skills against the live repo.

Read-only by construction: the DB is opened with a mode=ro URI; filesystem
checks only glob/read/parse (stdlib ast for ORM introspection, no imports of
project code). Exit 0 = all claims hold; exit 1 = drift found.

Claim classes:
  floor    — guarded safety minimum; a drop is an INCIDENT, never doc debt
  snapshot — dated state; drift means the skill text needs a dated refresh
  report   — volatile by declaration; printed, never judged

Modes:
  (default)  full check: DB + files + AST + frontend
  --no-db    skip DB-dependent claims (sql / queue_recon, and derived claims
             whose inputs were skipped). For CI runners: the SQLite DB lives
             only on the pipeline Mac and is not in git. Claims marked
             local_only (targets inside the nested dental-pe-nextjs repo,
             which is gitignored here) auto-SKIP with a printed reason when
             the path is absent; a missing path on any other claim is DRIFT.
             A SKIP is not a PASS — only the full local run is complete
             coverage, and the output says so.

Manifest ordering contract: a `derived` claim must appear AFTER every claim
it references.
"""
import ast
import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(__file__).with_name("claims.json")

DB_KINDS = {"sql", "queue_recon"}


def orm_class_columns(path):
    """Class-level assigned names per ORM class in a file, via AST.

    Catches both `name = Column(...)` and annotated assignments. This is the
    strong form of the old grep check: it proves the attribute is defined ON
    the model class, not merely that the string appears somewhere in the file.
    """
    tree = ast.parse((ROOT / path).read_text())
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            names = set()
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    names.update(t.id for t in stmt.targets if isinstance(t, ast.Name))
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    names.add(stmt.target.id)
            out[node.name] = names
    return out


def queue_reconstruction(db, m):
    """Re-derive the P1' census queue decomposition from scratch.

    Canonical predicate (matches merge_and_score.py GP bucketing): IL by
    pl.state — NOT by watched_zips join, which double-counts one location
    whose zip is watched but whose state isn't IL — GP-eligible entity
    classes, non-residential. Every stated queue number must reproduce from
    this exact predicate; if it stops reproducing, the skills' queue math is
    stale or the predicate itself changed (either way: investigate, don't
    edit numbers blind).
    """
    base = ("FROM practice_locations pl WHERE pl.state='IL' "
            "AND (pl.entity_classification IS NULL OR pl.entity_classification "
            "NOT IN ('specialist','non_clinical','da_unverified','duplicate_location')) "
            "AND (pl.is_likely_residential=0 OR pl.is_likely_residential IS NULL)")
    rows = db.execute("SELECT pl.location_id, pl.primary_npi, pl.org_npi " + base +
                      " AND pl.ownership_tier IS NULL").fetchall()
    triage = json.loads((ROOT / m["triage_file"]).read_text())
    tids = {t["location_id"] for t in triage}
    never = [r for r in rows if r[0] not in tids]
    synth = [r for r in never
             if str(r[1] or "").startswith(("DA_", "DIR_")) or str(r[2] or "").startswith(("DA_", "DIR_"))]
    return {
        "untiered": len(rows),
        "in_triage": len(rows) - len(never),
        "never": len(never),
        "synthetic": len(synth),
        "real": len(never) - len(synth),
    }


def check(db, c, m, cache, actuals):
    kind = c["kind"]
    if kind == "sql":
        row = db.execute(c["arg"]).fetchone()
        return row[0] if row else None
    if kind == "glob":
        return len(glob.glob(str(ROOT / c["arg"])))
    if kind == "grep":
        text = (ROOT / c["path"]).read_text(errors="replace")
        return len(re.findall(c["arg"], text))
    if kind == "grep_dir":
        # count of files under dir (by extension) whose text matches the regex
        pat = re.compile(c["arg"])
        exclude = c.get("exclude", "")
        n = 0
        for ext in c.get("exts", [".ts", ".tsx"]):
            for p in (ROOT / c["dir"]).rglob(f"*{ext}"):
                if exclude and exclude in str(p):
                    continue
                if pat.search(p.read_text(errors="replace")):
                    n += 1
        return n
    if kind == "lines":
        return sum(1 for _ in (ROOT / c["path"]).open(errors="replace"))
    if kind == "json_len":
        return len(json.loads((ROOT / c["path"]).read_text()))
    if kind == "json_tally":
        rows = json.loads((ROOT / c["path"]).read_text())
        return sum(1 for r in rows if r.get(c["field"]) == c["value"])
    if kind == "derived":
        # arg = "id + id - id ..." over already-computed actuals, left to right
        val, op = None, "+"
        for tok in c["arg"].split():
            if tok in "+-":
                op = tok
                continue
            ref = actuals.get(tok)
            if not isinstance(ref, int):
                raise ValueError(f"derived ref {tok!r} unavailable (got {ref!r})")
            val = ref if val is None else (val + ref if op == "+" else val - ref)
        return val
    if kind == "queue_recon":
        if "queue" not in cache:
            cache["queue"] = queue_reconstruction(db, m)
        return cache["queue"][c["metric"]]
    if kind == "orm_columns":
        key = f"orm:{c['path']}"
        if key not in cache:
            cache[key] = orm_class_columns(c["path"])
        return sum(1 for cls in c["classes"] for col in c["columns"]
                   if col in cache[key].get(cls, set()))
    raise ValueError(f"unknown claim kind: {kind}")


def main():
    no_db = "--no-db" in sys.argv
    m = json.loads(MANIFEST.read_text())
    db = None
    if not no_db:
        db = sqlite3.connect(f"file:{ROOT / m['db']}?mode=ro", uri=True)
    drifted, skipped, cache, actuals = [], [], {}, {}
    print(f"{'CLAIM':32} {'CLASS':9} {'EXPECTED':>9} {'ACTUAL':>9}  STATUS")
    for c in m["claims"]:
        cid = c["id"]
        exp = c.get("expected", c.get("expected_min", "-"))
        skip = None
        if no_db:
            if c["kind"] in DB_KINDS:
                skip = "needs local DB"
            elif c["kind"] == "derived" and any(
                    t not in "+-" and actuals.get(t) is None for t in c["arg"].split()):
                skip = "input skipped"
        if skip is None and c.get("local_only"):
            target = ROOT / (c.get("path") or c.get("dir"))
            if not target.exists():
                skip = "local-only path absent"
        if skip:
            skipped.append(cid)
            actuals[cid] = None
            print(f"{cid:32} {c.get('class', '-'):9} {str(exp):>9} {'-':>9}  SKIP ({skip})")
            continue
        try:
            actual = check(db, c, m, cache, actuals)
        except Exception as e:  # noqa: BLE001 - a broken check IS a drift signal
            actual = f"ERR:{e}"
        actuals[cid] = actual if isinstance(actual, int) else None
        if c.get("report_only"):
            status = "REPORT"
        elif isinstance(actual, str) or actual is None:
            status = "DRIFT"
        elif "expected_min" in c:
            status = "PASS" if actual >= c["expected_min"] else "DRIFT"
        else:
            status = "PASS" if actual == c["expected"] else "DRIFT"
        if status == "DRIFT":
            drifted.append(cid)
        print(f"{cid:32} {c.get('class', '-'):9} {str(exp):>9} {str(actual):>9}  {status}")
    if skipped:
        print(f"\nSKIPPED {len(skipped)} claim(s) in this mode: {', '.join(skipped)}")
        print("A SKIP is not a PASS — full coverage requires the local run on the pipeline Mac.")
    if drifted:
        print(f"\nDRIFT in {len(drifted)} claim(s): {', '.join(drifted)}")
        print("Consult each claim's on_drift note in claims.json before touching anything.")
        print("floor-class claims dropping = incident (load dental-pe-failure-archaeology), not doc debt.")
        return 1
    print(f"\nAll {len(m['claims']) - len(skipped)} checked claims verified ({m['last_verified']} baseline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
