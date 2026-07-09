# job_hunt_verification edge-bucket QA — 2026-07-09

Codex blocker 4: manual QA of the three edge buckets in the 48-row
verification layer. Method: a 12-agent adversarial re-verification fleet
(one agent per `no_usable_website` row, each instructed to REFUTE the
no-website call via name/dentist/phone searches, domain guesses, and direct
fetches), plus manual review of the 4 `ownership_conflict` rows and the 3
rows with empty `evidence_urls`. All fixes applied to Supabase and captured
in `data/job_hunt_verification_seed.json`; review items live in
`practice_manual_corrections` (submitted_by `jhv-edge-qa-20260709`).

Post-QA tally (48 rows): roster_verified 29, no_usable_website 10,
ownership_conflict 5, call_required 2, hiring_page_found 2.

## Bucket 1 — the 12 no_usable_website calls

False "no website" calls are the most damaging failure for job-hunt use, so
every row was adversarially re-checked. **10 confirmed, 2 refuted.**

### Refuted (fixed in place)

| location_id | Practice | Finding | Action |
|---|---|---|---|
| 6e1da5847ac2a0a9 | Nicorata Dental (Steven J. Nicorata DDS PC, Palos Heights) | drnicorata.com is **live** (301 → www, HTTP 200, full content: two-doctor roster Steven + Gregory Nicorata, practice since 1986; companion Wix site nicoratadental.com identical). The original "dead — TLS handshake failure" call was a transient hosting issue that no longer reproduces. | Upgraded to `roster_verified`, website live, 2 doctors, ownership `consistent` (site matches the census P.C.). |
| 00b3e3fb7e2346a0 | Glen Kulig DDS (New Lenox) | Succession: Dr. Kulig retired after 43 years (Village of New Lenox tribute). **CZ Family Dentistry** (Dr. Christopher Zwiercan) answers his exact phone (815) 485-8188, shares the DentalPlans internal practice ID (-265618), staff bio references "following the lead of Dr. Kulig", relocated to 196 W Illinois Hwy. Live site czfamilydental.com. | Reclassified `ownership_conflict` (public practice contradicts census entity); relabel/merge review queued (`practice_name` correction). |

### Confirmed (recheck stamped into row notes)

| location_id | Practice | Recheck result |
|---|---|---|
| 1c48dae13a792395 | Scottsdale Dental Clinic | Domain still parked (HugeDomains); phone traces to a different practitioner (Dr. Curt Lang, dead domain). |
| 45e77125cf27a136 | Neil P. Parikh DDS PC | ofsmiles.com belongs to Olympia Fields Dental Associates (different practice); Dr. Parikh now at an FQHC. |
| 53ab4c6d83e74c00 | Nour Issa DMD PC | Directory listings only; Dr. Issa affiliated with Oak Brook Dental Group. |
| 793fd65d1d75b40b | DuPage Dental Care | Directory/aggregator listings only across all passes. |
| 8c957ece2c079f8a | Periocare | periocare.com dead — every page redirects to /cancelled.aspx. |
| 993fe6f53c17c40f | Lauren Ming DDS (Evanston) | Directories, LinkedIn, hospital staff bio only. |
| af3fbb749a26da40 | Tyron Hill DDS (Glen Ellyn) | 4 search passes + 2 NXDOMAIN domain guesses; practice real and active but directory-only presence. |
| be6e3a0642562fab | John Marchese DDS (Downers Grove) | Directory/aggregator listings only. |
| ef66b532aff030ca | David Drake DDS (Chicago) | No practice site (Facebook only). **Census contact data wrong** — see bucket 3 note; correction queued. |
| fec8a97f57d0fb87 | (fec8…) | All directories consistently show no website field. |

## Bucket 2 — the 4 ownership_conflict rows → review queue

Each conflict now has a queued item in `practice_manual_corrections`
(field_key `owner_doctor_or_group`, status `queued`):

1. **92610afa95d3bc8f — High Point Dentistry** (legal: Fortress Dental
   Corporation, Elgin). Site: Dr. Vu Kong "CEO & Owner" of a 3-location
   group (Elgin/Schaumburg/Chicago). Suggested: re-tier dentist_multi (T3)
   with a network id.
2. **9474fbbb19738f80 — Homewood-Flossmoor Dental Care** (legal: Bhakta
   Niyati DDS). Own careers page: "Elite Dental Partners LLC" (Chicago DSO,
   75+ practices). Suggested: stealth/branded-DSO re-tier review; roster
   stale vs census (call).
3. **ace31cb7f9d2910c — Olive Family Dental**. Census says
   `brand:dental_starz`, but the site names only Dr. Samra Hussain and
   Dental Starz's own site lists different doctors at a different address.
   Suggested: dispute the network link; call to confirm.
4. **dbbac88ffb73610f — Setty Dental Group**. Indeed/Becker's/Group
   Dentistry Now indicate Smile Partners USA (~124-office DSO) affiliation;
   direct site fetch 403-blocked. Suggested: re-tier candidate; phone
   re-verify.

Plus two data-correction items from bucket 1: Kulig succession
(`practice_name`) and Drake wrong phone+address (`general_note` — census
phone (312) 846-6752 belongs to Dentologie South Loop; the real practice is
at 739 W Belmont Ave, (773) 248-8813).

## Bucket 3 — the 3 rows with empty evidence_urls

| location_id | Resolution |
|---|---|
| 6e1da5847ac2a0a9 (Nicorata) | Fixed by the bucket-1 refutation — now carries 3 evidence URLs (live site, companion site, Yelp). |
| af3fbb749a26da40 (Tyron Hill) | Backfilled 6 directory URLs documenting the searched-and-found-nothing rationale (Yelp, Vitals, WebMD, ADA, Healthgrades, NPI profile). |
| 8bf73126e79a8366 (Prairie Walk / Oak Park) | Legitimately empty: the live site 403-blocks automated reads, so there is no citable fetched evidence; row is `call_required` with the 403 documented in notes. Left as-is. |

## Reproduce / verify

```bash
python3 -m scrapers.import_job_hunt_verification --verify   # live == seed
```

Queue inspection:

```sql
SELECT location_id, field_key, suggested_value, status
FROM practice_manual_corrections
WHERE submitted_by = 'jhv-edge-qa-20260709';
```

### Amendment 2026-07-09 (verification follow-up): why an anon REST check shows 0 rows

An external verification pass ran the query above through the Supabase REST API
with the **anon key** and saw 0 rows, flagging the six queued corrections as
possibly fictitious. Root cause: `practice_manual_corrections` has **row-level
security enabled with no anon policies** (see
`scrapers/migrate_practice_manual_corrections.py`), so the anon role reads an
empty set by design — the moderation queue is not public. The rows exist and
were re-verified 2026-07-09 through two privileged paths:

1. **Pooler (postgres role):** all 6 rows returned, `status='queued'`.
2. **REST with the app's `SUPABASE_SECRET_KEY`** (the key
   `createServerClient()` actually uses, present in Vercel env): all 6 rows
   returned. The app's insert path (`/api/practice-corrections`) uses this same
   key, so submissions from the live UI also bypass RLS correctly.

The 6 rows are additionally mirrored into the local SQLite twin table
(`data/dental_pe_tracker.db :: practice_manual_corrections`) for offline
inspection. To verify from the repo without any Supabase key:

```bash
sqlite3 data/dental_pe_tracker.db "SELECT location_id, field_key, status
  FROM practice_manual_corrections WHERE submitted_by='jhv-edge-qa-20260709';"
```
