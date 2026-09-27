"""Scoped physical-address parser for the office census staging adapter.

Pure functions, no I/O. This is deliberately NOT the shared normalizer
(`dedup_practice_locations.normalize_address`, a.k.a. `office_census.NORM`):
that one feeds `location_id` and existing candidate IDs and must never change,
but it is lossy (its suite regex eats `ste...`/`fl...` prefixes, so
"1200 Sterling Ave" -> "1200 ave"). This parser keeps street names intact and
separates the house number, street and unit so that suites can be compared.

Rules (see data/office_census/COMPLETION_PLAN_2026-09-26.md §7.B):
- A trailing ", City, IL 6xxxx" (or " IL 6xxxx") is stripped.
- Unit designators are peeled ONLY as whole tokens at the END of the address,
  possibly repeated ("Fl 2 Ste 200"). Street words that merely start with a
  designator (Sterling, Flossmoor, Stetson, Aptakisic, Unity) are untouched.
- Suffixes and directionals are normalized identically on both sides; a few
  narrow, documented aliases are applied (ALIASES).
- Unit values keep their leading zeros ("01" != "1").
"""
from __future__ import annotations

import re

RULE_VERSION = "office-census-address-2026-09-26.1"

DIRECTIONALS = {
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
    "n": "n", "s": "s", "e": "e", "w": "w", "ne": "ne", "nw": "nw", "se": "se", "sw": "sw",
}

SUFFIXES = {
    "street": "st", "st": "st", "str": "st",
    "avenue": "ave", "ave": "ave", "av": "ave", "aven": "ave", "avn": "ave",
    "road": "rd", "rd": "rd",
    "drive": "dr", "dr": "dr", "drv": "dr",
    "lane": "ln", "ln": "ln",
    "court": "ct", "ct": "ct", "crt": "ct",
    "place": "pl", "pl": "pl",
    "parkway": "pkwy", "pkwy": "pkwy", "pky": "pkwy",
    "highway": "hwy", "hwy": "hwy", "hiway": "hwy",
    "boulevard": "blvd", "blvd": "blvd", "boul": "blvd",
    "circle": "cir", "cir": "cir",
    "square": "sq", "sq": "sq",
    "terrace": "ter", "ter": "ter",
    "trail": "trl", "trl": "trl",
    "plaza": "plz", "plz": "plz",
    "center": "ctr", "centre": "ctr", "ctr": "ctr",
    "expressway": "expy", "expy": "expy",
    "crossing": "xing", "xing": "xing",
    "way": "way",
    "route": "rte", "rte": "rte", "rt": "rte",
    "pike": "pike", "turnpike": "tpke", "tpke": "tpke",
    "row": "row", "walk": "walk", "path": "path", "run": "run",
}
# Suffix values after normalization (what may be dropped by the suffix-optional alias).
SUFFIX_VALUES = set(SUFFIXES.values()) - {"rte"}

# Narrow, documented aliases (token -> canonical). Applied to street tokens only.
ALIASES = {
    "saint": "st",        # "Saint Charles Rd" == "St Charles Rd"
    "mount": "mt",
    "fort": "ft",
    "heights": "hts",
    "arl": "arlington",   # Data Axle writes "N Arl Hts Rd" for Arlington Heights Rd
}

# Designators that take a value ("Ste 200", "# 104", "Fl 3").
VALUE_DESIGNATORS = {
    "#": "#", "ste": "suite", "suite": "suite", "unit": "unit", "apt": "apt",
    "apartment": "apt", "fl": "floor", "flr": "floor", "floor": "floor",
    "rm": "room", "room": "room", "bldg": "bldg", "building": "bldg",
    "spc": "space", "space": "space", "ofc": "office", "office": "office",
    "dept": "dept", "frnt": "front", "lowr": "lower", "uppr": "upper",
}
# Ordinary English words that can also be street words: their value must look like
# a unit (contain a digit, or be one or two characters) before they are peeled.
WEAK_DESIGNATORS = {"floor", "building", "space", "office", "room", "apartment", "suite", "unit"}
# Designators that stand alone at the end ("Rear", "Frnt"). Abbreviations only, so
# that a street called "... Front" or "... Lower" is not mistaken for a unit.
STANDALONE_DESIGNATORS = {
    "frnt": "FRNT", "rear": "REAR", "lowr": "LOWR", "uppr": "UPPR", "bsmt": "BSMT",
    "lbby": "LBBY", "ph": "PH",
}
# Unit kinds that are containers rather than the office's own unit.
CONTAINER_KINDS = {"floor", "bldg"}
# Tokens after which a bare trailing number is a route number, not a unit.
ROUTE_TOKENS = {"hwy", "rte", "us", "il", "state", "county", "cr", "sr", "tpke", "pike"}


# Designators that are unambiguous abbreviations: any following token is the unit ("# W", "Ste E").
STRONG_DESIGNATORS = {"#", "ste", "unit", "apt", "fl", "flr", "rm"}


def _looks_like_unit_value(designator, value):
    v = value.lower()
    if designator in STRONG_DESIGNATORS:
        return True
    if designator in WEAK_DESIGNATORS and not (re.search(r"\d", v) or len(v) <= 2):
        return False
    # "Office Ctr", "Bldg Ave": a street suffix, directional or alias word is not a unit value
    if not re.search(r"\d", v) and (v in SUFFIXES or v in DIRECTIONALS or v in ALIASES):
        return False
    return True


_CITY_TAIL = re.compile(
    r"(?:,\s*[A-Za-z][A-Za-z .'\-]*)?,?\s*\b(?:IL|ILL|ILLINOIS)\b\.?\s*(?:\d{5}(?:-?\d{4})?)?\s*$",
    re.I)
_ZIP_TAIL = re.compile(r",?\s*\b6\d{4}(?:-?\d{4})?\s*$")
_HOUSE = re.compile(r"^(?:\d+[a-z]?(?:-\d+[a-z]?)?|\d+[nsew]\d+[a-z]?)$", re.I)  # incl. DuPage grid "18W435"
_FRACTION = re.compile(r"^\d/\d$")
_ORDINAL = re.compile(r"^(\d+)(?:st|nd|rd|th)$", re.I)
_PO_BOX = re.compile(r"\b(?:p\.?\s*o\.?\s*box|post\s+office\s+box|box\s+\d)", re.I)


def _norm_unit_value(value):
    v = str(value or "").strip().upper()
    v = v.lstrip("#").strip()
    v = v.strip("-.,")
    return v or None


def _norm_street_token(tok):
    t = tok.lower()
    if t in ALIASES:
        return ALIASES[t]
    if t in DIRECTIONALS:
        return DIRECTIONALS[t]
    if t in SUFFIXES:
        return SUFFIXES[t]
    return t


def parse_unit(raw):
    """Parse a stand-alone suite string ('Ste 401', '#2B', 'Suite 200', '401', 'FL3')."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    toks = re.sub(r"[.,]", " ", s).split()
    toks = [t for t in toks if t.lower() not in VALUE_DESIGNATORS or len(toks) == 1]
    if len(toks) == 1:
        m = re.match(r"^(?:#|fl|flr|ste|suite|unit|rm)\s*([0-9][\w-]*)$", toks[0], re.I)
        if m:
            return _norm_unit_value(m.group(1))
    return _norm_unit_value(" ".join(toks))


def _strip_city_tail(s):
    prev = None
    while prev != s:
        prev = s
        s = _CITY_TAIL.sub("", s).strip()
        s = _ZIP_TAIL.sub("", s).strip()
        s = s.rstrip(",").strip()
    return s


def parse_physical_address(raw, explicit_suite=None):
    """Split a raw street address into house, street and unit.

    Returns {"raw", "house", "street", "unit", "unit_parts", "flags"}. `street` is
    the normalized street (directional + name + suffix), lowercase. `unit` is the
    office-level unit (a suite/#/unit/room value if present, otherwise a floor or
    building value), uppercase with leading zeros preserved. `explicit_suite`, when
    given, is authoritative for the unit (a disagreement is flagged).
    """
    out = {"raw": raw, "house": None, "street": None, "unit": None,
           "unit_parts": [], "flags": []}
    flags = out["flags"]
    s = "" if raw is None else str(raw).strip()
    if s.lower() in ("", "nan", "none", "null"):
        flags.append("blank_address")
        s = ""
    if s and _PO_BOX.search(s):
        flags.append("po_box")
    s = _strip_city_tail(s)
    s = s.replace(",", " ").replace(".", " ")
    s = re.sub(r"#\s*", " # ", s)          # "#104" and "# 104" become "# 104"
    toks = s.split()

    # house number
    if toks and _HOUSE.match(toks[0]):
        house = toks[0].upper()
        toks = toks[1:]
        if toks and _FRACTION.match(toks[0]):
            house += " " + toks[0]
            toks = toks[1:]
        out["house"] = house
    elif s:
        flags.append("no_house_number")

    # peel units from the end, whole tokens only
    parts = []  # (kind, value), outermost last
    while len(toks) >= 2:
        last, prev = toks[-1], toks[-2]
        ll, pl = last.lower(), prev.lower()
        if pl in VALUE_DESIGNATORS and ll not in VALUE_DESIGNATORS and _looks_like_unit_value(pl, ll):
            parts.append((VALUE_DESIGNATORS[pl], last))
            toks = toks[:-2]
            continue
        if ll in STANDALONE_DESIGNATORS and pl not in VALUE_DESIGNATORS:
            parts.append(("position", STANDALONE_DESIGNATORS[ll]))
            toks = toks[:-1]
            continue
        if ll in ("fl", "flr", "floor") and _ORDINAL.match(prev):
            parts.append(("floor", _ORDINAL.match(prev).group(1)))
            toks = toks[:-2]
            continue
        if ll in VALUE_DESIGNATORS and ll not in WEAK_DESIGNATORS:   # dangling ("... Ave Ste")
            flags.append("dangling_designator")
            toks = toks[:-1]
            continue
        break
    # A bare short token with a digit after a street suffix ("... Ave 914").
    if (not parts and len(toks) >= 3 and re.search(r"\d", toks[-1]) and len(toks[-1]) <= 5
            and _norm_street_token(toks[-2]) in SUFFIX_VALUES
            and _norm_street_token(toks[-2]) not in ROUTE_TOKENS and not _ORDINAL.match(toks[-1])):
        parts.append(("bare", toks[-1]))
        toks = toks[:-1]
        flags.append("bare_trailing_unit")

    street_toks = [_norm_street_token(t) for t in toks]
    street = " ".join(street_toks).strip() or None
    out["street"] = street
    if street is None and out["house"]:
        flags.append("no_street")
    if street and not [t for t in street_toks if t not in SUFFIX_VALUES]:
        flags.append("street_degenerate")   # e.g. the lossy NORM output "1200 ave"

    parts = list(reversed(parts))          # innermost-first reading order
    out["unit_parts"] = [{"kind": k, "value": _norm_unit_value(v)} for k, v in parts]
    office = [p for p in out["unit_parts"] if p["kind"] not in CONTAINER_KINDS and p["value"]]
    container = [p for p in out["unit_parts"] if p["kind"] in CONTAINER_KINDS and p["value"]]
    if office:
        out["unit"] = office[-1]["value"]
        if len({p["value"] for p in office}) > 1:
            flags.append("multiple_units_in_address")
    elif container:
        out["unit"] = container[-1]["value"]
        flags.append("unit_is_" + container[-1]["kind"])
    if explicit_suite is not None and str(explicit_suite).strip().lower() not in ("", "nan", "none", "null"):
        ex = parse_unit(explicit_suite)
        if ex:
            if out["unit"] and out["unit"] != ex:
                flags.append("explicit_suite_differs_from_address")
            out["unit"] = ex
            flags.append("unit_from_explicit_suite")
    return out


def _street_of(x):
    return x.get("street") if isinstance(x, dict) else x


def street_relation(a, b):
    """'same' | 'suffix_inferred' | None for two parsed addresses (house + street)."""
    if not a or not b or not a.get("house") or not b.get("house"):
        return None
    if a["house"] != b["house"]:
        return None
    sa, sb = _street_of(a), _street_of(b)
    if not sa or not sb:
        return None
    if sa == sb:
        return "same"
    ta, tb = sa.split(), sb.split()
    # Narrow alias: one side omits the street suffix ("3115 N Broadway" vs "3115 N Broadway St").
    if len(ta) == len(tb) + 1 and ta[-1] in SUFFIX_VALUES and ta[:-1] == tb and tb[-1] not in SUFFIX_VALUES:
        return "suffix_inferred"
    if len(tb) == len(ta) + 1 and tb[-1] in SUFFIX_VALUES and tb[:-1] == ta and ta[-1] not in SUFFIX_VALUES:
        return "suffix_inferred"
    return None


def same_street(a, b):
    """Same house number and normalized street (with the suffix-optional alias)."""
    return street_relation(a, b) is not None


def unit_relation(a, b):
    """'same' (both explicit, equal) | 'unknown' (at least one missing) | 'conflict'."""
    ua = a.get("unit") if isinstance(a, dict) else a
    ub = b.get("unit") if isinstance(b, dict) else b
    if not ua or not ub:
        return "unknown"
    return "same" if ua == ub else "conflict"


def units_compatible(a, b):
    """True unless both units are explicit and different. Unknown is compatible;
    call unit_relation() to see whether the compatibility was 'unknown'."""
    return unit_relation(a, b) != "conflict"


def near_miss(a, b):
    """Hint only: same house number and first 4 letters of the street name."""
    if not a or not b or not a.get("house") or a.get("house") != b.get("house"):
        return False
    def name4(p):
        toks = [t for t in (p.get("street") or "").split()
                if t not in DIRECTIONALS.values() and t not in SUFFIX_VALUES]
        return toks[0][:4] if toks else ""
    n = name4(a)
    return bool(n) and n == name4(b)
