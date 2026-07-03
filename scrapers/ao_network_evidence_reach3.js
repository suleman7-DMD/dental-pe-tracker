export const meta = {
  name: 'ao-network-evidence-reach3',
  description: 'AO Wave 3 — Hidden Local Consolidator Discovery on RANKED reach=3 + strong-signal reach=2 networks. Evidence-only; investigates each AO network as a multi-location ownership CANDIDATE, separates signal (AO reach) from documentary evidence. Emits ready_for_validation rows only — never final, never DB/ownership_tier.',
  phases: [{ title: 'Networks', detail: 'one agent per ranked AO network, corroborate owner type with documentary evidence' }],
}

const TARGETS = '/Users/suleman/dental-pe-tracker/data/dso_research/ownership_evidence_targets_20260621.json'
// Source-of-truth ranking artifact (built by the ranked-target-list step; embedded as the RANKED literal
// below because workflow scripts have NO filesystem access — only the agents can read files).
const RANKED_FILE = '/Users/suleman/dental-pe-tracker/data/dso_research/ao_network_evidence_reach3_ranked_targets_20260621.json'
const RAW_DIR = '/Users/suleman/dental-pe-tracker/data/dso_research/_reach3_raw_20260621'
// ╔══════════════════════════════════════════════════════════════════════════════════════════╗
// ║ ✅ AO WAVE 3 — RANKED reach=3 + strong-signal reach=2. Per user (Autonomous Work Mode,        ║
// ║ 2026-06-21): "Do NOT run a blind full reach 2-3 long tail. Build a ranked target list first,   ║
// ║ then launch agents on the highest-value clusters." This is RANKED (not blind): 36 reach=3 +    ║
// ║ 15 strong-signal reach=2 from ao_network_evidence_reach3_ranked_targets_20260621.json.         ║
// ║ EVIDENCE-ONLY: NO DB writes, NO consolidation, NO ownership_tier/LEDGER/PROGRESS mutation.     ║
// ║ Gate ceiling = ready_for_validation, NEVER final. AO reach = candidate signal, not proof.      ║
// ║ Excludes: top-8/reach>=5/reach=4/backfill-71 (already done), name-variant dups, specialist-     ║
// ║ only, Evenly-placeholder landmines, MA/Boston.                                                 ║
// ╚══════════════════════════════════════════════════════════════════════════════════════════╝
// The network list is loaded from the RANKED target file at run time (parameterized, not hardcoded),
// so the ranking artifact is the single source of truth for what this wave covers.

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    network: { type: 'string' },
    network_id: { type: 'string' },
    // What KIND of network the evidence supports — or that it could not be resolved.
    owner_type_verdict: { enum: ['dentist_owned_multi', 'pe_mso_backed', 'dso_brand', 'institutional', 'unresolved'] },
    network_summary: { type: 'string' },
    // ── Network intelligence to PRESERVE (user spec 2026-06-21). Future app uses these even when not final. ──
    owner_operator_identity: { type: ['string', 'null'] },          // owner/family/operator person(s) where documented
    brand_trade_names: { type: 'array', items: { type: 'string' } }, // consumer-facing brand/DBA names across the network
    legal_entities: { type: 'array', items: { type: 'string' } },   // PCs/LLCs/LTDs/management cos tied to the network
    durable_artifacts: { type: 'array', items: { type: 'string' } },// EIN / shared-address / name-chain / parent-org artifacts (NPPES-durable)
    mso_platform_pe_evidence: { type: ['string', 'null'] },         // any MSO/management-co/platform/PE corroborator found (null if none)
    stale_closed_false_positive_notes: { type: ['string', 'null'] },// vacated shells, relocations, AO-cluster false positives
    evidence_chain: { type: 'string' },                             // AO signal -> documentary corroboration narrative
    future_app_notes: { type: 'string' },                           // what the app should remember about this network
    classifications: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          location_id: { type: 'string' },
          // Candidate tier the evidence POINTS toward (not a final assignment).
          candidate_tier: { enum: ['dentist_multi', 'stealth_dso', 'branded_dso', 'institutional', 'undetermined'] },
          pe_backed: { type: ['boolean', 'null'] },
          owner_identity: { type: ['string', 'null'] },
          network_id: { type: ['string', 'null'] },
          // Codex correction #7: separate the candidate SIGNAL from documentary EVIDENCE.
          signal_vs_evidence: {
            type: 'object',
            additionalProperties: false,
            properties: {
              // structural candidate signals only (NPPES-derived): ao_reach, shared_mailing, ein_cluster, name_chain
              signal: { type: 'array', items: { type: 'string' } },
              // re-verifiable documentary corroborators: official group website, locator page, owner/doctor bio,
              // shared legal-entity filing, press, NPI artifact. Empty = signal-only (NOT ready_for_validation).
              evidence: { type: 'array', items: { type: 'string' } },
            },
            required: ['signal', 'evidence'],
          },
          evidence_urls: { type: 'array', items: { type: 'string' } },
          db_artifact: { type: ['object', 'null'], additionalProperties: true },
          web_searched: { type: 'boolean' },
          // Codex correction #4: highest status this wave can emit is ready_for_validation. NEVER "final".
          //   ready_for_validation = candidate_tier + >=1 documentary corroborator (Codex gate validates -> promotes)
          //   candidate            = AO-reach (or other structural) signal only, no corroborator yet
          //   undetermined         = even the candidate tier is unresolved
          gate_status: { enum: ['ready_for_validation', 'candidate', 'undetermined'] },
          confidence: { enum: ['high', 'medium', 'low'] },
          stale_closed_note: { type: ['string', 'null'] }, // per-location: vacated/closed/relocated/false-positive note (null if active+clean)
          reasoning: { type: 'string' },
        },
        required: ['location_id', 'candidate_tier', 'pe_backed', 'owner_identity', 'network_id', 'signal_vs_evidence', 'evidence_urls', 'db_artifact', 'web_searched', 'gate_status', 'confidence', 'stale_closed_note', 'reasoning'],
      },
    },
  },
  required: ['network', 'network_id', 'owner_type_verdict', 'network_summary', 'owner_operator_identity', 'brand_trade_names', 'legal_entities', 'durable_artifacts', 'mso_platform_pe_evidence', 'stale_closed_false_positive_notes', 'evidence_chain', 'future_app_notes', 'classifications'],
}

const MODEL = `You are a dental ownership investigator producing CANDIDATE evidence rows for a downstream validation gate. You are given ONE authorized-official (AO) network: a single registered official who appears on the NPIs of 2+ distinct Chicagoland watched-IL GP locations.

WHAT AN AO CLUSTER IS — READ CAREFULLY:
A shared authorized official across NPIs is FEDERALLY OBSERVED shared owner/officer/admin identity. It is a HIGH-VALUE multi-location ownership-network CANDIDATE — it is NOT ownership proof by itself. The same official can be the owner, a practice manager, a credentialing/admin contact, a billing officer, or a corporate officer, depending on the record. So AO reach is a strong SIGNAL that points at a network; it becomes dentist_multi or stealth_dso ONLY after documentary corroboration. Never call AO reach "proof of ownership."

CANDIDATE TIERS (what the evidence points toward — not a final assignment). TAXONOMY CORRECTION 2026-06-21:
the DSO tiers are decided by STRUCTURE (MSO / management-services entity / centralized DSO platform / established
DSO brand), NOT by private equity. pe_backed is a SEPARATE boolean flag — pe_backed=false does NOT make something
dentist_multi. A non-PE, even family-owned, brand can still be a DSO if there is a management-company/MSO/platform layer.
1. dentist_multi  — a DENTIST who owns/operates 2+ offices as a private group with NO separate DSO/MSO/platform/
                    management-company structure (just a dentist's own multi-office practice). network_id="ao:LAST_FIRST". pe_backed=false.
2. stealth_dso    — local/friendly-PC trade names that are BACKED or MANAGED by a DSO/MSO/PE platform; requires
                    DOCUMENTARY MSO/management-services/MSA/PE evidence (a real URL/filing). pe_backed=true ONLY with a documentary PE sponsor; if it is MSO/management-backed but no PE found, keep stealth_dso with pe_backed=false.
3. branded_dso    — the offices operate under one public DSO brand OR sit under a DSO/platform/management-company
                    structure, EVEN IF family-owned / non-PE (e.g. a family-owned DSO with its own MSO entity). pe_backed=true ONLY if that brand has a documentary PE sponsor; otherwise branded_dso with pe_backed=false. Do NOT downgrade a real DSO brand/MSO to dentist_multi just because no PE was found.
4. institutional  — FQHC / hospital / health-system / university / government.
5. undetermined   — cannot resolve owner type from the web.

CORROBORATION BAR (Codex corrections #2, #3, #6) — gate_status rules:
- gate_status="ready_for_validation" requires the candidate_tier to be backed by >=1 DOCUMENTARY corroborator, entered in signal_vs_evidence.evidence AND evidence_urls:
    * official group website showing multiple locations, OR
    * a doctor/owner bio tying the named owner to multiple practices, OR
    * a shared legal entity / shared official brand across the locations, OR
    * same mailing address + same owner identity, OR
    * NPPES AO + a matching website/entity.
- For dentist_multi specifically: AO reach ALONE (no corroborator) is NOT enough for ready_for_validation -> set gate_status="candidate".
- For stealth_dso: REQUIRES documentary MSO/management-services/MSA/DSO-management (or PE) evidence (a real URL). Do NOT infer DSO backing from size, AO reach, or many ZIPs. A dentist-owned multi-location group is NOT a stealth DSO unless management/MSO/PE evidence exists -> if you only have reach and no management/MSO/PE doc, that's dentist_multi as candidate, NOT stealth_dso. (If you DO find an MSO/management layer but no PE, it is still stealth_dso/branded_dso with pe_backed=false — pe_backed is separate.)
- branded_dso / institutional: ready_for_validation needs a locator/official URL, a DSO/MSO/management-company filing, or an institutional affiliation match. A documented MSO/management-company layer qualifies a brand as branded_dso even when pe_backed=false — do NOT call it dentist_multi.
- If you cannot corroborate at all: candidate_tier stays your best structural guess (usually dentist_multi for a real multi-office AO) but gate_status="candidate", confidence reflects the doubt, and reasoning states what's missing. If even the tier is unclear -> candidate_tier="undetermined", gate_status="undetermined".

signal_vs_evidence (REQUIRED on every row, Codex correction #7):
- signal: the structural candidate signals only — e.g. "ao_reach=3 across 3 ZIPs", "shared_mailing", "ein_cluster", "name_chain". These come from the federal data; they are NOT evidence of ownership type.
- evidence: the documentary corroborators you actually found, each as a short description; the URL goes in evidence_urls. Empty evidence[] => gate_status must be "candidate" or "undetermined", never "ready_for_validation".

db_artifact: keep the federal fact {type:"ao_reach", authorized_official, reach, zips:[...]} — but it lives under SIGNAL, not evidence. It alone never makes a row ready_for_validation.

SPECIALIST EXCLUSION (this census is GP-only): if the network is specialist-dominant — ortho / endo / perio / oral & maxillofacial surgery / pediatric-only / implant-only by practice name or taxonomy (e.g. "The Dental Specialists", "Implant Solutions", "Orthodontic ...") — set candidate_tier="undetermined", gate_status="undetermined", and state "specialist network — exclude from GP denominator" in reasoning. Do NOT force a specialist network into a GP ownership tier.

RULES: NEVER fabricate a URL — if a search returns nothing, leave evidence_urls empty and use gate_status="candidate". NEVER assign true_independent (multi-office network by definition). Cap ~3 web searches per network (offices share an owner; research the OWNER once, apply to all its locations). Nothing you emit is "final" — the downstream gate validates and promotes; you produce ready_for_validation at most.

NETWORK INTELLIGENCE FIELDS (preserve everything you find — the downstream app keeps these even when not final):
- owner_operator_identity: the named owner/family/operator person(s) you documented (e.g. "Dr. Jane Doe DDS, founder"); null if unknown.
- brand_trade_names: every consumer-facing brand / DBA you saw across the offices (e.g. ["Smiling Dental", "Smiling Dental Group"]).
- legal_entities: PCs/LLCs/LTDs/management companies tied to the network (from NPPES parent-org, the website footer, or filings).
- durable_artifacts: NPPES-durable, re-checkable artifacts — shared EIN, shared mailing address, name-chain across distinct ZIPs, shared parent organization. Phrase each as a short fact.
- mso_platform_pe_evidence: if (and only if) you found a real MSO / management-company / DSO-platform / PE corroborator, summarize it with the URL; otherwise null. Do NOT invent one.
- stale_closed_false_positive_notes (network) + stale_closed_note (per-location): flag vacated shells, relocations, closed offices, or AO-cluster false positives (e.g. an AO who is a billing contact, not an owner; a specialist office that shouldn't be in a GP network).
- evidence_chain: a short narrative "AO signal -> documentary corroboration": what the federal AO-reach signal was, then what documentary evidence you found (or failed to find) to corroborate it.
- future_app_notes: what the app should remember about this network for later validation (open questions, what would confirm it, watch-items).

OUTPUT: call StructuredOutput once. owner_type_verdict + network_summary + the network-intelligence fields describe the whole network; classifications has ONE row per location in the cluster (same tier/pe_backed unless evidence splits them), each with its own location_id, signal_vs_evidence, stale_closed_note, and reasoning.`

// ── RANKED target list (single source of truth for this wave's coverage). Embedded as a literal because
// workflow scripts have NO filesystem access; mirrors RANKED_FILE.targets exactly (36 reach=3 + 15 strong
// reach=2 = 51). Generated from ao_network_evidence_reach3_ranked_targets_20260621.json. ──
const RANKED = [
  { ao: 'HILLARY THULL', reach: 3, rank: 1, linked: null },
  { ao: 'SIMONE WILSON-ADELEKE', reach: 3, rank: 2, linked: null },
  { ao: 'KOUSHAN AZAD', reach: 3, rank: 3, linked: null },
  { ao: 'SCOTT GOLDMAN', reach: 3, rank: 4, linked: null },
  { ao: 'BEN MEHTA', reach: 3, rank: 5, linked: null },
  { ao: 'SYED REHMAN', reach: 3, rank: 6, linked: null },
  { ao: 'SAWSAN ASFOUR', reach: 3, rank: 7, linked: null },
  { ao: 'JIANJUN HAO', reach: 3, rank: 8, linked: 'Smiling Dental Group — backfill71 individual (Pulaski, dentist_multi); DB affiliated_dso hint may be mislabel' },
  { ao: 'RESHMA DHAKE', reach: 3, rank: 9, linked: null },
  { ao: 'MOHAMMED SAYEED', reach: 3, rank: 10, linked: null },
  { ao: 'LINH TRAN', reach: 3, rank: 11, linked: null },
  { ao: 'FARIDEH DAFTARY', reach: 3, rank: 12, linked: null },
  { ao: 'NICOLE WILLIS', reach: 3, rank: 13, linked: null },
  { ao: 'MOHAMMAD MOEIN AZIMI', reach: 3, rank: 14, linked: null },
  { ao: 'ROBERT STITES', reach: 3, rank: 15, linked: null },
  { ao: 'BELLA ZARITSKY', reach: 3, rank: 16, linked: null },
  { ao: 'SUNITA SAHU', reach: 3, rank: 17, linked: null },
  { ao: 'VESNA SUTTER', reach: 3, rank: 18, linked: null },
  { ao: 'MUZAFFAR MIRZA', reach: 3, rank: 19, linked: null },
  { ao: 'DEEPAK AGARWAL', reach: 3, rank: 20, linked: null },
  { ao: 'SAQIB MOHAJIR', reach: 3, rank: 21, linked: null },
  { ao: 'AMJAD MAHAIRI', reach: 3, rank: 22, linked: null },
  { ao: 'INCHUN YANG', reach: 3, rank: 23, linked: null },
  { ao: 'REEM SHAFI', reach: 3, rank: 24, linked: 'possible SHAFI family network (backfill71 SHAFI x17)' },
  { ao: 'MICHAEL TEUSCHER', reach: 3, rank: 25, linked: null },
  { ao: 'JOSEPH FORNAL', reach: 3, rank: 26, linked: null },
  { ao: 'YAQIN DAWOUD', reach: 3, rank: 27, linked: null },
  { ao: 'YOSIF JABIR', reach: 3, rank: 28, linked: null },
  { ao: 'ZUZANA VITKOVA', reach: 3, rank: 29, linked: null },
  { ao: 'JONATHAN VILLANUEVA', reach: 3, rank: 30, linked: null },
  { ao: 'CRYSTAL BARRON', reach: 3, rank: 31, linked: null },
  { ao: 'WILLIAM LI', reach: 3, rank: 32, linked: null },
  { ao: 'ANNA PELAK', reach: 3, rank: 33, linked: null },
  { ao: 'SINAN RAZZAK', reach: 3, rank: 34, linked: 'Image Dental / Dental Town Chicago — backfill71 second pass (branded_dso, 12 offices)' },
  { ao: 'MOHAMMED SALIH', reach: 3, rank: 35, linked: 'Teeth Matter/Salih Dental — backfill71 individual (dentist_multi)' },
  { ao: 'ANITA SHAHIN', reach: 3, rank: 36, linked: null },
  { ao: 'SUNIL EAMANI', reach: 2, rank: 37, linked: null },
  { ao: 'CHRISTINE BARBER', reach: 2, rank: 38, linked: null },
  { ao: 'KAMAL VIBHAKAR', reach: 2, rank: 39, linked: null },
  { ao: 'RICHARD CONEN', reach: 2, rank: 40, linked: null },
  { ao: 'CASSANDRA PETERSEN', reach: 2, rank: 41, linked: null },
  { ao: 'KIM WILSON', reach: 2, rank: 42, linked: null },
  { ao: 'IVANA BUENO', reach: 2, rank: 43, linked: null },
  { ao: 'BEHZAD SANEI', reach: 2, rank: 44, linked: null },
  { ao: 'MUSTAPHA HOTAIT', reach: 2, rank: 45, linked: null },
  { ao: 'KENDRA WALKER', reach: 2, rank: 46, linked: null },
  { ao: 'HARRY VARVARESSOS', reach: 2, rank: 47, linked: null },
  { ao: 'LAWRENCE WHITE', reach: 2, rank: 48, linked: null },
  { ao: 'LAWRENCE MULVANEY', reach: 2, rank: 49, linked: null },
  { ao: 'MANISSA LAMPMAN', reach: 2, rank: 50, linked: null },
  { ao: 'PETER PULLARA', reach: 2, rank: 51, linked: null },
]
const NETWORKS = RANKED.map((t) => t.ao)
const reachByAO = Object.fromEntries(RANKED.map((t) => [t.ao, t.reach]))
const rankByAO = Object.fromEntries(RANKED.map((t) => [t.ao, t.rank]))
const linkedByAO = Object.fromEntries(RANKED.map((t) => [t.ao, t.linked || null]))
const N_REACH3 = RANKED.filter((t) => t.reach === 3).length
const N_REACH2 = RANKED.filter((t) => t.reach === 2).length

phase('Networks')
log(`AO Wave 3 [ranked reach=3 + strong reach=2]: ${NETWORKS.length} networks (reach3=${N_REACH3}, reach2_strong=${N_REACH2})`)
const results = await parallel(NETWORKS.map((ao) => () => {
  const linked = linkedByAO[ao]
  const linkedNote = linked
    ? `\n\nPRIOR-WORK LINKAGE (note, do not assume): this AO has prior-session linkage — ${linked}. Treat this cluster's locations as NEW unless the location_id already appeared in a completed wave; if your evidence ties it to that prior network, say so in future_app_notes, but still classify the locations listed here.`
    : ''
  return agent(
    `${MODEL}

YOUR TASK: Read the JSON file at ${TARGETS}. In its "ao_clusters" array, find the cluster whose "authorized_official" == "${ao}" (reach=${reachByAO[ao]}). It lists every location_id in that AO's network with name/dba/address/city/zip/ein/parent_company/affiliated_dso. Investigate the OWNER (${ao}) on the web to CORROBORATE whether this is a dentist-owned group (dentist_multi), a PE/MSO group (stealth_dso, documentary PE/MSO evidence required), a DSO brand (branded_dso), or institutional — then emit one classification row per location in that cluster, plus the network-intelligence fields. network = "${ao}".${linkedNote}

DURABILITY: BEFORE your final StructuredOutput call, write your complete findings as pretty JSON to the file "${RAW_DIR}/${ao.replace(/[^A-Za-z0-9]+/g, '_')}.json" using the Write tool (same shape as StructuredOutput: the network fields + classifications array). This is a durable raw artifact for assembly; the StructuredOutput call is still required and authoritative.`,
    { label: `net:${ao.split(' ')[0]}`, phase: 'Networks', model: 'sonnet', schema: SCHEMA }
  )
}))

const ok = results.filter(Boolean)
const allClass = ok.flatMap((r) => (r.classifications || []).map((c) => ({ ...c, _network: r.network, _verdict: r.owner_type_verdict })))

// TAXONOMY CORRECTION 2026-06-21 (gate-owner): the DSO tiers are decided by MSO/management-services/
// platform/DSO-brand STRUCTURE, not by private equity. pe_backed=false does NOT auto-downgrade a DSO to
// dentist_multi. hasPlatformEvidence() scans the row's own text (owner_identity/reasoning/verdict/evidence/
// signal/db_artifact) for a real DSO/MSO/management/platform layer, stripping negations ("no MSO", "not
// PE-backed") so a denial does not false-positive.
function hasPlatformEvidence(c) {
  const sve = c.signal_vs_evidence || {}
  const txt = [c.owner_identity, c.reasoning, c._verdict, ...(sve.evidence || []), ...(sve.signal || []),
    c.db_artifact ? JSON.stringify(c.db_artifact) : ''].filter(Boolean).join(' || ')
  const cleaned = txt.replace(
    /\b(no|not|without|zero|lacks?|absent|none of|did not find|could not find|no evidence of)\b[^.|]*?(mso|dso|management|platform|private equity|\bpe\b|msa)[^.|]*/gi, ' ')
  return /(managed by|management serv|management compan|\bmso\b|\bdso\b|support organization|dental support org|\bplatform\b|portfolio company|private equity|capital partners|\bmsa\b|"affiliated_dso"\s*:\s*"|"parent_company"\s*:\s*"|"entity_classification"\s*:\s*"dso|friendly[- ]?pc|centralized|holding compan)/i.test(cleaned)
}

// Defensive re-gate (Codex correction #2/#3): a row is ready_for_validation ONLY with >=1 real
// documentary corroborator. Trust the artifact, not the agent's self-label.
for (const c of allClass) {
  const ev = (c.signal_vs_evidence && c.signal_vs_evidence.evidence) || []
  const hasUrl = (c.evidence_urls || []).length > 0
  const corroborated = hasUrl && ev.length > 0
  const platform = hasPlatformEvidence(c)
  if (c.gate_status === 'ready_for_validation' && !corroborated) {
    c.gate_status = c.candidate_tier === 'undetermined' ? 'undetermined' : 'candidate'
    c._regated = 'downgraded: no documentary corroborator (AO reach is signal, not evidence)'
  }
  // stealth_dso with neither a URL nor any platform/MSO evidence is just an AO-reach guess -> dentist_multi candidate.
  // If platform/MSO evidence IS present, keep stealth_dso even without a clean URL (pe_backed stays as found).
  if (c.candidate_tier === 'stealth_dso' && !hasUrl && !platform) {
    c.candidate_tier = 'dentist_multi'; c.pe_backed = false; c.gate_status = 'candidate'
    c._regated = (c._regated ? c._regated + '; ' : '') +
      'stealth_dso->dentist_multi candidate: no URL and no MSO/management/platform evidence'
  }
  // TAXONOMY CORRECTION 2026-06-21: downgrade branded_dso -> dentist_multi ONLY when there is NO
  // MSO/management/platform/DSO-brand evidence. A real DSO brand or MSO/management layer stays branded_dso
  // EVEN IF pe_backed=false (DSO structure -> DSO/PE headline; PE is a separate flag).
  if (c.candidate_tier === 'branded_dso' && !platform) {
    c.candidate_tier = 'dentist_multi'
    c._regated = (c._regated ? c._regated + '; ' : '') +
      'branded_dso->dentist_multi: no MSO/management/platform/DSO-brand evidence found (dentist-owned multi only)'
  }
  c._platform_evidence = platform
  c._reach = reachByAO[c._network] ?? null
  c._rank = rankByAO[c._network] ?? null
}
const verdicts = {}, tiers = {}, gates = {}
for (const r of ok) verdicts[r.owner_type_verdict] = (verdicts[r.owner_type_verdict] || 0) + 1
for (const c of allClass) { tiers[c.candidate_tier] = (tiers[c.candidate_tier] || 0) + 1; gates[c.gate_status] = (gates[c.gate_status] || 0) + 1 }
const readyForVal = allClass.filter((c) => c.gate_status === 'ready_for_validation')
log(`Done: ${ok.length}/${NETWORKS.length} networks, ${allClass.length} locations. verdicts=${JSON.stringify(verdicts)}`)
log(`tiers=${JSON.stringify(tiers)} gate=${JSON.stringify(gates)} ready_for_validation=${readyForVal.length}`)
return {
  wave: 'ao_network_reach3_ranked', standard: 'corrected_2026-06-21', emits: 'ready_for_validation_max',
  networks_ok: ok.length, networks_total: NETWORKS.length, n_locations: allClass.length,
  verdict_tally: verdicts, tier_tally: tiers, gate_tally: gates, n_ready_for_validation: readyForVal.length,
  raw_dir: RAW_DIR,
  network_summaries: ok.map((r) => ({
    network: r.network, network_id: r.network_id, reach: reachByAO[r.network] ?? null, rank: rankByAO[r.network] ?? null,
    verdict: r.owner_type_verdict, summary: r.network_summary,
    owner_operator_identity: r.owner_operator_identity ?? null,
    brand_trade_names: r.brand_trade_names || [], legal_entities: r.legal_entities || [],
    durable_artifacts: r.durable_artifacts || [], mso_platform_pe_evidence: r.mso_platform_pe_evidence ?? null,
    stale_closed_false_positive_notes: r.stale_closed_false_positive_notes ?? null,
    evidence_chain: r.evidence_chain || '', future_app_notes: r.future_app_notes || '',
    linked_prior_work: linkedByAO[r.network] ?? null,
    n: (r.classifications || []).length,
  })),
  classifications: allClass,
}
