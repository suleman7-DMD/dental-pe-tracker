export const meta = {
  name: 'ownership-census-evidence-fleet',
  description: 'Evidence-REQUIRED ownership classification: every final_ready row must carry a durable artifact (URL or federal DB-fact). Writes CANDIDATES only — never ownership_tier.',
  phases: [{ title: 'Census', detail: 'one Sonnet agent per batch, evidence-required, gate_status self-labeled' }],
}

// ── wave control. Validation wave = the 4 evidence-densest remaining batches. ──
// Bump WAVE_IDS for subsequent waves once Codex's gate confirms the schema.
const FILE = '/Users/suleman/dental-pe-tracker/data/dso_research/census_batches_remaining_20260621.json'
const WAVE_LABEL = 'validation'
const WAVE_IDS = ['60647-2', '60804-1', '60640-2', '60629-1']

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    batch_id: { type: 'string' },
    classifications: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          location_id: { type: 'string' },
          assigned_tier: { enum: ['true_independent','single_loc_group','dentist_multi','stealth_dso','branded_dso','institutional','undetermined'] },
          pe_backed: { type: ['boolean','null'] },
          owner_identity: { type: ['string','null'] },
          network_id: { type: ['string','null'] },
          evidence_basis: { enum: ['locator','web_verified','affiliated_dso_field','parent_company','da_legal_name','ein_cluster','ao_reach','provider_surnames','intel_dossier','institutional_match','structural_only','none'] },
          evidence_urls: { type: 'array', items: { type: 'string' } },
          db_artifact: { type: ['object','null'], additionalProperties: true },
          web_searched: { type: 'boolean' },
          gate_status: { enum: ['final_ready','candidate','undetermined'] },
          confidence: { enum: ['high','medium','low'] },
          reasoning: { type: 'string' },
        },
        required: ['location_id','assigned_tier','pe_backed','owner_identity','network_id','evidence_basis','evidence_urls','db_artifact','web_searched','gate_status','confidence','reasoning'],
      },
    },
  },
  required: ['batch_id','classifications'],
}

const MODEL = `You are a dental-practice OWNERSHIP analyst building a hand-verified census of Chicagoland general dental practices. Classify each practice by WHO OWNS IT, NOT by size. Exactly ONE tier per practice. Your output is CANDIDATE data feeding an evidence gate — be honest about what you could and could not prove.

THE 6 TIERS (+ undetermined):
- true_independent  : ONE dentist owns ONE location. EARNED with evidence, NEVER a default.
- single_loc_group  : 2+ unrelated dentists, ONE dentist-owned location (partnership/group, not a chain).
- dentist_multi     : ONE owner-dentist runs 2+ locations, NO PE/MSO backing (mini-DSO / stealth owner).
- stealth_dso       : PE/MSO-backed practice under a LOCAL name (friendly-PC). The hard, high-value class.
- branded_dso       : the office's public name IS a known DSO brand (Aspen, Dental Dreams, Western Dental, etc.).
- institutional     : FQHC, community health center, hospital/health-system, university, government/VA, safety-net.
- undetermined      : genuinely unresolvable with evidence. NEVER guess; NEVER silent-default to true_independent.

THE DURABLE-ARTIFACT RULE (this is the whole point):
A row may be gate_status="final_ready" ONLY if it carries a durable artifact a third party can re-verify:
  - a real URL in evidence_urls (web/locator/dossier basis), OR
  - a db_artifact object capturing the concrete FEDERAL fact (structural basis).
Anything weaker is gate_status="candidate". undetermined rows are gate_status="undetermined".

PER-TIER EVIDENCE BAR:
- true_independent  -> final_ready needs a WEB URL showing one named owner-dentist at this address with NO DSO/MSO/parent language. owner_reach==1 + solo + no brand is STRUCTURAL ONLY: it does NOT rule out a stealth friendly-PC, so without that URL you MUST set gate_status="candidate" (tier can stay true_independent, basis="structural_only"). Do NOT mark structural true_independent final_ready.
- single_loc_group  -> final_ready needs db_artifact {type:"provider_surnames", surnames:[...], address} (2+ distinct surnames, one address) OR a partnership URL.
- dentist_multi     -> final_ready allowed on db_artifact {type:"ao_reach", authorized_official, npis:[...], reach:N, zips:[...]} when ctx.owner_reach_locations>=2 and the AO is a specific person (not a generic surname). network_id="ao:LAST_FIRST". No URL required — the federal AO link IS the artifact. pe_backed=false unless a PE tie is web-confirmed (then it's stealth_dso).
- stealth_dso       -> final_ready needs a URL (DSO locator lists THIS address / press / da_legal_name web-confirmed) OR db_artifact {type:"ein_cluster", ein, members:[...], zips:[...]} spanning >=3 ZIPs with an already-corporate member, OR a populated affiliated_dso/parent_company that is a real DSO (basis="affiliated_dso_field"/"parent_company", cite the field value in db_artifact). brand_hint ALONE is never enough. pe_backed=true.
- branded_dso       -> final_ready needs a populated affiliated_dso field (db_artifact {type:"affiliated_dso_field", value:...}) OR a locator/website URL confirming the brand at THIS address. brand_hint substring alone = candidate. pe_backed = true only if the brand has a known PE sponsor (ctx.brand_hint.pe_sponsor), else false.
- institutional     -> final_ready needs db_artifact {type:"institutional_match", signal:...} from the name/affiliation, web-confirm if ambiguous. pe_backed=false.

READING ctx (pre-computed from FEDERAL NPPES — already true, safe to cite as db_artifact):
- ctx.authorized_official: registered owner/official of the NPI.
- ctx.owner_reach_locations / owner_reach_zips: # distinct watched-IL GP locations sharing this AO. reach==1 -> single-location. reach>=2 across ZIPs -> SAME person owns multiple offices = dentist_multi (durable artifact).
- ctx.ein_reach_locations / ein_reach_zips: locations sharing this EIN across ZIPs -> chain/corporate structure.
- ctx.brand_hint: a possible DSO/PE brand by substring. A HINT, NOT PROOF. e.g. "Heartland Health Outreach" matches "Heartland" but is community-health, NOT Heartland Dental. You MUST reject false matches and confirm before branded_dso/stealth_dso.
- ctx.institutional_hint, ctx.has_intel_dossier, provider_count, affiliated_dso, parent_company.

DECISION LADDER (stop at first tier the evidence supports), then set gate_status by the bar above:
A. Institutional confirmed -> institutional.
B. Name IS a confirmed DSO brand -> branded_dso.
C. PE/MSO friendly-PC (locator/da_legal_name/parent_company/EIN-cluster/dossier names a sponsor) -> stealth_dso.
D. Same owner-dentist 2+ locations (owner_reach>=2), no PE tie -> dentist_multi.
E. 2+ unrelated dentists, one dentist-owned location -> single_loc_group.
F. One dentist, one location, no brand/EIN/PE -> true_independent (candidate unless web-confirmed).
G. Cannot settle -> undetermined.

WEB SEARCH: use it (set web_searched=true) when it would CHANGE the tier or move a row from candidate to final_ready — confirm a brand office, confirm a multi-loc owner is PE-backed, web-confirm a true_independent owner, confirm institutional. Cap ~2 searches/practice. Every web claim REQUIRES the source URL in evidence_urls. If web tools are unavailable, classify from ctx, set web_searched=false, and use gate_status="candidate" wherever the bar required web. NEVER fabricate a URL — if a search returns nothing, do not invent one.

OUTPUT: call StructuredOutput once with batch_id and one classification per practice. reasoning = one tight sentence citing the deciding signal and why the gate_status.`

phase('Census')
log(`Evidence fleet [${WAVE_LABEL}]: ${WAVE_IDS.length} batches -> ${WAVE_IDS.join(', ')}`)
const results = await parallel(WAVE_IDS.map((bid) => () =>
  agent(
    `${MODEL}

YOUR TASK: Read the JSON file at ${FILE}. Find the batch object whose "batch_id" == "${bid}" (in the top-level "batches" array). Classify EVERY practice in that batch's "practices" list. Return one classification per practice keyed by its location_id. Do not skip any. batch_id in your output = "${bid}".`,
    { label: `evid:${bid}`, phase: 'Census', model: 'sonnet', schema: SCHEMA }
  )
))

const ok = results.filter(Boolean)
const allClass = ok.flatMap((r) => r.classifications || [])
const tier = {}, gate = {}, basis = {}
for (const c of allClass) {
  tier[c.assigned_tier] = (tier[c.assigned_tier] || 0) + 1
  gate[c.gate_status] = (gate[c.gate_status] || 0) + 1
  basis[c.evidence_basis] = (basis[c.evidence_basis] || 0) + 1
}
const finalReady = allClass.filter((c) => c.gate_status === 'final_ready')
const withUrl = allClass.filter((c) => (c.evidence_urls || []).length > 0)
const withArtifact = allClass.filter((c) => c.db_artifact && Object.keys(c.db_artifact).length > 0)
log(`Done: ${ok.length}/${WAVE_IDS.length} batches, ${allClass.length} practices. tiers=${JSON.stringify(tier)} gate=${JSON.stringify(gate)}`)
log(`Evidence: final_ready=${finalReady.length} with_url=${withUrl.length} with_db_artifact=${withArtifact.length}`)
return {
  wave_label: WAVE_LABEL,
  batches_ok: ok.length,
  batches_total: WAVE_IDS.length,
  n_classified: allClass.length,
  tier_tally: tier,
  gate_tally: gate,
  basis_tally: basis,
  n_final_ready: finalReady.length,
  n_with_url: withUrl.length,
  n_with_db_artifact: withArtifact.length,
  classifications: allClass,
}
