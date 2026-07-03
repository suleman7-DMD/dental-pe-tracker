export const meta = {
  name: 'ao-network-evidence',
  description: 'Investigate top authorized-official networks as multi-location ownership CANDIDATES. Separate signal (AO reach) from evidence (corroborating URL/entity). Emits ready_for_validation rows only — never final, never DB/ownership_tier.',
  phases: [{ title: 'Networks', detail: 'one agent per AO network, corroborate owner type with documentary evidence' }],
}

const TARGETS = '/Users/suleman/dental-pe-tracker/data/dso_research/ownership_evidence_targets_20260621.json'
const RAW_DIR = '/Users/suleman/dental-pe-tracker/data/dso_research/_reach4_raw_20260621'
// ╔══════════════════════════════════════════════════════════════════════════════════════════╗
// ║ ✅ CLEARED + RUN 2026-06-21 (reach==4 batch ONLY) per explicit user GO: "Launch Hidden Local ║
// ║ Consolidator Discovery Wave 2 — Main AO lane. Use the staged reach=4 AO batch ... explicitly  ║
// ║ cleared as evidence-only work." Evidence-only: NO DB writes, NO consolidation.                ║
// ║ Waves done: top-8 (wave 1) + reach>=5 (wave 2, 14) + reach==4 (wave 2 main, this run, 14).     ║
// ║ ⛔ STILL HELD: the reach 2-3 long tail is NOT cleared — do NOT run it without a fresh user GO.  ║
// ╚══════════════════════════════════════════════════════════════════════════════════════════╝
// Staged reach==4 batch (14 clusters; excludes the 8 top + 14 reach>=5 already done waves 1-2).
// Known DSO suspect in this batch: Huerta (Dental Professionals of Illinois P.C. = Heartland friendly-PC,
// already dso_national). Taxonomy: branded_dso/stealth_dso is decided by MSO/DSO/platform/management-company
// structure, NOT by pe_backed (pe_backed is a SEPARATE flag). Keep specialist exclusion.
const NETWORKS = [
  'BELINDA HUERTA', 'LAWRENCE GROH', 'OSCAR GONZALEZ', 'STEVE NAPIER',
  'MOHAMED WAHEED', 'KHALIL TAKLA', 'LINDSAY BEARDEN', 'STEVEN REMPAS',
  'AROON PAL', 'ABHISHEK NAGARAJ', 'DIMITRI HARALAMPOPOULOS', 'ROSHAN PARIKH',
  'PHIL KURAL', 'NATHAN HOFFMAN',
]

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
- signal: the structural candidate signals only — e.g. "ao_reach=7 across 5 ZIPs", "shared_mailing", "ein_cluster", "name_chain". These come from the federal data; they are NOT evidence of ownership type.
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

phase('Networks')
log(`AO-network evidence [corrected standard]: ${NETWORKS.length} networks -> ${NETWORKS.join(', ')}`)
const results = await parallel(NETWORKS.map((ao) => () =>
  agent(
    `${MODEL}

YOUR TASK: Read the JSON file at ${TARGETS}. In its "ao_clusters" array, find the cluster whose "authorized_official" == "${ao}". It lists every location_id in that AO's network with name/dba/address/city/zip/ein/parent_company/affiliated_dso. Investigate the OWNER (${ao}) on the web to CORROBORATE whether this is a dentist-owned group (dentist_multi), a PE/MSO group (stealth_dso, documentary PE/MSO evidence required), a DSO brand, or institutional — then emit one classification row per location in that cluster, plus the network-intelligence fields. network = "${ao}".

DURABILITY: BEFORE your final StructuredOutput call, write your complete findings as pretty JSON to the file "${RAW_DIR}/${ao.replace(/[^A-Za-z0-9]+/g, '_')}.json" using the Write tool (same shape as StructuredOutput: the network fields + classifications array). This is a durable raw artifact for assembly; the StructuredOutput call is still required and authoritative.`,
    { label: `net:${ao.split(' ')[0]}`, phase: 'Networks', model: 'sonnet', schema: SCHEMA }
  )
))

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
  // TAXONOMY CORRECTION 2026-06-21 (supersedes the Belkic/Aqel blunt rule): downgrade branded_dso ->
  // dentist_multi ONLY when there is NO MSO/management/platform/DSO-brand evidence. A real DSO brand or
  // MSO/management layer stays branded_dso EVEN IF pe_backed=false (it lands in the DSO/PE headline because
  // it is a DSO structure; PE is a separate flag). e.g. Dental Dreams / KOS Services MSO = branded_dso, pe_backed=false.
  if (c.candidate_tier === 'branded_dso' && !platform) {
    c.candidate_tier = 'dentist_multi'
    c._regated = (c._regated ? c._regated + '; ' : '') +
      'branded_dso->dentist_multi: no MSO/management/platform/DSO-brand evidence found (dentist-owned multi only)'
  }
  // Keep pe_backed honest: it should be true only with documentary PE evidence, never set merely by tier.
  c._platform_evidence = platform
}
const verdicts = {}, tiers = {}, gates = {}
for (const r of ok) verdicts[r.owner_type_verdict] = (verdicts[r.owner_type_verdict] || 0) + 1
for (const c of allClass) { tiers[c.candidate_tier] = (tiers[c.candidate_tier] || 0) + 1; gates[c.gate_status] = (gates[c.gate_status] || 0) + 1 }
const readyForVal = allClass.filter((c) => c.gate_status === 'ready_for_validation')
log(`Done: ${ok.length}/${NETWORKS.length} networks, ${allClass.length} locations. verdicts=${JSON.stringify(verdicts)}`)
log(`tiers=${JSON.stringify(tiers)} gate=${JSON.stringify(gates)} ready_for_validation=${readyForVal.length}`)
return {
  wave: 'ao_network', standard: 'corrected_2026-06-21', emits: 'ready_for_validation_max',
  networks_ok: ok.length, networks_total: NETWORKS.length, n_locations: allClass.length,
  verdict_tally: verdicts, tier_tally: tiers, gate_tally: gates, n_ready_for_validation: readyForVal.length,
  raw_dir: RAW_DIR,
  network_summaries: ok.map((r) => ({
    network: r.network, network_id: r.network_id, verdict: r.owner_type_verdict, summary: r.network_summary,
    owner_operator_identity: r.owner_operator_identity ?? null,
    brand_trade_names: r.brand_trade_names || [], legal_entities: r.legal_entities || [],
    durable_artifacts: r.durable_artifacts || [], mso_platform_pe_evidence: r.mso_platform_pe_evidence ?? null,
    stale_closed_false_positive_notes: r.stale_closed_false_positive_notes ?? null,
    evidence_chain: r.evidence_chain || '', future_app_notes: r.future_app_notes || '',
    n: (r.classifications || []).length,
  })),
  classifications: allClass,
}
