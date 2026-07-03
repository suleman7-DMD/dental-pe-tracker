# 📢 GLOBAL PRIORITIES CORRECTION — 2026-06-21

**Broadcast from Main session (Lane 1) per user coordination. For Gate Owner, QA, and Fleet B.**

---

Correction/update:
**Main AO session is NOT running reach=4 now. It is staged only.**

Current priorities:
- **Gate Owner:** finish taxonomy/manifest/validate-only.
- **QA:** review only new files or addendum questions from Gate Owner.
- **Fleet B:** run zero-corp sweep only if explicitly cleared; otherwise hold.
- **Main:** hold AO fan-out after reach≥5.

**We do not need more AO volume until the manifest shows what is actually ready, blocked, or duplicated.**

---

Context for the record:
- The wave-1 reset is **complete** (practice_locations & practices `ownership_tier` non-null = 0/0, LEDGER
  header-only, PROGRESS 0/4,439). Evidence gathering may continue without the old pollution.
- **Consolidation remains FROZEN** — no `ownership_tier`/LEDGER/PROGRESS writes, no
  `consolidate_census.py --allow-db-write` — until the Gate Owner finishes the canonical manifest +
  validate-only pass AND the user explicitly approves.
- Taxonomy correction in force: DSO tier is decided by MSO/management/platform/DSO structure, **not** PE alone;
  `pe_backed` is a separate flag; AO reach is signal, not proof; specialist networks → undetermined/exclude
  from GP. Dental Dreams / KOS = `branded_dso`, `pe_backed=false` (MSO/platform evidence stands).
- Main's staged-but-unlaunched reach=4 batch (14 clusters) and the corrected runner/tooling are in
  `scrapers/ao_network_evidence.js`; the corrected reach≥5 evidence is in
  `ao_network_evidence_reach5_20260621.json` + `..._qa.json`. Full record:
  `_taxonomy_correction_and_pause_20260621.md`.
