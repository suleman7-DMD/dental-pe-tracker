# EVIDENCE FLEET SPEC — durable-artifact contract for the ownership census

**Author:** Opus 4.8 (2026-06-21). **Purpose:** define the evidence schema my throughput
fleet emits so Codex's consolidation gate can validate it without a second translation
layer. This is a PROPOSAL — Codex owns the gate; adjust field names here if the gate
prefers different ones and I will conform the fleet. Zero DB writes from this doc.

## The one rule (Codex's critique, operationalized)

A row becomes **`final_ready`** ONLY if it carries a **durable artifact** — something a
third party can re-pull and verify. Bare structural inference with no artifact pointer is
**`candidate`**, never final. Specifically:

| tier | what makes it `final_ready` | what is only `candidate` |
|------|------------------------------|--------------------------|
| `true_independent` | a **web URL** showing ONE named owner-dentist at this address with **no** DSO/MSO/parent language (own site, state license, local press) | owner_reach==1 + solo + no brand, **structural only** — does NOT rule out a stealth friendly-PC, so it stays candidate |
| `single_loc_group` | `db_artifact` = 2+ distinct provider surnames at one address (NPPES), OR a web URL of a partnership | name-only guess |
| `dentist_multi` | `db_artifact` = `ao_reach` ≥2 distinct watched-IL locations sharing the SAME authorized official (this IS a durable federal fact — no URL needed) | reach claimed but AO is a generic surname / no NPI list |
| `stealth_dso` | a **URL** (DSO locator lists THIS address / press / da_legal_name), OR `db_artifact` = EIN cluster across ≥3 ZIPs with ≥1 already-corporate member, OR a populated `affiliated_dso`/`parent_company` field that is a real DSO | `brand_hint` ALONE — never sufficient |
| `branded_dso` | populated `affiliated_dso` field, OR a locator/website URL confirming the brand operates THIS address | `brand_hint` substring match alone (e.g. "Heartland Health Outreach" ≠ Heartland Dental) |
| `institutional` | `db_artifact` = institutional name/affiliation match (FQHC/hospital/university/gov), web-confirmable | ambiguous |
| `undetermined` | n/a → `gate_status: undetermined` | the honest default when evidence is absent |

**Key consequence the validation will show:** most `true_independent` rows come back
`candidate`, not `final_ready`, because single-dentist ownership at scale is hard to
web-confirm — and that is CORRECT. The floor of *confirmed* true-independents is earned,
not assumed; the rest stay candidate until a human or a web pass clears them. This is the
mirror image of the corporate floor: both sides are now floors-with-coverage, no anchor.

## Schema (per classification row)

```jsonc
{
  "location_id": "string",
  "assigned_tier": "true_independent|single_loc_group|dentist_multi|stealth_dso|branded_dso|institutional|undetermined",
  "pe_backed": true|false|null,
  "owner_identity": "string|null",          // named dentist or operator
  "network_id": "string|null",              // "ao:LAST_FIRST" for dentist_multi; brand slug for DSO
  "evidence_basis": "locator|web_verified|affiliated_dso_field|parent_company|da_legal_name|ein_cluster|ao_reach|provider_surnames|intel_dossier|institutional_match|structural_only|none",
  "evidence_urls": ["https://..."],          // REQUIRED non-empty for any web-based basis
  "db_artifact": {                            // REQUIRED non-null for any structural final_ready
    "type": "ao_reach|ein_cluster|provider_surnames|affiliated_dso_field|institutional_match",
    "...": "the concrete federal fact: AO name + npis[] + reach + zips[], or ein + members[], etc."
  },
  "web_searched": true|false,
  "gate_status": "final_ready|candidate|undetermined",
  "confidence": "high|medium|low",
  "reasoning": "one sentence citing the deciding signal"
}
```

## Division of labor (per user, 2026-06-21)

- **Opus fleet (this spec):** high-throughput evidence-required classification of the 4,090
  remaining IL GP locations. Emits candidates with the schema above to
  `data/dso_research/census_evidence_candidates_<wave>.json`. **Does NOT write `ownership_tier`.**
- **Codex gate:** validates candidates → promotes only `final_ready` rows to durable
  `ownership_tier`; quarantines the rest as candidate-grade. Owns `consolidate_census.py`,
  `LEDGER.jsonl`, `PROGRESS.json`.

Handshake: fleet writes candidate JSON → Codex's gate consumes it. If the gate wants a
different field set, edit the schema above and I conform the fleet runner (one file:
`scrapers/census_evidence_fleet.js`).
