# PLAN — Hidden-Corporate Escalation Ladder (hunt false "true independent" calls)
**Author:** Fable (PM) · 2026-07-03 · Status: DRAFT for refinement with user + analyst after usage reset

## 0. Objective and threat model

Find T1/T2 ("true independent" / "single-location group") census rows that are actually
corporate-controlled. Illinois's Dental Practice Act forces every DSO to hide by design:
the clinical entity is ALWAYS a dentist-owned PC, controlled through a Management Services
Agreement (MSA). The worst case is a quiet acquisition: DSO buys a solo practice, keeps the
seller's website and branding, seller stays on as associate and often remains the NPI
Authorized Official (AO). Public-web research alone cannot see that transaction.

**Why "AO ≠ practicing dentist" is a strong signal but NOT foolproof (user's question):**
1. **Seller stays as AO.** NPPES only requires updates when the info changes; an acquired
   PC's NPI record routinely stays frozen with the selling dentist as AO for years.
2. **AO is often an office manager or spouse at genuinely independent shops** → false
   positives if used alone.
3. **MSA structure means the dentist IS the legal owner** — the corporate control never
   appears on the NPI record or Data-Axle legal-name fields at all.
4. **Data-Axle staleness/junk** — we already purged 179 synthetic DA rows and demoted 13
   false-corporates caused by the `parent_iusa=000000000` placeholder (2026-06-12). DA
   fields are corroborating, never sufficient.
So AO-mismatch is **Rung 1's cheapest filter**, not a verdict. Verdicts come from stacked
signals + fail-closed adversarial verification.

## 1. The ladder (ordered by yield ÷ cost)

### Rung 1 — In-hand data sweep (free, local, scriptable TODAY)
Sources already in SQLite: NPPES (incl. Phase-A ownership cols: AO name/title, mailing
address, subpart, parent org), Data-Axle (`da_legal_name`, `parent_company`, EIN, IUSA
linkage, franchise fields), phones, addresses.
Signals per T1/T2 row:
- **S1 AO-mismatch:** AO last name ∉ {practice-name dentist, any provider NPI-1 at address};
  weight ↑ if AO title is corporate (CEO/CFO/Manager/Member) or AO appears as AO on 2+
  other practices in different ZIPs (shared-AO clustering = mini-network fingerprint).
- **S2 EIN/parent clustering:** DA EIN or parent_company shared across 2+ ZIPs, esp. with an
  already-confirmed T4/T5 member (this rule already promoted 27 in Phase-4).
- **S3 Mailing-address divergence:** NPPES mailing address ≠ practice address AND matches a
  known MSO/corporate address or a shared PO box used by 3+ practices.
- **S4 Phone clustering:** same phone across ZIPs (existing detector logic).
- **S5 DA legal-name mismatch:** legal name is an unrelated LLC (not Dr-name PC) — weak alone.
Output: `_hidden_corp_suspects_rung1.json` with per-row signal vector + composite score.
Build: one script, ~half a day. Cost: $0.

### Rung 2 — IL Secretary of State + IDFPR (the highest-yield NEW layer)
ilsos.gov corp/LLC search + IDFPR license lookup. For each suspect (and eventually all T1/T2):
- **S6 Registered agent fingerprint:** CT Corporation / Cogency / Registered Agents Inc /
  Illinois Corporation Service = corporate-stack fingerprint. Solo dentists are almost
  always their own agent or use a local attorney.
- **S7 Non-dentist managers/members** on the LLC (cross-check names against IDFPR licenses).
- **S8 Shared agent/manager across multiple "independent" practices** → hidden network.
- **S9 Entity-name churn:** amendments/re-registrations near a suspected sale date.
Access note: SoS search is form-based; scrape politely or use agents with rate limits.
Build: scraper + agent hybrid, 1–2 days. Cost: ~$0 + agent tokens for lookups.

### Rung 3 — Web-infrastructure fingerprints (scriptable)
- **S10 Shared platform:** same site template/hosting/booking system (Heartland-supported
  practices reuse platforms), shared GTM/GA container IDs, identical privacy-policy text
  hashes across "unrelated" practices, WHOIS registrant orgs.
Build: fetch + hash pipeline over T1/T2 practice URLs we already collected. ~1 day.

### Rung 4 — Employment surface (agent research)
- **S11 Job-post employer names:** Indeed/Glassdoor/LinkedIn postings at the practice
  address listing the real employer ("a supported practice of…"). HR leaks what marketing
  hides. Agent-driven; reuse Lane A unit machinery.

### Rung 5 — UCC-1 filings (IL SoS UCC search)
- **S12 Secured-party names:** equipment/AR liens naming an MSO, DSO, or PE lender against
  the practice entity. Very high precision when present; sparse coverage.

### Rung 6 — Adversarial deep-dive + re-tier (existing machinery)
Rows with **2+ independent signals** from Rungs 1–5 → Opus verification units (same
CONFIRM/REFUTE/DOWNGRADE/INSUFFICIENT protocol, same evidence gate: real http(s) URLs).
Confirmed → T1→T4 correction via consolidate_census with full evidence; unresolved →
`undetermined`, NEVER left as T1 once 2+ signals stand unrebutted (fail-closed applies in
both directions).

## 2. Hard gates (unchanged)
Two-axis separation (detector floor 268/1,152/4,801 untouched); no auto-flips — every
re-tier passes the evidence gate + PM review; ADA band presentation stays (this work
shrinks the unmeasured gap, it never lets us claim "the true rate"); MA parked.

## 3. ANALYST ASSIGNMENT (research the cracks, propose the fix)
Deliverable: a proposal doc back to Fable for refinement. Two studies:
**A. Retrodiction test (known-answer):** take 25–40 confirmed T4/T5 practices from Lane A
whose acquisition kept local branding (Elite/GLDP/Imagen/Heartland-supported finds).
Pretend we didn't know; record which signals S1–S12 fire. This measures each rung's
RECALL on real hidden-corporates and finds the minimal signal set that catches ≥90%.
**B. Attack the T1 bucket:** stratified random n=50 from the 1,326 T1 rows (oversample:
recently-established entities, practices with AO mismatch, practices whose site is a
template/stock build). Adversarially attack each with Rungs 1–2 by hand. Report the
observed false-negative rate with examples + the cheapest rung combination that would
have caught each miss. Then PROPOSE: which rungs to operationalize first, thresholds for
the composite score, and the re-tier workflow. Fable reviews, refines, and schedules.

## 4. Sequencing after usage reset
1) Resume fleet (33 units) + verdict harvest + merge chain (separate, already planned).
2) Rung 1 script over merged T1/T2 set → suspect queue.
3) Analyst studies A+B in parallel (they're manual/sampled).
4) Refine plan with user → build Rung 2 scraper → Rung 6 verification waves.
