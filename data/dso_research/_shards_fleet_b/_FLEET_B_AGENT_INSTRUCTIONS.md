# EVIDENCE FLEET B — shared agent instructions (read fully before classifying)

You are one worker in **Evidence Fleet B**, a non-colliding evidence-gathering fleet for the
Chicagoland dental ownership census. You produce **candidate evidence rows only** — never final
truth. A separate QA/validation session decides what gets written to the DB. **You make ZERO DB
writes and ZERO writes to LEDGER.jsonl / PROGRESS.json.** You write exactly ONE shard JSON file
(path given in your task) and nothing else.

DB (read-only): `/Users/suleman/dental-pe-tracker/data/dental_pe_tracker.db` (table `practice_intel`
keyed by `npi`; table `practice_locations` keyed by `location_id`). IL / Chicagoland ONLY.

Your output must pass `scrapers/consolidate_census.py --validate-only`. Emit the **validator-native
field names below verbatim** — earlier fleets failed because they used `gate_status`,
`structural_only`, `ao_reach` etc., which the validator rejects.

## The ownership tiers (assign the FIRST that documentary evidence supports)
- `true_independent` — ONE dentist owns ONE location; no brand, no EIN chain, no PE tie. **EARNED, never defaulted.** Needs a positive web URL of one named owner-dentist at this address with no DSO/MSO language. A bare structural fact (provider surnames, one location) does NOT earn `classified` true_independent → it is `needs_verification`. Most true_independent rows come back `needs_verification` — that is CORRECT.
- `single_loc_group` — 2+ unrelated dentists, ONE location, dentist-owned, no chain. Needs a partnership web page (URL) OR ≥2 distinct provider surnames at one address as a `structural` artifact (the latter is candidate-grade → usually `needs_verification`).
- `dentist_multi` — a **dentist-owned** multi-location practice/group operating 2+ locations across ZIPs with **NO separate DSO/MSO/management-company/platform structure**. Artifact: same authorized official (AO) at ≥2 distinct watched-IL locations → `evidence_basis:"ao_cluster"` with the AO+NPIs+ZIPs artifact. AO alone with a generic surname / no NPI list = candidate → `needs_verification`. `pe_backed=false` by default.
- `stealth_dso` — a LOCAL / friendly-PC brand **backed or managed by a DSO/MSO/PE platform**. `classified` needs ONE durable item: a DSO official locator/source URL listing THIS exact street+ZIP (`locator`); the NPI's own legal/parent name = a DSO/MSO confirmed on the web (`web_verified`); an EIN across ≥3 ZIPs with ≥1 already-corporate member (`ein_cluster` artifact); or an intel dossier naming a PE sponsor/DSO/MSO with a citation URL (`intel_dossier`). Usually `pe_backed=true`, but a non-PE MSO/management platform still qualifies.
- `branded_dso` — a **DSO / platform / management-company structure OR an established DSO brand**, confirmed against the brand's OWN locator/official source at exact street+ZIP (`locator` + URL) or other documentary platform evidence. **This tier holds EVEN IF family-owned or non-PE** (`pe_backed` is a SEPARATE flag — see taxonomy rule below). Brand substring alone is never enough.

> **⚠️ TAXONOMY RULE (2026-06-21 correction — do NOT regress):** `pe_backed=false` is **NOT** a reason to downgrade `branded_dso`/`stealth_dso` to `dentist_multi`. The tier is decided by **DSO/platform/MSO STRUCTURE**, not by PE backing. `pe_backed` is an orthogonal boolean.
> - If evidence shows a real **MSO / management-services entity / centralized management company / DSO platform / multi-location support org / official chain locator / explicit DSO or corporate-platform language**, keep the DSO tier (`branded_dso` or `stealth_dso`) even when `pe_backed=false`.
> - If it is simply a **dentist-owned multi-location brand with NO MSO/platform evidence**, use `dentist_multi`.
> - This matters for **Dental Dreams / KOS Services**, and possibly **Webster, 1st Family, Family Dental Care, Brite**, etc. — do NOT collapse all non-PE brands into `dentist_multi` without checking for DSO/platform structure. When the structure is unclear → `assigned_tier:"undetermined"`, `proposed_tier:"<best guess>"`, `status:"needs_verification"`.
- `institutional` — FQHC, community health center, hospital, university clinic, county/state/VA, Medicaid safety-net org. `classified` needs an official FQHC/nonprofit/hospital/gov source URL (`web_verified`). Own bucket; not consolidated, not DSO.
- `undetermined` — evidence absent or conflicting. The honest default; pair with `status:"needs_verification"`.

## HARD quality rules (the census exists because these were violated before)
- **AO reach alone ≠ ownership proof.** Shared AO = a *candidate* for `dentist_multi`; generic surname / no NPI list → `needs_verification`.
- **stealth_dso / branded_dso REQUIRE exact documentary evidence** (a real URL or a durable artifact). A brand SUBSTRING alone ("Heartland Health Outreach" ≠ Heartland Dental) is NEVER sufficient → `needs_verification`.
- **`affiliated_dso` field is NOT final by itself.** Use `evidence_basis:"locator"` ONLY if an exact official locator/source URL matches exact address+ZIP. Otherwise `evidence_basis:"structural"` + `status:"needs_verification"`.
- **pe_backed=true requires real PE-sponsor evidence** (named PE firm / platform-company filing), never size or provider count. A non-PE DSO/MSO keeps its DSO tier with `pe_backed=false`.
- **DSO/platform tier ≠ pe_backed.** DSO/platform evidence includes: an MSO / management-services entity, a centralized management company, explicit DSO language, a multi-location support org, an official chain locator, or corporate-platform language. Any ONE keeps `branded_dso`/`stealth_dso` regardless of PE status. Absent that → `dentist_multi` (if dentist-owned multi-loc) or `needs_verification`.
- **true_independent must be POSITIVELY earned.** "No DSO language" alone is NOT enough → `needs_verification`.
- **Data-Axle synthetic rows** (primary_npi/org_npi starting `DA_`, or entity_classification `da_unverified`) can NEVER be classified → `status:"undetermined"`, `disposition:"reject"`.
- **Insurance/discount-plan names are NOT ownership.** "Careington", "accepts X PPO", a brand named as *insurance accepted* or a *nearby competitor* is NOT ownership evidence. Read the sentence.
- When uncertain → `needs_verification` (tier `undetermined`) or reject. Never guess.

## evidence_basis mapping (USE ONLY the validator vocabulary on the LEFT)
`locator` ← DSO official locator/source page matching exact address+ZIP (needs evidence_urls) ·
`web_verified` ← web search/press/official site/FQHC-nonprofit-hospital-gov source (needs evidence_urls) ·
`intel_dossier` ← a `practice_intel` dossier naming the owner/DSO (needs that dossier's verification URL) ·
`ein_cluster` ← shared EIN across ≥3 ZIPs (needs evidence_artifacts) ·
`ao_cluster` ← shared authorized-official reach, formerly "ao_reach" (needs evidence_artifacts; AO alone = candidate only) ·
`name_chain` ← same brand across 3+ ZIPs (needs evidence_artifacts) ·
`structural` ← any NPPES/provider/surname fact, formerly "structural_only"/"provider_surnames" (needs evidence_artifacts; NOT final true_independent on its own) ·
`none` ← for needs_verification / reject rows with no durable artifact.

- URL bases (`locator`, `web_verified`, `intel_dossier`) → `evidence_urls` MUST be non-empty for `status:"classified"`.
- Artifact bases (`ein_cluster`, `ao_cluster`, `name_chain`, `structural`) → `evidence_artifacts` MUST be non-empty (concrete federal fact strings, e.g. `"NPPES AO=JOHN SMITH npis=[1234567890,1987654321] reach=2 zips=[60148,60101]"`).

## Output row schema — emit EXACTLY these field names (validator-native + extended)
```json
{
  "location_id": "...",
  "assigned_tier": "true_independent|single_loc_group|dentist_multi|stealth_dso|branded_dso|institutional|undetermined",
  "status": "classified|needs_verification|undetermined",
  "evidence_basis": "locator|web_verified|intel_dossier|ein_cluster|ao_cluster|name_chain|structural|none",
  "evidence_urls": ["https://..."],
  "evidence_artifacts": ["concrete federal fact string or query ref"],
  "confidence": "high|medium|low",
  "reasoning": "one evidence-based sentence citing the deciding signal",

  "proposed_tier": "same as assigned_tier, or the tier you suspect when status!=classified",
  "disposition": "ready|needs_verification|reject",
  "pe_backed": true,
  "owner_identity": "named dentist/operator or null",
  "network_id": "ao:LAST_FIRST or brand slug or null",
  "signal": {"type": "affiliated_dso|practice_intel|locator|ao_cluster|name_chain|website|other", "details": "what made this a target"},
  "exact_address_match": true,
  "practice_name": "...", "address": "...", "city": "...", "zip": "...",
  "agent": "fleet_b", "reviewed_at": "2026-06-21"
}
```

### status ↔ tier ↔ disposition consistency (the validator enforces the first three)
- **classified** (`disposition:"ready"`) → a REAL `assigned_tier` + sufficient evidence (URL for URL-bases, artifact for artifact-bases; DSO/stealth tiers need a URL or artifact). `confidence` MUST be `high` or `medium`, NEVER `low`.
- **needs_verification** (`disposition:"needs_verification"`) → `assigned_tier` MUST be `"undetermined"`; put your hunch in `proposed_tier`; `evidence_basis` usually `"none"` (or `structural` with the partial artifact). Use whenever there's a lead but no durable artifact yet.
- **reject** → `status:"undetermined"`, `assigned_tier:"undetermined"`, `disposition:"reject"`. For DA_ synthetics, non-IL, excluded GP class, or unclassifiable noise.

Write your shard as a JSON array of these rows. Then return a 3-4 sentence summary: counts by
disposition (ready / needs_verification / reject), by assigned_tier, notable exact-address DSO
locator matches (brand + address), and any conflicts you noticed.
