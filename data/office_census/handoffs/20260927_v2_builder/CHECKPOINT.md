# Office census v2 builder: checkpoint 2 (2026-09-27 late; session wrapped at the user's request)

**Read this file, then start work.** The next-session prompt is `NEXT_PROMPT.txt` next to this
file (also on `handoffs/20260926_task_c_lite/OFFICE_CENSUS_HANDOFF.html#v2-builder`). The plan
`data/office_census/V2_PLAN_2026-09-27.md` is background. Read a section of it only when you need
that section. Checkpoint 1's content is folded in below; nothing else is needed to resume.

## 1. Where things stand (rows; store pull 2026-09-27 after the publish)

| | Rows |
|---|---:|
| Rapid queue | 4,022 |
| Checked | 3,332 (690 not yet checked) |
| Resolved (VALID 291 · VALID_CORRECTED 1,141 · NOT_CURRENT_GP 772) | **2,204 / 3,332 = 66.1%** |
| Unresolved (IDENTITY_ONLY 647 · ESCALATE 232 · IDENTITY_PROBLEM 223 · NO_WEB_EVIDENCE 26) | **1,128** (was 1,358 at the freeze, 2026-09-27 08:21 UTC) |
| **v2 published live this session** | **230 of the frozen 1,358 (16.9%)** |
| Mission target (80% of 1,358) | 1,087, so **857 still to go** |

- **Live on the Directory:** 230 rows. The session is `v2-auto-20260927`, researcher
  `claude-v2-builder`, validator rules `rapid-2026-09-28.v2`, rule set `v2-rules-2026-09-27.3`.
  All 230 came back `live`: 0 held, 0 rejected. Removal share after the publish: 772 of 3,332
  live rows = 23.2% globally (limit 35%) and exactly 115 of 230 = 50% in the session (limit
  "more than 50%").
- **Nothing is running.** No background jobs, and no commits or pushes. The IEMA crawl and the
  browser probe resume from their caches.
- **The store had one open claim** (`rv-0927-0056-420e`, 10 rows) from an earlier v1 session.
  I did not touch it.

## 2. What was published, and why only this

| Rule | Decision | Rows |
|---|---|---:|
| PL-RECENT: Google listing at the site, tied by the row's name, a review within 365 days | VALID | 52 |
| PL-IEMA: tied Google listing + an IEMA Open X-ray facility at the site, the same office | VALID | 49 |
| IEMA-LIC: IEMA facility tied by phone AND name/administrator + an active IDFPR license | VALID | 11 |
| FP-SITE: the office's own site (real browser) gives this address; the row's name ties | VALID | 3 |
| PL-CLOSED: a Google listing tied to the row (name/dentist) is permanently closed; nothing operates at the site | NOT_CURRENT_GP closed | 56 |
| MOVED-PH: the row's phone AND name/dentist belong to an operating office in another ZIP, or to another row's office | NOT_CURRENT_GP moved | 31 |
| LIC-CLOSED: every row dentist's IDFPR license is non-active + no X-ray registration, Google dental listing or office website at the site | NOT_CURRENT_GP closed | 28 |

**Publish policy** (`publish_tier()` in `scrapers/office_census_v2_rules.py`). It is deliberately
narrower than the engine's "auto" tier. It answers the analyst's review (the user pasted it
2026-09-27) as follows:
- **No Google display name overwrites a row name.** Successor or rebrand name corrections and
  duplicates wait for an agent or a first-party page. This round also held VALID_CORRECTED
  rows, whose corrected values come from Places content.
- **VALID needs the row's own name tied**, or a row named after its dentist. A dentist-only tie
  could confirm a wrong practice name (the "Peacock Dental" case).
- **Rows v1 marked IDENTITY_PROBLEM or ESCALATE/gp_scope keep that question** for an agent.
- **MOVED-PH publishes only with a name or dentist tie.** A phone-only tie can be a number
  handed to a buyer (the "Illinois Dental Arts → Van Beek" case).
- **MOVED-D, SUCCESSOR and SPEC-L never publish.** In the spot check, 2 of 4 MOVED-D samples
  matched a different dentist of the same name.

**Evidence for publishing (not proof):**
- **Control direction errors of the publish tier:** 1 of 250 open controls would be removed
  (Dental Limited: Google and IEMA both show Buffalo Grove, so the v1 label is disputed). 1 of
  366 not-open controls would be opened, and it is a VALID_CORRECTED row this round did not
  publish.
- **Spot check:** 32 auto proposals were read by hand; the misfires found were fixed or held,
  as above.
- **The controls are v1's labels, not ground truth.** The independent test is still to come:
  - 19 of the 100 hand-check rows are among the 230 published; my proposals for all 100 are in
    `data/office_census/v2/hand_check_v2_proposals_2026-09-27.csv`. The user should fill the
    hand check blind first.
  - The hand check was **0 of 100 filled** at 2026-09-27.

**Rollback is by class.** Every published entry carries `rule_id`, `packet_id`, the session and
the rules version.
- The exact records are in `data/office_census/v2/PUBLISH_2026-09-27_records.jsonl` (our wording,
  Maps links and registry lines only).
- The packets they were decided from are in
  `staging/v2_probes/published_packets_20260927.jsonl` (gitignored; Places content, purge after
  30 days).
- If an audit fails a rule, supersede that rule's rows with `supersede: true` records.

**82 publishable removals wait for the removal brake**
(`data/office_census/v2/PUBLISH_2026-09-27_waiting_for_brake.jsonl`: LIC-CLOSED 43 + HOME-R 39,
all validator-clean).
- They go live in a later session once that session has recorded at least as many opens.
- Never split sessions to get around the brake.
- Regenerate the file before recording: rows may have been re-checked since (`publish-records`
  skips any row whose latest check changed).

## 3. Cost (exact, from `places-cost`; month 2026-09)

| SKU (Places API New) | Used | Free / month | Left | Price after the free allotment |
|---|---:|---:|---:|---|
| Text Search Pro `search_pro` | 1,999 | 5,000 | 3,001 | $32 / 1,000 |
| Text Search Enterprise `search_ent` | 915 | 1,000 | 85 | $35 / 1,000 |
| Text Search Enterprise+Atmosphere `search_ent_atmos` | 1,000 | 1,000 | **0** | $40 / 1,000 |
| Place Details Enterprise `details_ent` | 76 | 1,000 | 924 | $20 / 1,000 |
| Place Details Enterprise+Atmosphere `details_ent_atmos` | 1,000 | 1,000 | **0** | $25 / 1,000 |

**Spend: $0.00.**
- The ledger counts each call before it is sent, so it overcounts slightly. For example, 2
  calls were logged for 1 row a crashed chunk never saved.
- All other levers are free: IEMA and IDFPR are public registries, and the browser probe is
  local Chrome.
- **The allotments reset October 1.** Until then, review-date lookups (`details_ent_atmos`)
  and the Atmosphere phone search are **exhausted**. `--cap 0` (the default) makes the probe
  hold those calls rather than pay.
- The ledger cannot see other usage on the same billing account. The user should keep a
  budget alert on it.

**Places key:** `GOOGLE_PLACES_API_KEY` in `~/dental-pe-tracker/.env`; the probe reads it itself.
Never print it, and never copy a `.env` into this worktree: it would shadow `RAPID_TOKEN`, and
the repo is public.

## 4. What changed this session (all uncommitted)

| File | Change |
|---|---|
| `scrapers/office_census_v2_probes.py` | **Places scheme 2:** one Enterprise(+Atmosphere) Text Search by phone returns phone, website and reviews for up to 5 places, so no Details call is needed. It is followed by "dentist <address>" on Pro, and a name search only if nothing is tied. Omitted-field markers stop wasted refetches.<br>**Other subcommands:**<br>- `places-reviews`: one Details+Atmosphere lookup for each row's deciding listing.<br>- browser v2: address context, dentists and status text; exact pages on file; priority for rows with no proposal; `--max-seconds`.<br>- `packets`: adds `other_rows_site`, `phone_listings` and the new `elsewhere_listings`.<br>- **`publish-records`**: writes validated `record` input for the rows `publish_tier` allows and caps removals at the brake. |
| `scrapers/office_census_v2_rules.py` | `v2-rules-2026-09-27.3`.<br>**Identity model:** identity ties (name/dentist) vs place-only ties (phone/website) → P1 successor or duplicate.<br>**Weak or ambiguous evidence:** practitioner listings count only when the phone ties; multi-tenant buildings go to review; place-only ties need a recent review.<br>**Rule changes:** MOVED-PH ties and in-ZIP abstain; new **MOVED-D** (review-only); HOME-R needs residential form + nothing dental; SPEC-L uses the strict Google type.<br>**Quotes** use our own wording (no Google names or addresses).<br>**`publish_tier()`** added. |
| `scrapers/office_census_rapid.py` | **Validator v2.**<br>- `V2_RULES = "rapid-2026-09-28.v2"`, `V2_RULE_IDS` (incl. `AGENT` for the future v2 agent lane).<br>- Kinds `places_listing` and `license_registry`; places/IEMA count as current evidence **only** in a record citing `rule_id` + `packet_id`, which may have 0 searches.<br>- Signals `split_from_mixed_row`, `license_inactive`, `domain_hijacked`.<br>- `make_entry` stamps the v2 rules. v1 behaviour is unchanged. |
| `scrapers/test_office_census_v2_rules.py` (new) | 17 tests: each rule's case plus the must-abstain look-alikes and the publish tier |
| `scrapers/test_office_census_rapid.py` | +6 v2 validator tests. All 45 rapid + store tests pass. |
| `data/office_census/RAPID_VALIDATION_RUNBOOK.md` | **v1 improvements for the looper:**<br>- a free IDFPR license check (a curl, not a search);<br>- policy P1, "the row is the place": a successor at the same suite is VALID_CORRECTED, not closed;<br>- traps: phone/website continuity ≠ identity; personal-name listings outlive offices; absence needs a positive companion.<br>**Cloud looper sessions read the branch, so this reaches them only after a commit + push.** |
| `data/office_census/v2/` | `PUBLISH_2026-09-27_records.jsonl` (230), `PUBLISH_2026-09-27_waiting_for_brake.jsonl` (82), `hand_check_v2_proposals_2026-09-27.csv` |

**Caches** (`data/office_census/staging/v2_probes/`, gitignored):
- `targets` 1,974.
- `places` covers all 1,974 targets (scheme 2), plus review re-appends; `places_ledger` 4,990.
- `iema_profiles` 3,161 of ~3,643 facilities.
- `browser` 649 keys cached (live_dental 461, dns_dead 55, live_not_dental 34, parked 28, …);
  1,714 keys still to open.
- `packets` 1,974.

## 5. The 1,128 still unresolved (packet evaluation 2026-09-27)

| Bucket | Rows | Route |
|---|---:|---|
| Publishable removals waiting on the brake | 82 | Next session, interleaved with opens |
| VALID_CORRECTED (phone), values from Places content | 6 | Agent confirms on a first-party page or IEMA |
| Review-confidence proposals (conflicts, successors, multi-tenant, negative v1 signal, MOVED-D) | 272 | v2 agent lane: confirm or reject the proposal |
| MOVED-PH phone-only (number may have gone to a buyer) | 43 | v2 agent lane |
| Open proposal, but the row's name is not tied (name correction needed) | 37 | v2 agent lane |
| IDENTITY_PROBLEM 14 · gp_scope 4 · successor/duplicate 19 · name/website correction 3 | 40 | v2 agent lane |
| **No proposal** | **648** | see below |

The 648 with no proposal:

| Situation | Rows | Cheapest next lever |
|---|---:|---|
| Nothing dental at the site; a row dentist's license ACTIVE | 120 | Where does the dentist practice now? An agent with 1–2 searches (moved vs home vs unlisted) |
| Tied Google listing at the site, no review in 12 months | 109 | Stale or quiet office: the browser (website) or an agent phone/web check |
| Tied Google listing at the site, review dates unknown | 106 | **Oct 1:** 106 `details_ent_atmos` lookups (free) → PL-RECENT |
| Only untied operating listings at the site | 97 | P1 successor or other tenant: an agent (suite-level) |
| Nothing dental at the site; license unmatched in IDFPR | 94 | Name-match repair (middle names, hyphenation), then LIC-CLOSED/HOME-R |
| Row phone listed at another address | 85 | In-ZIP moves (VALID_CORRECTED address), specialists, stale |
| IEMA facility at the site, no Google or website tie | 26 | Browser or agent |
| Nothing at the site; license mixed/non-active | 10 | Agent |
| Closed listing at the site not tied to the row | 1 | Agent |

**Honest yield view:**
- Deterministic rules put *a* proposal on 710 of 1,358 (52.3%); 318 (23.4%) passed the
  publish tier, 230 of which are live.
- Reaching 80% (1,087) needs three more things: the v2 agent lane over the ~392 held
  proposals, the October review lookups, and an agent pass over the no-proposal buckets.
- **Do not reach 80% by loosening rules.**

## 6. Policy findings and disagreements (for the user)

- **P1 conflicts with v1 practice.** v1 removed successor rows as closed: Engen→Bright
  Valley, Bork→Aura, Sandstrom→Magnolia, Sanders→HP Smiles, Pasha→Ascend.
  - 179 checks carry the `successor_practice` signal.
  - Recommend a v2 re-check of v1 NOT_CURRENT_GP rows with that signal. Under P1 they are
    VALID_CORRECTED, or duplicates.
- **Relabel the controls under P1 before Gate A** (the analyst agrees). 18 not-open controls
  get successor-type open proposals at review confidence (9 closed + 9 moved). Many are
  probably v1 errors under P1.
- **Disputed control labels:**
  - Dental Limited (open control; Google + IEMA show Buffalo Grove, the site had a
    connect_error).
  - Four Seasons Dental Studio (closed control with current evidence).
- **Where I disagree with the analyst:** "publish nothing yet" was too strict for a narrow,
  class-reversible tier. That tier made 2 direction errors in 616 controls, and both are
  disputed labels. Its hand-read spot check found errors only in rules that were then held
  back. I agree on everything else: no Google name overwrites, relabel the controls, freeze the
  rules before the blind audit, and don't weaken rules to chase 80%.
- **Absence-based removal requires a positive companion signal:** lapsed licenses, a
  residential address form, or the practice's own current listing elsewhere. This is now both
  rule behaviour and v1 runbook guidance.

## 7. Next steps (in order)

1. **Verify (§8).** Pull the store (`python3 scrapers/office_census_rapid.py pull`,
   read-only). If the v1 looper ran since, recount before quoting any number.
2. **Audit the publish** before building more. For a random 40 of the 230 (seed it; stratify
   by rule), open the Maps link or registry line and do at most 1 web search each. Record
   correct/incorrect in `data/office_census/v2/audit_publish_2026-09-27.csv`.
   - If any rule class has ≥2 errors, supersede that class's rows and tighten the rule.
   - Compare with the hand check if the user has filled it.
3. **Finish the free probes** in ~3-minute foreground chunks. The user forbids background
   jobs and pollers.
   - `iema-profiles --max-seconds 170` (~480 left).
   - `browser --concurrency 6 --max-seconds 165` (1,714 keys, rows without a proposal first).
   - Then `packets`, and recount.
4. **Relabel the controls under P1**, then rerun Gate A: each publishable rule needs ≤3%
   stale positives on the not-open controls.
5. **Build the v2 agent lane.**
   - `next --lane v2` in `office_census_rapid.py` hands an agent a row plus a compact packet
     summary: our wording, Maps links, IEMA/IDFPR lines, and the engine's proposal and
     conflicts.
   - Budget: at most 2 searches. The agent records with `rule_id: "AGENT"` and the
     `packet_id`.
   - Write `V2_RESOLVE_RUNBOOK.md` and tests.
   - Order of work: the 272 review proposals, then the 43 phone-only moves, 37 name
     corrections and 40 identity/scope rows, then the no-proposal buckets.
   - Every opened row makes room to publish one waiting removal (82).
6. **Pilot 100 v2-lane rows → Gate B** (≥70% resolved; ≥19/20 on the user's Maps spot check),
   then sweep.
7. **October 1** (free allotments reset):
   - 106 `details_ent_atmos` review lookups for the "review dates unknown" bucket;
   - Places for the 690 unchecked rows if v1 hasn't reached them;
   - `places-purge` for Places content older than 30 days (the first records date from
     2026-09-27, so they are due on 2026-10-27).
8. **P1 re-check** of v1 successor removals (§6).
9. **Accuracy audit** of 100 random v2 resolutions (≥95 correct), plus the hand-check
   comparison.

## 8. Verify (read-only)

```bash
cd /Users/suleman/dental-pe-census-work
git branch --show-current            # office-census-pilot-2026-09-24
pgrep -fl office_census_v2_probes || echo "nothing running"
python3 scrapers/office_census_v2_probes.py places-cost
wc -l data/office_census/staging/v2_probes/{targets,iema_profiles,browser,places,packets}.jsonl
python3 -m pytest -q scrapers/test_office_census_v2_rules.py scrapers/test_office_census_rapid.py scrapers/test_rapid_store.py
python3 scrapers/office_census_rapid.py pull && python3 scrapers/office_census_rapid.py status | head -14
```

Expected at the wrap:
- `targets` 1,974, `iema_profiles` 3,161, `browser` 916 lines (649 keys), `places` 2,599,
  `packets` 1,974;
- 62 tests pass;
- status: VALID 291, NOT_CURRENT_GP 772, IDENTITY_ONLY 647;
- spend $0.00.

## 9. Standing rules

- **Git and data writes:**
  - No commits or pushes unless the user asks.
  - No SQLite writes.
  - Never delete data.
  - Rapid-store writes are allowed only for calibrated, spot-checked v2 rules via `record`, as
    the user granted on 2026-09-27 ("I want the live app directory to be updated to reflect
    the things you have resolved").
- **Google data:** Places content is never committed. Only place IDs, Maps links and our own
  wording leave the gitignored cache. Run `places-purge` after 30 days.
- **Removal brake** (35% global, 50% per session, minimum 20): never bypassed, and never
  evaded by splitting sessions.
- **Cost:** stay inside the free allotments (`--cap 0`). Anything that would bill needs the
  user's explicit approval first.
- **Scope and units:** MA/Boston is parked. State every count as rows, with denominator and
  date. The building-packet lane and the Directory map task are other lanes.
- **Execution:** no background jobs or pollers; use foreground chunks of ~3 minutes.
