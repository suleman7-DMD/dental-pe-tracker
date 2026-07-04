# T1/T2 Source-Check Notes — 2026-07-04

Supplement to `audit_t1_t2_source_check_20260704.json` after the late-Opus rerun.

The bounded URL source check over the final 104-row audit sample found 3 rows with corporate-language
regex hits. Manual review outcome:

- `31abbd4a8d8300c9` Comfort Dental LLC — already held by the T1/T2 audit. The source page hit
  `private equity`; no extra action needed because the row is already excluded.
- `20c2ed45dd8cf50a` Inverness Dental Care — already held by the T1/T2 audit. The source page
  hit `Supported by`; no extra action needed because the row is already excluded.
- `4ca83acbcd91a330` Oak Dental Partners — already held by the T1/T2 audit. The source page hit
  `DSO`; no extra action needed because the row is already excluded.
Conclusion: all corporate-language source-check hits were already excluded by the audit; no
additional source-check holds beyond the 50 rows already moved to triage by
`scrapers/audit_lane_a_t1_t2.py`.
