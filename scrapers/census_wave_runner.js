export const meta = {
  name: 'ownership-census-wave',
  description: 'Classify a wave of Chicagoland GP practices into the 6-tier OWNERSHIP model with documentary evidence',
  phases: [{ title: 'Census', detail: 'one agent per ~18-practice batch, classify ownership' }],
}

// ── wave control: bump WAVE between launches; WAVE_SIZE batches per wave ──
const WAVE = 0
const WAVE_SIZE = 40
const FILE = '/Users/suleman/dental-pe-tracker/data/dso_research/census_batches_remaining_20260621.json'
const ALL_IDS = ["60491-1","60439-1","60439-2","60441-1","60540-1","60564-1","60564-2","60564-3","60563-1","60563-2","60563-3","60527-1","60527-2","60515-1","60515-2","60516-1","60532-1","60532-2","60559-1","60559-2","60514-1","60521-1","60521-2","60523-1","60148-1","60148-2","60148-3","60440-1","60440-2","60490-1","60504-1","60504-2","60502-1","60431-1","60435-1","60435-2","60435-3","60586-1","60585-1","60503-1","60554-1","60543-1","60543-2","60560-1","60517-1","60517-2","60465-1","60448-1","60526-1","60451-1","60451-2","60446-1","60464-1","60403-1","60404-1","60410-1","60436-1","60447-1","60450-1","60004-1","60004-2","60004-3","60007-1","60007-2","60008-1","60010-1","60010-2","60010-3","60015-1","60016-1","60016-2","60016-3","60018-1","60022-1","60025-1","60025-2","60025-3","60026-1","60035-1","60035-2","60040-1","60045-1","60053-1","60053-2","60056-1","60056-2","60056-3","60061-1","60061-2","60067-1","60067-2","60069-1","60070-1","60074-1","60074-2","60076-1","60076-2","60077-1","60077-2","60077-3","60089-1","60089-2","60089-3","60090-1","60090-2","60091-1","60091-2","60093-1","60093-2","60201-1","60201-2","60202-1","60712-1","60714-1","60714-2","60601-1","60601-2","60602-1","60603-1","60604-1","60605-1","60605-2","60606-1","60607-1","60607-2","60607-3","60608-1","60608-2","60609-1","60610-1","60610-2","60611-1","60611-2","60611-3","60612-1","60612-2","60613-1","60613-2","60615-1","60616-1","60616-2","60617-1","60617-2","60618-1","60618-2","60618-3","60619-1","60620-1","60621-1","60623-1","60623-2","60624-1","60625-1","60625-2","60625-3","60626-1","60628-1","60629-1","60629-2","60630-1","60630-2","60630-3","60631-1","60631-2","60632-1","60632-2","60632-3","60633-1","60634-1","60636-1","60637-1","60638-1","60638-2","60639-1","60639-2","60640-1","60640-2","60640-3","60641-1","60641-2","60642-1","60643-1","60643-2","60644-1","60645-1","60646-1","60646-2","60646-3","60647-1","60647-2","60647-3","60647-4","60649-1","60651-1","60652-1","60653-1","60654-1","60654-2","60655-1","60656-1","60657-1","60657-2","60657-3","60657-4","60659-1","60659-2","60659-3","60660-1","60660-2","60661-1","60406-1","60409-1","60411-1","60411-2","60415-1","60418-1","60419-1","60422-1","60423-1","60423-2","60426-1","60428-1","60429-1","60430-1","60438-1","60442-1","60443-1","60445-1","60449-1","60452-1","60453-1","60453-2","60453-3","60455-1","60456-1","60457-1","60458-1","60459-1","60461-1","60462-1","60462-2","60462-3","60463-1","60463-2","60466-1","60467-1","60467-2","60468-1","60471-1","60473-1","60475-1","60477-1","60477-2","60478-1","60480-1","60481-1","60482-1","60484-1","60487-1","60501-1","60803-1","60804-1","60804-2","60805-1","60827-1","60101-1","60101-2","60103-1","60103-2","60104-1","60106-1","60107-1","60107-2","60108-1","60108-2","60126-1","60126-2","60126-3","60130-1","60131-1","60133-1","60137-1","60137-2","60139-1","60143-1","60153-1","60154-1","60154-2","60155-1","60160-1","60160-2","60162-1","60163-1","60164-1","60165-1","60171-1","60176-1","60181-1","60181-2","60188-1","60189-1","60190-1","60191-1","60193-1","60194-1","60194-2","60195-1","60301-1","60304-1","60305-1","60402-1","60402-2","60402-3","60513-1","60525-1","60525-2","60534-1","60546-1","60546-2","60555-1","60558-1","60706-1","60706-2","60707-1","60707-2","60110-1","60118-1","60119-1","60120-1","60120-2","60123-1","60123-2","60124-1","60134-1","60134-2","60151-1","60172-1","60172-2","60173-1","60173-2","60174-1","60174-2","60175-1","60185-1","60505-1","60506-1","60506-2","60510-1","60511-1","60538-1","60542-1","60544-1","60544-2","60545-1","60548-1","60416-1","60432-1","60433-1"]

const IDS = ALL_IDS.slice(WAVE * WAVE_SIZE, (WAVE + 1) * WAVE_SIZE)

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
          evidence_basis: { enum: ['locator','web_verified','ein_cluster','ao_cluster','name_chain','intel_dossier','structural','none'] },
          evidence_urls: { type: 'array', items: { type: 'string' } },
          confidence: { enum: ['high','medium','low'] },
          status: { enum: ['classified','undetermined','needs_verification'] },
          reasoning: { type: 'string' },
        },
        required: ['location_id','assigned_tier','pe_backed','owner_identity','network_id','evidence_basis','evidence_urls','confidence','status','reasoning'],
      },
    },
  },
  required: ['batch_id','classifications'],
}

const MODEL = `You are a dental-practice OWNERSHIP analyst building a hand-verified census of Chicagoland general dental practices. Classify each practice by WHO OWNS IT (ownership structure), NOT by its size. Every practice gets exactly ONE tier.

THE 6 TIERS (+ undetermined):
- true_independent  : ONE dentist owns ONE location. Solo or single-family. EARNED, never a default.
- single_loc_group  : 2+ unrelated dentists, ONE location, dentist-owned (a partnership/group at a single office). NOT a chain.
- dentist_multi     : ONE owner-dentist runs 2+ locations, NO private-equity/MSO backing (a "mini-DSO" / stealth owner).
- stealth_dso       : PE/MSO-backed practice operating under a LOCAL name (friendly-PC). The hard, high-value class.
- branded_dso       : the office's public name IS a known DSO brand (Aspen, Dental Dreams, Western Dental, Great Lakes Dental Partners, etc.).
- institutional     : FQHC, community health center, hospital/health-system, university, government/VA, safety-net.
- undetermined      : genuinely ambiguous OR not resolvable with evidence. NEVER guess; NEVER silent-default to true_independent.

pe_backed (boolean): true for stealth_dso always; for branded_dso true only if the brand has a known PE sponsor (provided as ctx.brand_hint.pe_sponsor); false for true_independent/single_loc_group/dentist_multi/institutional; null when unknown/undetermined.

HOW TO READ THE PRE-COMPUTED CONTEXT (ctx) — it is from the FEDERAL NPPES data, already true:
- ctx.authorized_official: the registered owner/official of the practice's NPI.
- ctx.owner_reach_locations / owner_reach_zips: how many DISTINCT watched-IL GP locations share this same authorized official, and which ZIPs. reach==1 -> single-location owner (supports true_independent / single_loc_group). reach>=2 across multiple ZIPs -> the SAME person owns multiple offices = dentist_multi (unless PE-backed -> stealth_dso).
- ctx.ein_reach_locations / ein_reach_zips: locations sharing the same EIN across ZIPs -> corporate/chain structure.
- ctx.brand_hint: a possible DSO/PE brand matched by substring. THIS IS A HINT, NOT PROOF. e.g. "Heartland Health Outreach" matches "Heartland" but is a community-health org, NOT Heartland Dental — you MUST reject false matches. Confirm via web before assigning branded_dso/stealth_dso on a brand_hint.
- ctx.institutional_hint: name suggests FQHC/hospital/university/government.
- provider_count: # providers at the address (1 -> solo-ish; many -> group or DSO).

DECISION LADDER (stop at first tier the evidence supports):
A. Institutional name/affiliation confirmed -> institutional.
B. Name IS a known DSO brand (confirmed, not a false hint) -> branded_dso.
C. PE/MSO-backed friendly-PC (DSO locator lists this exact address under a local name; or da_legal_name/parent_company is a DSO; or EIN shared across 3+ ZIPs with a corporate member; or an AI dossier names a PE sponsor) -> stealth_dso.
D. Same owner-dentist runs 2+ locations (owner_reach>=2 across ZIPs), no PE tie -> dentist_multi. network_id="ao:LAST_FIRST".
E. 2+ unrelated dentists at ONE location, dentist-owned, single-location -> single_loc_group.
F. ONE dentist, ONE location (owner_reach==1, no brand, no EIN chain, no PE tie), confirmed -> true_independent (EARNED).
G. Cannot settle with evidence -> undetermined (status=needs_verification, say why).

EVIDENCE RULES (zero fabrication):
- structural basis (owner_reach / ein_reach / clearly-institutional or clearly-branded NPPES name) needs NO url — set evidence_basis accordingly and confidence by strength.
- Any web/locator/dossier claim MUST include the source URL(s) in evidence_urls.
- brand_hint alone is NOT sufficient for branded_dso/stealth_dso — confirm.
- Prefer classifying from ctx (most resolve structurally). Use web search ONLY when ctx is ambiguous AND the answer would change the tier (e.g. confirm a brand office, confirm whether a multi-loc owner is PE-backed, confirm institutional). Cap ~2 web searches per practice. If web tools are unavailable, classify from ctx and set status=needs_verification where web was truly required.
- Never demote a clearly-branded DSO to independent just because reach data is sparse.

OUTPUT: call StructuredOutput once with batch_id and one classification object per practice in your batch. reasoning = one tight sentence citing the deciding signal.`

phase('Census')
log(`Wave ${WAVE}: batches ${WAVE * WAVE_SIZE}..${WAVE * WAVE_SIZE + IDS.length - 1} of ${ALL_IDS.length} (${IDS.length} this wave)`)
const results = await parallel(IDS.map((bid) => () =>
  agent(
    `${MODEL}

YOUR TASK: Read the JSON file at ${FILE}. Find the batch object whose "batch_id" == "${bid}" (in the top-level "batches" array). Classify EVERY practice in that batch's "practices" list. Return one classification per practice, keyed by its location_id. Do not skip any. batch_id in your output = "${bid}".`,
    { label: `census:${bid}`, phase: 'Census', model: 'sonnet', schema: SCHEMA }
  )
))

const ok = results.filter(Boolean)
const allClass = ok.flatMap((r) => r.classifications || [])
const tally = {}
for (const c of allClass) tally[c.assigned_tier] = (tally[c.assigned_tier] || 0) + 1
log(`Wave ${WAVE} done: ${ok.length}/${IDS.length} batches, ${allClass.length} practices. Tiers: ${JSON.stringify(tally)}`)
return { wave: WAVE, batches_ok: ok.length, batches_total: IDS.length, n_classified: allClass.length, tier_tally: tally, classifications: allClass }
