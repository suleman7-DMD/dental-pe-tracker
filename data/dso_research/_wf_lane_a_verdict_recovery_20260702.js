export const meta = {
  name: 'lane-a-verdict-recovery',
  description: 'Opus 4.8 adversarial verification of wave 1+2 DSO claims whose verifiers were rate-limit-killed',
  phases: [
    { title: 'Verify DSO claims', detail: 'one Opus 4.8 verifier per result file carrying unverified T4/T5 rows', model: 'claude-opus-4-8' },
  ],
}

const ARGS = typeof args === 'string' ? JSON.parse(args) : args
const FILES = ARGS.files
if (!Array.isArray(FILES) || !FILES.length) throw new Error('args.files must be a non-empty array of result file paths')

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

function verifyPrompt(file) {
  return `You are an adversarial ownership verifier for a PE-consolidation census. Read ${file} (use the Read tool) — a JSON file with a "classifications" array. Extract every row whose assigned_tier is "stealth_dso" or "branded_dso": these are DSO claims made by another research agent. They move a PE-consolidation headline metric, so your job is to REFUTE them if possible. Load WebSearch/WebFetch via ToolSearch "select:WebSearch,WebFetch" if needed.

For EACH such row: independently check its evidence_urls (fetch them) and run at least one independent web search of your own. Ask: does the cited page actually place THIS street address under the claimed brand/controller? Is the "DSO" actually a dentist-owned group (that would be DOWNGRADE_T3)? Is this a name collision with a different practice? Is the URL dead or irrelevant?

Verdicts: CONFIRM (evidence genuinely supports the DSO tier), REFUTE (evidence contradicts or does not support it), DOWNGRADE_T3 (real multi-location network but demonstrably dentist-owned), INSUFFICIENT (cited evidence too weak to confirm; default here if uncertain).

Return the structured output: unit_id = the file's unit_id field, and one verdict per DSO-claim row keyed by that row's location_id, each with 1-2 sentence notes and urls_checked. Do NOT write or modify any file.`
}

phase('Verify DSO claims')
const out = await parallel(FILES.map(f => () =>
  agent(verifyPrompt(f), {
    label: `verify:${f.split('/').pop()}`,
    phase: 'Verify DSO claims',
    schema: VERDICT_SCHEMA,
    model: 'claude-opus-4-8',
    agentType: 'general-purpose',
  }).then(v => ({ file: f, unit_id: v ? v.unit_id : null, verdicts: v ? v.verdicts : null }))
))

const ok = out.filter(x => x && x.verdicts)
const tally = { CONFIRM: 0, REFUTE: 0, DOWNGRADE_T3: 0, INSUFFICIENT: 0 }
for (const u of ok) for (const v of u.verdicts) if (tally[v.verdict] !== undefined) tally[v.verdict] += 1
log(`Verdict recovery: ${ok.length}/${FILES.length} units verified — CONFIRM ${tally.CONFIRM} / REFUTE ${tally.REFUTE} / DOWNGRADE_T3 ${tally.DOWNGRADE_T3} / INSUFFICIENT ${tally.INSUFFICIENT}`)
return { tally, units: out }