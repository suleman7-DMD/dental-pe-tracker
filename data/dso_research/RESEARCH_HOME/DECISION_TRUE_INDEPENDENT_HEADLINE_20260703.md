# DECISION — "True Independent" Definition + Headline Buckets (USER-RATIFIED)
**Author:** Fable (PM) · 2026-07-03 · Status: BINDING for merge, consolidation, and UI Phase 0
**Source:** User message 2026-07-03 (relayed Codex convo) + Codex REVIEW_TRUE_INDEPENDENT_HARDENING_20260703.md §0–§1, which the user has now effectively ratified.

## 1. The user's definition (verbatim intent, cleaned up)
The app's core question is: **is this practice a single solo owner-operator shop, or not?**
Everything that is NOT a true solo owner-operator counts toward the app's broad
"consolidated / not-true-independent" concept — including:
- DSO-owned (branded or stealth), PE-backed, MSO-controlled → T4/T5.
- A dentist-owned group of 2+ locations (owner may be a dentist) → T3. Per the user:
  "if they actually have 2 locations then that = consolidated = not true independent."
- A single-location shop where the working dentist is an ASSOCIATE and the owner is a
  different dentist who owns 2+ practices → that location belongs to a T3 network.
- Institutional (hospital/school/public health) → T6.
- Multi-dentist single-location dentist-owned groups → T2. NOT solo, therefore not T1.
  (The user's strict test is "simply a single solo owner operator vs what's not" — T2
  fails the "solo" half even though it's dentist-owned.)

**PM ruling on the T2/absentee edge:** T1 = one dentist who BOTH owns AND operates one
location. A single-location practice owned by a non-practicing/absentee dentist is not
T1 (fails owner-OPERATOR), even if the owner owns nothing else — route to T2/undetermined
per evidence. This matches the §6h positive-proof standard already binding.

## 2. Two concepts, never conflated (ratified from Codex REVIEW §0)
1. **Conventional DSO/PE control** = T4 + T5 (+ pe_backed flag). This is the ONLY concept
   comparable to the ADA 14.6% per-dentist DSO-affiliation anchor.
2. **Not true solo owner-operated** = everything not T1 (T2+T3+T4+T5+T6). This is the
   user's app-defining broad concept.

## 3. Headline buckets for the frontend (feeds UI Phase 0 / distillation plan P1)
| Bucket label (user-facing) | Tiers |
|---|---|
| True Solo Owner-Operated | T1 |
| Dentist-Owned, Not Solo | T2 + T3 |
| DSO / PE / Corporate Controlled | T4 + T5 |
| Institutional | T6 |
| Unresolved | undetermined + holds + unreviewed |

**Labeling law:** the broad top-line number is called **"Not Solo Owner-Operated %"** —
NEVER "DSO-affiliated %". The user's internal shorthand ("T3 = dso affiliated") is a
mental model, not a publishable label: putting a dentist-owned two-office group under a
"DSO" label on the live app would be factually attackable and would corrupt the ADA
comparison. The stacked ownership truth bar (REVIEW §8) renders all five buckets so both
concepts are visible without conflation.

## 4. Numeric consequence (kills the long-standing 14.6% frustration)
The user has been bothered that "my data hunt routinely gives numbers lower than ADA's
14.6%." Under the ratified definition this inverts:
- Lane A researched rows so far: T1 ≈ 1,333 of ~2,498 classified → **Not-Solo ≈ 47–55%**,
  FAR ABOVE 14.6%. The broad number was never supposed to match ADA.
- The conventional T4/T5 number sits BELOW the ADA anchor for structural reasons:
  per-LOCATION vs ADA's per-DENTIST unit, plus hidden control (the escalation ladder
  shrinks this gap; it never claims to close it).
**Guard:** never validate or bound the broad Not-Solo number against ADA 14.6%; pair the
ADA anchor only with the T4/T5-per-dentist presentation (existing band discipline stands).
All Lane A percentages are pre-adjudication (§6h screen: 236 block_before_merge pending)
— recompute after merge before quoting anywhere.

## 5. Division of labor (user directive 2026-07-03)
- **Codex owns:** deal-flow scrapers (GDN/Becker's/PESP audit + backfill), frontend/UI
  work incl. deals.ts changes and any "run scrapers" button, Data-Axle re-download
  workflow refresh.
- **Fable owns:** ownership census (fleet, adjudication, merge→consolidate→sync chain),
  true-independent hardening, escalation ladder refinement, PM review of everything.
- **Coordination rule:** no full `sync_to_supabase.py` run, no `refresh.sh`, and no
  practices-table sync may execute WHILE Fable's merge→consolidate→sync chain is running
  (race risk). Deals-table syncs are an independent axis and safe anytime. Census columns
  survive full practices sync (ORM-mapped since 2026-07-02) but mid-chain concurrency is
  still prohibited.

## 6. New ladder signal candidates (for the escalation-refinement session; not yet in S1–S12)
- **S13 — DOL Form 5500 plan-sponsor names (EFAST, free):** a "solo" practice whose
  employee 401(k)/benefits plan is sponsored by an MSO/DSO entity is near-conclusive
  hidden control. High precision, scriptable, nobody's using it.
- **S14 — IL HFS Medicaid credentialing/billing-group linkage:** billing/payee group NPI
  differing from the practice org NPI exposes control networks (n.b. Dentagraphics cites
  Medicaid.gov as its source — same vein).
- **S15 — Google Business Profile review-response signatures:** identical corporate
  response accounts/signature blocks across "unrelated" practices = shared ops layer.
  Weak-to-network-grade; scriptable.

## 7. What did NOT change
§6h gates, hold protocol, two-axis separation (detector floor 268/1,152/4,801 untouched),
fail-closed rules, evidence-URL requirements, MA parked, merge-chain sequence — all stand
exactly as written in MASTER_RESUME_LANE_A_FLEET_20260702.md.
