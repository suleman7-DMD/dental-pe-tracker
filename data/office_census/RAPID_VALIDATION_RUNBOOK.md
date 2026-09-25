# Office Census — Rapid Validation Runbook (Track A)

You are checking **existing directory rows** against the live web, one row at a time,
as fast as the evidence allows. Each row gets one decision, recorded immediately. Rows are
research items, not "offices" or "practices"; say "rows" in any summary.

This is not ownership research, not discovery, and not building reconciliation. Downtown ZIPs
and merged-building rows are already routed to a separate building lane and never appear here.
You record each decision with the `record` command. It is saved in the shared store (Supabase)
and **goes live on the Directory page the moment you record it**. Several sessions, local or
Claude Code cloud, can work the queue at once; `next` never hands two sessions the same row.

**Your decisions go live.** On the public Directory page (list and map):
- `NOT_CURRENT_GP` **removes the row**. It is shown with your evidence under "Show removed".
- `VALID_CORRECTED` **replaces** the displayed name, phone, website and address with your
  `observed` values.
- Every other decision adds a status line and leaves the row in place.

Be exactly as careful as that deserves.

## 0. Session start (once)

Run every command from the repository root (the directory holding `scrapers/`), exactly as
written. The shell starts each command there. If you ever `cd` elsewhere, put `cd` back to the
root in front of the next command.

```sh
test -f data/office_census/rapid/queue.jsonl && git branch --show-current
python3 scrapers/office_census_rapid.py status
python3 scrapers/office_census_rapid.py tag
```

- The first line must print the branch name (`office-census-pilot-2026-09-24`). If it prints
  nothing, this checkout doesn't have the rapid queue: stop and tell the user.
- `status` must end with a `shared store:` line. If it prints `STORE NOT CONFIGURED` or
  `STORE ERROR`, stop and report it; don't work around it (a local-only run would be lost).
- `tag` prints your session tag, e.g. `rv-0925-1830-4f2a`. Use it in every `next`/`record`/
  `release` call this session. In the commands below it is shown as `S`. Your search budget is
  counted per tag, so keep the same one all session.

Then:
1. Load the web tools: ToolSearch `select:WebSearch,WebFetch`.
2. Work inline. Do not spawn subagents.

## 1. The loop

```sh
python3 scrapers/office_census_rapid.py next --n 10 --session S
```

For each card, in order: **search → decide → record**. Record each row right after you
decide it; then take the next card. When the batch is done, call `next` again. Keep going
until `next` says the queue is empty or the user stops you. Don't write progress reports
between batches. Everything you record is already saved.

**Search budget.** A session gets about 200 web searches in total.
- `next` shows how many you have used. After 170, it hands out only rows you already claimed,
  then prints `SEARCH BUDGET REACHED`.
- When you see that, or when WebSearch itself refuses (a limit or quota error), stop and go
  straight to §7.
- Don't stop just because the conversation is long. Context is compacted automatically, and
  your work is saved row by row.

**Removal brake.** If `record` says `HELD by the removal brake` (or `next` prints
`REMOVAL BRAKE`), too many of your rows were removals: the check is saved but kept off the page
for a human to review. Finish the card you are on, then go to §7. Don't try to get around it.

**Store errors.** If `record` prints `NOT SAVED`, resend the identical command once (the store
ignores a record it already has). If `next` or `record` fails twice in a row, go to §7 and
report the error line.

## 2. Per-row procedure

**Budget per row: at most 3 searches and 2 page fetches. Then decide.** Speed matters. Most
rows should take one search.

1. **Read the card.**
   - `⚠` lines are tripwires: prior closure, retirement, death or sale notes; a dead website;
     a residential-looking address; a non-Illinois phone.
   - `public name` (when shown) is what an earlier site check found the office calls itself.
2. **Run `q1`** with WebSearch, verbatim.
   - Judge mainly from result **titles and URLs**. The tool's prose summary sometimes blends
     different businesses together.
   - Titles like `NAME - CLOSED - … - Yelp` and real-estate listings are strong signals.
3. **The office's own website in the results showing this address usually decides the row.**
   Otherwise run `q2`, then `q3`.
4. **Fetch a page only when a decisive fact isn't visible in the results.** Decisive facts are
   the address, suite, phone or a closure. Usually fetch the practice's contact page.
   - Use WebFetch, or `curl -sL --max-time 15 URL | head -c 20000` via Bash. Fetches don't use
     up the search budget; searches do.
   - Yelp and Google can't be fetched; use the result titles instead.
   - A fetch that fails on DNS means the site is dead. Tag it `website_dead`.
5. **When the budget is spent,** choose IDENTITY_ONLY, NO_WEB_EVIDENCE or ESCALATE and move on.
   Unresolved rows get a deeper lane later. Never turn a row into a research project.
6. **Before recording a new address or phone,** check whether another row already has it:
   `python3 scrapers/office_census_rapid.py lookup --address "135 N Arlington Heights Rd" --zip 60089`
   (or `--phone`, or `--name "Creekside" --zip 60089`).
   - Same office already listed as another row → `NOT_CURRENT_GP` with reason `duplicate` and
     `duplicate_of`.
   - A different office in the same building is fine: keep `VALID_CORRECTED` with the suite.
     `record` stores the collision automatically.

## 3. Decisions

**VALID / VALID_CORRECTED require all four:**

1. A dental office at this house number and street (and suite, if known), matching the row by
   name, phone or dentist.
2. **A current signal.** The evidence `kind` must be one of:
   - `first_party_site`: the office's own website lists this address;
   - `dso_locator`: the operator's own location page;
   - `maps_panel`: only if you actually saw a Google Maps business panel (normally you won't).
3. General dentistry offered here: `gp_scope` is `gp` or `mixed`.
4. No unresolved tripwire.

**Listings never prove an office is open.** Healthgrades, WebMD, Vitals, Yellow Pages, BBB,
CareCredit, Zocdoc, Facebook, patientconnect365 and dentistsranked stay up for years after an
office closes; they are kind `listing`.

NPI mirror sites (npiprofile, npino, npidb, doctorsnetwork, dentalplans, dentistsok,
dr-leonardo, opennpi, hipaaspace) are kind `registry`. They copy the registry our directory
came from, so they prove almost nothing.

**Why these rules exist (pilot traps):**
- BMC Family Dentistry had BBB, CareCredit and Yelp listings at its address. A real-estate
  listing showed the office sold in 2024, and its website does not resolve.
- Krafcisin & Assoc was listed as "accepting new patients". The owner died in 2026, and the
  practice closed in 2023.

| Decision | Use when | Must include |
|---|---|---|
| `VALID` | All four conditions; the app's name, address, phone and website are substantially right | current evidence; `gp_scope` |
| `VALID_CORRECTED` | All four conditions; at least one field is wrong or missing | current evidence; `gp_scope`; `observed` with **only** the differing fields |
| `IDENTITY_ONLY` | Listings or registry pages show this dental office at this address, but there is no current signal (typical for solo offices with no website) | ≥1 evidence item |
| `NOT_CURRENT_GP` | Positive evidence the row is not a current GP office here | `reason`; `ties_by`; ≥1 evidence item **with a quote** |
| `IDENTITY_PROBLEM` | The row mixes offices (one business's name, another's phone), or several dental businesses share the suite or phone and you can't tell which one the row is | `note` |
| `NO_WEB_EVIDENCE` | ≥2 searches found nothing credible about a dental office at this address, name or phone. This never means "closed" | `note` saying what you tried |
| `ESCALATE` | Real conflict you can't settle within budget | `reason`, `note` |

**NOT_CURRENT_GP reasons:**
- `closed`
- `moved`: gone from this address, to outside the ZIP or into another row's office
- `home_or_registration`: a residence or registration-only address
- `specialist_only`: only specialty care at this address
- `nonclinical`
- `duplicate`: needs `duplicate_of`

An office that **moved within the ZIP** to an address that isn't another row's office is
`VALID_CORRECTED` with `observed.address` (and `suite`).

**`ties_by` (required on `NOT_CURRENT_GP`):** which facts tie the evidence to *this* row. It is
a list from `name`, `phone`, `dentist`, `website`, `address`.
- `closed`, `moved` and `duplicate` need at least one tie beyond `address`.
- A "CLOSED" listing for a *different* business at the same address says nothing about this
  row. That is `IDENTITY_PROBLEM` or `ESCALATE`, not a closure.
- Example: the row is `EXCELLENT DENTISTRY LTD`, and its dentist on the card is Victoria Eyber.
  The listing reads "DENTAL OFFICE OF VICTORIA EYBER - CLOSED". Record `ties_by: ["dentist"]`.

**ESCALATE reasons:** `conflict`, `gp_scope`, `operating_status`, `other`.

**Tripwires (any one blocks VALID unless current first-party evidence settles it):**
- a real-estate listing for this address (Zillow, Redfin, homes.com, LoopNet, Crexi,
  @properties, cityfeet);
- "CLOSED" or "Permanently closed" in any title;
- the website on file is dead, parked, or belongs to another business;
- a `⚠ prior note` on the card;
- a different dental business in the same suite, or the row's phone belongs to another business;
- a specialty-only occupant.

A residential listing plus a dentist who practices elsewhere is `NOT_CURRENT_GP` with reason
`home_or_registration`.

## 4. Recording

Send one JSON object per call, right after deciding:

```sh
python3 scrapers/office_census_rapid.py record --session S <<'EOF'
{"candidate_id": "loc:2107d40f445f0f18", "decision": "VALID_CORRECTED", "gp_scope": "gp",
 "evidence": [{"kind": "first_party_site", "url": "https://www.krouthdental.com/",
               "quote": "1016 Douglas Rd, Unit A, Oswego, IL 60543 (630) 554-5244"}],
 "observed": {"name": "Krouth Dental"},
 "searches": 1, "fetches": 0}
EOF
```

More shapes:

```json
{"candidate_id": "loc:…", "decision": "VALID", "gp_scope": "gp",
 "evidence": [{"kind": "first_party_site", "url": "https://…/contact"}], "searches": 1, "fetches": 0}

{"candidate_id": "loc:…", "decision": "IDENTITY_ONLY", "gp_scope": "gp",
 "evidence": [{"kind": "listing", "url": "https://www.yelp.com/biz/…", "quote": "PATEL N P DDS - Updated October 2025 - 3426 W Armitage Ave"}],
 "observed": {"name": "Naran P. Patel, DDS"}, "note": "Listings only; phone matches.", "searches": 1, "fetches": 0}

{"candidate_id": "loc:…", "decision": "NOT_CURRENT_GP", "reason": "closed", "gp_scope": "gp", "ties_by": ["name"],
 "evidence": [{"kind": "listing", "url": "https://www.yelp.com/biz/dental-corner-chicago", "quote": "DENTAL CORNER - CLOSED - Updated June 2026 - 4857 N Western Ave"},
              {"kind": "real_estate", "url": "https://www.loopnet.com/Listing/…", "quote": "4857 N Western Ave - Office/Medical for Lease"}],
 "signals": ["real_estate_listing"], "searches": 1, "fetches": 0}

{"candidate_id": "loc:…", "decision": "NOT_CURRENT_GP", "reason": "home_or_registration", "gp_scope": "unknown", "ties_by": ["dentist", "address"],
 "evidence": [{"kind": "real_estate", "url": "https://www.redfin.com/…", "quote": "1564 Wind Energy Pass, Batavia, IL 60510 - 3 beds/2.5 baths"}],
 "signals": ["home_address"], "note": "Dentist practices elsewhere (Healthgrades).", "searches": 2, "fetches": 0}
```

Field rules:

- `observed`: include only fields that differ from the app or are newly found. On
  `VALID_CORRECTED` these values are shown publicly, so take them from the office's own site or
  its operator's locator, never from a listing.
  - `name`: the name the office uses publicly.
  - `address`: street only, e.g. `"135 N Arlington Heights Rd"` (no suite, city or ZIP).
  - `suite`: separate, e.g. `"185"`.
  - `phone`: `"(847) 634-4773"`.
  - `website`: the homepage URL.
  - `zip`: only if it differs.
  - Legal-to-public name changes count as corrections (`ERIKA L KROUTH DDS PC` → `Krouth Dental`).
- `evidence`: at most 4 items. Kinds: `first_party_site`, `dso_locator`, `maps_panel`,
  `iema_registry`, `listing`, `registry`, `real_estate`, `news_or_obituary`, `other`.
  - `quote` is at most 240 characters, copied from the page or title that proves the key fact.
  - One quote for the decisive fact is enough.
- `searches` / `fetches`: honest counts. They feed throughput stats.
- `record` answers `OK … · live on the Directory page` for each saved row.
- If `record` prints `REJECTED`, fix exactly what it says and resend. Don't argue with the
  validator.
- To change an earlier decision, resend it with `"supersede": true`. Only do this when you
  made an error.

## 5. Keep the incidental findings

Interesting facts you run into are valuable: sales, deaths, retirements, successor practices,
renames. Capture them cheaply.

- **`note`**: one line, only when something is non-obvious (why you decided, what's odd).
  Skip it for clean VALID rows.
- **`signals`** (tags, any number):
  - Ownership changes: `practice_sold`, `owner_deceased`, `owner_retired`,
    `successor_practice` (a different practice now at the address).
  - Name and branding: `rebranded` (name changed), `dso_or_group_branded`,
    `multi_location_practice`.
  - The building: `other_offices_in_building`, `real_estate_listing`, `home_address`.
  - Contact details: `website_dead`, `website_wrong_business`, `phone_belongs_elsewhere`.
  - `hiring_seen`: saw a hiring or careers page. Note it; don't go looking.
- **`leads`**: other dental offices you *happened to see* at this address that aren't this
  row, as `[{"name": "APG Dentistry", "suite": "204", "url": "https://…"}]`. Don't search for
  them.

Don't research ownership, and don't browse beyond the budget for any of this.

## 6. Hard rules

- Your only write is `record` (plus `next`/`release`, which claim and hand back rows). Never
  write SQLite, `practice_locations`, ownership tiers, `research_ledger.jsonl`, or Supabase
  directly, and never run `directory_web_checks_publish.py` (maintenance only).
- Never delete anything.
- Don't commit or push; the shared store is the record.
- Boston/MA is out of scope (the queue is Illinois-only).
- If a tool call is denied, adjust; don't retry it verbatim.

## 7. Ending a session

End the session when any of these happens:
- `next` says the queue is empty;
- `next` prints `SEARCH BUDGET REACHED`;
- WebSearch refuses with a limit error;
- the user stops you.

Record any row you have already decided, then run:

```sh
python3 scrapers/office_census_rapid.py release --session S
python3 scrapers/office_census_rapid.py status
```

- `release` hands your unrecorded claimed rows back to the queue. Without it they stay
  locked for 4 hours.
- Your rows are already live; there is nothing to publish or commit.

Then reply in at most 5 lines:
- rows this session;
- the decision mix;
- notable signals (sales, deaths, closures);
- held removals or store errors, if any;
- anything that slowed you down or broke.

**After an automatic context compaction:** re-read sections 2–5 of this runbook, keep your
session tag if you still know it, and continue the loop.
