# REVIEW — True Independent Hardening / Hidden Consolidation Attack Plan
**Author:** Codex QA review · 2026-07-03  
**Audience:** Fable PM + analyst team  
**Status:** Recommendation, not yet implemented

## 0. Core correction

Fable's hidden-corporate escalation plan is directionally right, but the threat model is too narrow if the product goal is:

> Identify the practices that are truly single-location dentist owner-operators, and make every other ownership structure visible.

This means the app needs two separate concepts:

1. **Conventional DSO/PE control:** T4 stealth DSO + T5 branded DSO, with `pe_backed` as a cited flag.
2. **Not true solo-owner-operated:** anything that is not T1, including T2 single-location groups, T3 dentist-owned multi-location groups, T4/T5 DSO/PE, and T6 institutional.

Do not force the ADA 14.6% per-dentist DSO-affiliation figure to validate or bound the second concept. ADA's statistic is a conventional DSO-affiliation anchor. The user's app-specific question is broader: "is this a solo owner-operator shop, or not?"

## 1. Definitions to use in the app and merge gate

Keep the tiers, but change the headline grouping language:

| Tier | Meaning | Headline bucket |
|---|---|---|
| T1 `true_independent` | One dentist owner-operator, one location, current evidence of ownership/control | True solo owner-operated |
| T2 `single_loc_group` | One location, multiple dentists, dentist-owned/no MSO proven | Dentist-owned but not solo |
| T3 `dentist_multi` | Dentist-owned network, 2+ locations, no MSO/PE proven | Dentist-owned multi-location |
| T4 `stealth_dso` | Corporate/MSO control without consumer brand | DSO/corporate controlled |
| T5 `branded_dso` | DSO brand/locator/acquisition evidence | DSO/corporate controlled |
| T6 `institutional` | Hospital, school, public-health, HRSA, etc. | Institutional, not solo |
| `undetermined` / holds | Researched but unresolved, blocked, stale, closure/duplicate/scope issue | Unknown, do not count as true independent |

Recommended frontend labels:
- **True Solo Owner-Operated:** T1 only.
- **Dentist-Owned, Not Solo:** T2 + T3.
- **DSO / PE / Corporate Controlled:** T4 + T5.
- **Institutional:** T6.
- **Unresolved:** undetermined + holds + unreviewed.

If a top-line "not independent" number is shown, call it **Not Solo Owner-Operated**, not "ADA DSO-affiliated." It can include T2/T3 by the user's definition without confusing it with conventional DSO affiliation.

## 2. Finding from current artifacts

Current local DB has only the first write:
- 343 locations with `ownership_tier`.
- Live written T1/T2 is small: T1 32, T2 7.

Lane A result files are the real pre-merge risk surface:
- 185 result unit files inspected.
- 2,934 researched rows.
- T1 `true_independent`: 1,333.
- T2 `single_loc_group`: 804.
- T3 `dentist_multi`: 278.
- T4/T5: 83.
- Undetermined: 391.

For the 2,137 Lane A T1/T2 rows:
- 636 have only directory/social/registry-style evidence URLs under a conservative domain screen.
- 2 have no URL.
- Only 284 reasoning blocks mention AO / authorized-official style checks.
- Only 409 mention provider-count style checks.

This does **not** prove hallucination or bad work. It means T1/T2 currently have a weaker evidence bar than T4/T5. Before merge, T1/T2 need a deterministic hidden-consolidation screen and a stricter "positive proof of independence" rule.

## 3. Positive proof standard for T1

T1 should not mean "we found no corporate signal." T1 should mean:

1. **Current owner identity:** a named dentist owner is supported by a current source.
2. **Single-location proof:** same owner/practice/brand is not operating a second active location in the watched area or nearby.
3. **Treating-owner link:** the owner is plausibly practicing or directly operating the office, not merely an old seller still named in stale records.
4. **No control signal:** no DSO/MSO/corporate signal from site, privacy policy, careers, NPI AO, Data-Axle, SoS, UCC, job postings, phone/mail/EIN clusters, locator pages, or known DSO infrastructure.
5. **Currentness:** stale "served since 1995" copy is history, not proof of current ownership.

Minimum evidence for high-confidence T1:
- Own practice website or current official profile naming the owner dentist.
- Plus one independent corroborator: NPI org AO, state/business filing, BBB, IDFPR/license profile, local press, or durable practice bio.
- Plus negative network check: no second office, DSO locator, MSO privacy/careers, or shared structural cluster.

Rows supported only by directories should not be high-confidence T1. They can be `undetermined_control`, `medium`, or routed to escalation until corroborated.

## 4. Fix Fable's ladder by widening the target

Fable's six rungs should run on **T1, T2, and suspicious T3**, not just "T1/T2 actually corporate." It should detect three failure modes:

1. **False T1 -> T2:** multi-dentist single-site group, not solo owner-operated.
2. **False T1/T2 -> T3:** dentist-owned multi-location group.
3. **False T1/T2/T3 -> T4/T5:** corporate/MSO/PE controlled.

The existing `scrapers/detect_corporate_clusters.py` already implements much of Rung 1: AO, mailing, parent-TIN, EIN, Data-Axle EIN/legal/officer, institutional exclusions, and overbroad-cluster controls. Do not rebuild from scratch. Reuse and harden it into a location-centric `hidden_control_screen` that joins Lane A result rows to all NPIs for the location.

Important implementation detail:
- Rich AO/Data-Axle fields live mostly on `practices`, not `practice_locations`.
- The screen must bridge each `location_id` to `primary_npi`, `org_npi`, and every `provider_npis` entry.
- Use org NPIs for AO/mailing/legal control.
- Use individual provider NPIs for roster/surname/owner matching.
- Do not let missing AO on NPI-1 rows dilute the signal.

## 5. Recommended signal model

Hard-positive signals:
- Exact DSO locator at normalized street + ZIP.
- Practice site/privacy/careers says "supported by" or names an MSO.
- Known DSO/PE parent in Data-Axle, NPPES, SoS, UCC, or job posting.
- Non-dentist manager/member/officer tied to multiple practices or an MSO.
- Shared EIN/parent TIN with a confirmed T4/T5 member.

Network-positive signals:
- Same AO across multiple ZIPs.
- Same phone across multiple offices.
- Same mailing address or PO box across multiple practices.
- Same website analytics/GTM/privacy-policy hash across unrelated brands.
- Same owner dentist appears across multiple active locations.

Weak/stale signals:
- AO mismatch alone.
- Registered-agent service alone.
- Directory-only evidence.
- Old founder language with no current owner proof.
- Website exists but no ownership statement.
- NPI last-updated date older than a suspected sale/rebrand.

Proposed decision rule:
- Any hard-positive signal -> hold for T4/T5 verification.
- Two independent network-positive signals -> cannot remain T1/T2 without PM review.
- One weak signal -> lower confidence and sample.
- Directory-only T1/T2 -> not high-confidence; require corroboration before merge.
- Ambiguous after attack -> `undetermined_control`, not T1.

## 6. Analyst assignment upgrade

Fable's proposed studies are good but too small and recall-only. Upgrade them:

### Study A — Retrodiction with controls
Use:
- 25-40 confirmed local-name T4/T5 stealth/branded DSOs.
- 25 known strong T1 controls.
- 25 known T2 controls.
- 25 known T3 dentist-owned multi controls.

For each row, record S1-S12 and any added signals above. Report recall **and false-positive rate** by signal and by signal combination. The goal is not just "catch DSOs"; it is "catch DSOs without destroying true independents."

### Study B — T1 attack sample
Start with n=100 if usage allows; n=50 only as a pilot.

Stratify:
- 25 random high-confidence T1.
- 25 directory-only T1.
- 25 T1 with AO/mailing/DA/network oddities.
- 25 older-founder/stale-site/succession-risk T1.

Adversarially test Rungs 1-2 by hand. Each miss should be labeled:
- false T1 -> T2,
- false T1/T2 -> T3,
- false T1/T2/T3 -> T4/T5,
- stale/closed/transition,
- unresolved but suspicious.

Deliverable should include thresholds for the deterministic screen and examples that become regression fixtures.

## 7. Pre-merge gates for Lane A

Before any Lane A consolidation write:

1. Run hidden-control screen over all Lane A T1/T2/T3 rows.
2. Block high-confidence T1 for any row that is directory-only, stale-owner-only, or has 2+ structural signals.
3. Require flat-file verdict coverage for all T4/T5 claims, as already planned.
4. Add a T1/T2 audit separate from the DSO audit:
   - n=20 minimum per wave.
   - Force include directory-only rows and structural-signal rows.
   - The question is "is this truly solo owner-operated?" not merely "is this not DSO?"
5. Persist the signal vector and rationale to the DB, not just final tier. The future UI should show why a row is T1 and when that proof was last checked.

## 8. Frontend implication

The app should not present a single "corporate percent" that silently changes definitions.

Show a stacked ownership truth bar:
- True solo owner-operated.
- Dentist-owned but not solo.
- DSO/PE/corporate.
- Institutional.
- Researched unresolved.
- Unreviewed.

This lets the product answer the user's real question without pretending the number equals ADA's DSO-affiliation statistic.

## 9. Bottom line

Fable's plan is the right base, but it should be promoted from "hidden corporate escalation" to "true independent proof hardening."

The strict rule should be:

> T1 is a positive, current, corroborated ownership claim. It is not the absence of DSO evidence.

If that rule is enforced before Lane A merges, the app will be much closer to the user's actual product goal: a directory where every practice is either proven solo-owner-operated, proven not solo, or honestly unresolved.
