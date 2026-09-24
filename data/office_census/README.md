# Office census: pilot operations

One office is one distinct, currently operating, patient-facing dental operation
at a physical site offering routine general dentistry. Mixed GP/specialty and
community dental sites qualify. Provider NPIs, billing entities, street addresses,
domains and phone numbers are evidence signals, never office identities by themselves.

## Start a batch

```sh
python3 scrapers/office_census.py next-batch --zip 60602 --full-reconciliation
python3 scrapers/office_census.py inspect CANDIDATE_ID
```

Read the compact file in `worklists/batch_60602.json`; use `inspect` only for the
items being researched. The full source bundle stays in `candidates.jsonl`.
Default `next-batch` selects one ZIP, favoring least recently worked ZIPs and then
pilot/workload rank. It never permanently retires a ZIP. `--target-items` is a
soft ZIP selection budget, not a per-ZIP truncation. For dense ZIPs stop after
10-20 difficult items and checkpoint explicit unresolved cases and source passes.

## P1-P4

1. P1: source groups absent from the location table, clean leads first. Alternate
   phone/address matches are review hints, not automatic duplicates. Bad-address
   and non-dental source groups remain visible after the cleaner leads.
2. P2: suspicious current rows and previously excluded rows. Resolve suite/building
   identity, status and GP contradictions. A specialist flag is not an adjudication.
3. P3: independently search for offices absent from BOTH the directory and existing
   source universe. Do this in every pilot ZIP even if P2 has unresolved cases.
4. P4: ordinary existing rows are deferred, not newly verified. Existing evidence
   and dates remain visible. Research only for a new contradiction, a precision
   sample, stale-evidence refresh or a convenient check during discovery.

`--full-reconciliation` deliberately includes P4 for the first 60602 experiment.
It does not make universal individual reverification the default workload.
Zero new census confirmations does not mean zero historical evidence.

## What the source leads mean

The builder reads SQLite **read-only**, raw Data Axle CSVs (latest copy per IUSA),
NPPES primary records and existing DSO location records. It compares normalized
street+ZIP keys against ALL IL-watched location rows, including excluded rows.
An unmatched key produces a stable `src:<zip>:<hash>` research bundle.
The manifest contains current family breakdowns, alternate matches and flags.
These are candidate GROUPS, not missing offices. A group may contain several offices.

The street key strips suites. Therefore this procedure does not discover every
missing office inside an already represented building. Inspect `source_refs.records`
on P2 rows: full original addresses, suites, names, phones, source IDs/dates and
Data Axle files are retained. No common key, phone, domain or NPI proves a merge.
NPPES primary ingestion has already lost some address-line-two data; those suites
cannot be reconstructed from the DB. No secondary NPPES location feed is imported.
Do not run the old `dedup_practice_locations.py` builder.

## Historical evidence

`prior_evidence.historical_observations` references site checks, practice-intel
contact/status evidence, relevant manual corrections and locator location records.
Each has a stable content ID, original source ID/date, claim scope and full payload.
Missing dates remain missing. A locator `il_seed:` identifier is not a fetched web
page; follow its source before treating it as proof. Dossier URLs are now read from
`verification_urls`. Ownership-only reviews remain labeled context and do not
constitute imported office verification. No historical record automatically confirms.

Useful historical facts can support a NEW adjudication: append an observation
with the original date/URL and clearly state what the historical check established.
Do not substitute today's date for the old check. Recheck the relevant page when
the old evidence cannot establish current operation at the exact site.

## Evidence and decisions

Append JSON objects, one per line, to `research_ledger.jsonl`. Never edit prior
research; append a superseding decision, or `retract` an incorrect entry with a
reason. Every entry needs `entry_id`, `type`, `researcher`, `recorded_at`.

Observation example (illustrative only; do not append this fictitious office):

```json
{"entry_id":"pilot-example-contact","type":"observation","researcher":"session-name","recorded_at":"2026-09-24T15:00:00Z","candidate_id":"loc:EXISTING_ID","source_family":"office_website","claim":"exists_at_address","confidence":"high","observed_at":"2026-09-24","source_url":"https://example.com/contact","evidence":"The office's own contact page explicitly lists its public name and exact address, Suite 200."}
```

Allowed source families: office_website, phone_call, dso_locator,
google_business_profile, insurer_directory, hrsa_fqhc, idfpr_license, nppes,
data_axle, street_view, healthgrades_zocdoc_yelp, other_web.
Record negative/conflicting observations too. A phone call needs a dated account
of whom you reached and what they confirmed; no URL is required for a call.

Decisions need `candidate_id`, `terminal_status`, `confidence`, `decided_at`,
`basis_entry_ids` and explanatory `notes`. Confirmation additionally needs:

- `fields.office_name`, `fields.address`, `fields.suite_status` (verified suite,
  explicitly no suite, or why a distinct patient entrance resolves suite ambiguity).
- `assessment`: keys `identity`, `exists_at_address`, `current_operation`,
  `gp_scope`, `address_suite`, `contact`. Each contains `conclusion`, `rationale`,
  and `basis_entry_ids` citing observations of this same candidate.
- The first five conclusions must be `established`; contact can also be
  `unresolved` or `not_available`, with explanation.
- `contradictions_reviewed`: address competing evidence explicitly, or describe
  the checked bundle and absence of conflicts. Current-operation observations
  must be within 365 days; older confirmations return to review. This is a maximum
  validity window, not a guarantee that an office cannot close sooner.

An official location/service page may establish several claims when it explicitly
ties them to this office. Live hosting alone does not establish operation. Two
stale aggregators do not make a fact true. No source count or score auto-confirms;
the researcher is accountable for the claim-specific assessment.

Statuses: `OPERATING_GP_CONFIRMED`, `OPERATING_MIXED_GP_CONFIRMED`,
`OPERATING_SPECIALIST_ONLY`, `CLOSED`, `MOVED`, `DUPLICATE`,
`MERGED_RECORD_NEEDS_SPLIT`, `NONCLINICAL_OR_ADMINISTRATIVE`, `UNRESOLVED`.
Closure/move requires positive evidence, never directory absence. `MOVED` needs
`moved_to`; `DUPLICATE` needs an existing `duplicate_of` target. Add split children
with `add_candidate` entries (`ext:<zip>:<stable-slug>`, name, full address, ZIP,
discovered_via, source_url, optional suite/phone/site, `split_from` parent ID).
The parent stays open until children exist. Give each child its own adjudication.
Independently discovered offices use the same add-candidate format without a parent.

## Discovery and coverage

A `zip_sweep` entry records `zip`, `pass_type` (`current_rows`, `discovery`,
`recall_audit`), `completed_at`, `sources_searched`, `notes` (queries, geographic
limits, unavailable sources), and `findings` (candidate IDs or explicit no-result
details). An empty findings list is valid; an unexplained empty search is not.
Record only source families actually attempted. A recorded pass does not mean
that family is exhaustive. Candidate adjudication counts and discovery history
are separate. Neither is a permanent ZIP completion flag.

For each ZIP, first reconcile internal leads, then search broadly without limiting
the search to known names: general web/business listings, official practice and
multi-location locators, FQHC/community site lists, available payer directories.
Dense buildings need tenant/suite resolution. Record unavailable commercial/payer
sources as gaps. A later secondary-NPPES import should select dental providers
nationally before filtering EACH secondary site into the watched ZIP geography.

For 60602 freeze the initial roster, reconcile all candidate groups (including the
small P4 roster), and independently search for previously unknown offices. Report:
new GP offices recovered from existing sources; wholly external discoveries;
old rows rejected; duplicates; splits; closures/moves; unresolved cases; confirmed
count; provisional count separately; source coverage and limits. Do not invent a
single best-estimate total by adding unresolved groups that might overlap.

## Map and eventual directory

Stored/recoverable coordinates are not verified. Keep verified but ungeocoded
offices in the directory without a marker. After checking the patient-facing
address, use a geocoder and inspect the result against that site. Store lat/lon,
`geocode_precision` (entrance/rooftop/parcel/site), `geocode_source`, and
`geocode_checked_at` in decision fields. ZIP centroids are rejected. Suite identity
still needs evidence even when multiple offices share a legitimate building point.

This is a staging/adjudication layer. Promotion to the eventual canonical office
directory will use stable office IDs with source-candidate mappings; split children
become distinct offices, duplicates link to the survivor, and rejected records
remain retained with status/reason. The legacy directory stays unchanged during the
pilot. No permanent second directory or automatic promotion is introduced here.

## Checkpoint and acceptance

```sh
python3 scrapers/office_census.py check-ledger
python3 scrapers/office_census.py build
python3 -m pytest scrapers/test_office_census.py -q
python3 scrapers/office_census_publish.py
```

The builder refuses orphaned research instead of silently dropping it. If source
IDs disappear, inspect both identities, append correctly associated observations
and decisions, then retract obsolete entries with cross-references. No heuristic
relinking. Unchanged inputs yield identical candidate IDs/content. Source history
is preserved by committed build artifacts and append-only ledger research.

For isolated worktrees, set `OFFICE_CENSUS_INPUT_ROOT` to the original tracker repo;
inputs stay read-only and outputs stay in the worktree. Publish only after Python
tests, frontend tests/typecheck/build and ledger validation pass. Publisher changes
only its three staging tables in one transaction. `--verify` compares all published
candidate and coverage fields, not just counts. Commit generated files with code.

Pilot acceptance: every processed item has an explicit decision or a recorded
unresolved next action; every confirmation supports all required claims; every
split/duplicate has explicit relationships; no fake map positions; all attempted
discovery sources and constraints are recorded. A pilot is an experiment, not
proof of completeness across Chicagoland.

Before promoting the whole directory, independently sample the proposed active
offices for precision, stratified by urban density/source/risk. Target >=98%
identity/existence/GP correctness and report a binomial interval and actual errors.
For recall, reserve a stratified set of ZIPs for blind independent discovery from
source families not used by the first reviewer, then match the independently
adjudicated list back to the census. Report overlap, newly discovered offices,
per-stratum uncertainty and source dependence; choose sample size from pilot error
rates. Do not claim 100% completeness, a numeric recall bound from a convenience
sample, or recall from candidate-review percentages. Expand discovery where the
held-out search still finds material omissions.
