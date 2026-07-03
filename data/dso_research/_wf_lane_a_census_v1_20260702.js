export const meta = {
  name: 'lane-a-census-wave1',
  description: 'Ownership-census web research on remaining IL GP locations (Lane A, wave 1)',
  phases: [
    { title: 'Research', detail: 'one Sonnet 5 agent per 16-practice unit, web evidence only', model: 'claude-sonnet-5' },
    { title: 'Verify DSO claims', detail: 'Opus 4.8 adversarial check of every stealth/branded DSO claim', model: 'claude-opus-4-8' },
  ],
}

const DIR = '/Users/suleman/dental-pe-tracker/data/dso_research/_lane_a_20260702'
const ARGS = typeof args === 'string' ? JSON.parse(args) : args
const UNITS = ARGS.units
if (!Array.isArray(UNITS) || !UNITS.length) throw new Error('args.units must be a non-empty array of unit file paths')

const RESEARCH_SCHEMA = {
  type: 'object',
  required: ['unit_id', 'n_total', 'n_classified', 'n_undetermined', 'result_file', 'tier_tally', 'dso_claims'],
  properties: {
    unit_id: { type: 'string' },
    n_total: { type: 'integer' },
    n_classified: { type: 'integer' },
    n_undetermined: { type: 'integer' },
    result_file: { type: 'string' },
    tier_tally: { type: 'object' },
    dso_claims: {
      type: 'array',
      items: {
        type: 'object',
        required: ['location_id', 'practice_name', 'zip', 'assigned_tier', 'evidence_urls', 'claim_summary'],
        properties: {
          location_id: { type: 'string' },
          practice_name: { type: 'string' },
          zip: { type: 'string' },
          assigned_tier: { type: 'string' },
          evidence_urls: { type: 'array', items: { type: 'string' } },
          network_id: { type: ['string', 'null'] },
          claim_summary: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['unit_id', 'verdicts'],
  properties: {
    unit_id: { type: 'string' },
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['location_id', 'verdict', 'notes'],
        properties: {
          location_id: { type: 'string' },
          verdict: { type: 'string', enum: ['CONFIRM', 'REFUTE', 'DOWNGRADE_T3', 'INSUFFICIENT'] },
          notes: { type: 'string' },
          urls_checked: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

function researchPrompt(unitPath) {
  return `You are an ownership-census research analyst for Chicagoland (IL) dental practices, working one unit of a hand-verified census. Your ONLY data-gathering tools are Read (for your unit file), WebSearch, and WebFetch (load WebSearch/WebFetch via ToolSearch "select:WebSearch,WebFetch" first if not already available). You must NOT touch any database, must NOT edit any file except your one result file, and must NOT classify anything outside your unit.

INPUT: Read ${unitPath} — it contains ~16 practices, each with location_id, name, dba, address, city, zip, phone, provider_count, and ctx (authorized_official = NPPES AO name, owner_reach_locations = how many IL locations share that AO, ein_reach_locations, brand_hint, institutional_hint, has_intel_dossier). ctx is CONTEXT ONLY — it is never evidence. Evidence comes from the web.

TASK: For EACH practice, run 1-3 targeted web checks (e.g. "<name> <city> IL dentist", the practice's own website, a DSO locator page if a brand is suspected) and assign an ownership tier:
- true_independent (T1): solo dentist owner-operator, one location. Typical evidence: own website naming the owner dentist ("Dr. X has served Naperville since...") with no corporate parent.
- single_loc_group (T2): multi-dentist group at ONE location, dentist-owned.
- dentist_multi (T3): dentist-OWNED practice with 2+ locations (their own site lists multiple offices, owner is a licensed dentist). NEVER a DSO headline tier.
- stealth_dso (T4): multi-location network controlled by a NON-dentist/corporate entity WITHOUT overt national branding (management company in privacy policy/careers page, corporate parent, "partnered with X Dental Partners", non-dentist controller).
- branded_dso (T5): the address belongs to a known branded DSO (Aspen, Heartland, Dental Dreams, Dental 360, All Family/UDP, Smile Brands, Western/Sonrava, Family Dental Care, Destiny/ProSmile, DCA, Great Lakes, Midwest Dental, etc.) — best evidence is the brand's OWN locator/locations page showing this address.
- institutional (T6): FQHC / hospital clinic / university / public-health (HRSA listing, hospital site).
- undetermined: you could not earn any of the above from web evidence.

OUTPUT CONTRACT (fail-closed validator downstream — violations get the whole unit rejected):
1) Write EXACTLY ONE file: ${unitPath.replace('unit_', 'result_unit_')} with JSON {"unit_id": "...", "classifications": [one row PER practice in the unit]}.
2) Each row: {"location_id", "practice_name", "zip", "assigned_tier", "pe_backed" (bool; true ONLY with documented PE sponsor evidence, else false), "evidence_basis" (one of: locator | web_verified | intel_dossier | ein_cluster | ao_cluster | name_chain | structural | none), "evidence_urls" (list of REAL http(s) URLs you actually loaded or that appeared in your search results — never invented, never bare domains, never prose), "evidence_artifacts" (list of short strings for structural notes, may be empty), "confidence" ("high"|"medium"|"low"), "status" ("classified"|"undetermined"), "network_id" ("brand:<slug>" or "ao:<LAST_FIRST>" or null), "reasoning" (2-4 sentences: what you checked, what you found, why the tier follows), "searched" (list of the queries you ran).
3) HARD RULES:
   - status="classified" requires confidence high or medium (never low) AND: basis locator/web_verified/intel_dossier needs >=1 valid URL; basis ein_cluster/ao_cluster/name_chain/structural needs >=1 artifact.
   - stealth_dso/branded_dso ALWAYS need a documentary URL (locator page, corporate site, news). AO/EIN reach alone is NEVER enough for T4/T5 (it can support T3 only when a shared website lists the locations).
   - If a network you find appears to span 10+ locations, do NOT classify — set status="undetermined", note "R4_protected_network:<name>" in reasoning (a one-network-one-decision review handles those).
   - If search suggests the practice is permanently CLOSED, do NOT classify — status="undetermined", note "closure_suspect" in reasoning.
   - NO FABRICATION. If the web gives you nothing usable: status="undetermined", evidence_basis="none", evidence_urls=[], reasoning says what you searched and that it was insufficient. An honest undetermined is worth more than a guessed tier.
   - Distinguish same-name collisions: match on ADDRESS and city, not name alone.
4) Efficiency: budget ~1-3 searches per practice; do not rabbit-hole any single practice.

FINAL: return the structured summary (unit_id, counts, tier_tally, result_file path, and dso_claims = one entry per row you classified stealth_dso or branded_dso, with claim_summary = 1 sentence naming the brand/controller and the key URL).`
}

function verifyPrompt(unitId, claims) {
  return `You are an adversarial ownership verifier. Another agent classified the following Chicagoland dental locations as DSO tiers (stealth_dso/branded_dso). These claims move a PE-consolidation headline metric, so your job is to REFUTE them if possible. Load WebSearch/WebFetch via ToolSearch "select:WebSearch,WebFetch" if needed.

CLAIMS (JSON): ${JSON.stringify(claims)}

For EACH claim: independently check the cited evidence_urls (fetch them) and run at least one independent search of your own. Ask: does the cited page actually place THIS street address under the claimed brand/controller? Is the "DSO" actually a dentist-owned group (that would be DOWNGRADE_T3)? Is this a name collision with a different practice? Is the URL dead or irrelevant?

Verdicts: CONFIRM (evidence genuinely supports the DSO tier), REFUTE (evidence contradicts or does not support it), DOWNGRADE_T3 (real multi-location network but demonstrably dentist-owned), INSUFFICIENT (cited evidence too weak to confirm; default here if uncertain).
Return the structured verdicts with 1-2 sentence notes and the URLs you checked. Do not write any files.`
}

phase('Research')
const results = await pipeline(
  UNITS,
  (u) => agent(researchPrompt(u), {
    label: `research:${u.split('/').pop()}`,
    phase: 'Research',
    schema: RESEARCH_SCHEMA,
    model: 'claude-sonnet-5',
    agentType: 'general-purpose',
  }),
  (res, u) => {
    if (!res) return null
    const claims = (res.dso_claims || [])
    if (!claims.length) return { ...res, verdicts: [] }
    return agent(verifyPrompt(res.unit_id, claims), {
      label: `verify:${res.unit_id}`,
      phase: 'Verify DSO claims',
      schema: VERDICT_SCHEMA,
      model: 'claude-opus-4-8',
      agentType: 'general-purpose',
    }).then((v) => ({ ...res, verdicts: v ? v.verdicts : [{ location_id: 'ALL', verdict: 'INSUFFICIENT', notes: 'verifier agent failed; treat unit DSO claims as unverified' }] }))
  }
)

const done = results.filter(Boolean)
const totals = { units_ok: done.length, units_failed: results.length - done.length, classified: 0, undetermined: 0, dso_claims: 0, confirmed: 0, refuted_or_downgraded: 0 }
const tierTotals = {}
for (const r of done) {
  totals.classified += r.n_classified
  totals.undetermined += r.n_undetermined
  totals.dso_claims += (r.dso_claims || []).length
  for (const [t, n] of Object.entries(r.tier_tally || {})) tierTotals[t] = (tierTotals[t] || 0) + n
  for (const v of r.verdicts || []) {
    if (v.verdict === 'CONFIRM') totals.confirmed += 1
    else if (v.verdict === 'REFUTE' || v.verdict === 'DOWNGRADE_T3') totals.refuted_or_downgraded += 1
  }
}
log(`Wave 1 complete: ${totals.classified} classified / ${totals.undetermined} undetermined across ${totals.units_ok} units`)
return { totals, tierTotals, perUnit: done.map(r => ({ unit: r.unit_id, file: r.result_file, classified: r.n_classified, undetermined: r.n_undetermined, verdicts: (r.verdicts || []).map(v => ({ lid: v.location_id, verdict: v.verdict, notes: v.notes })) })) }