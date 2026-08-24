---
id: "002"
title: CompanyName/CompanyAddress stripped legitimate apostrophes
models: [GoogleMapsProspect, Company, Person]
fields: [name, full_address, street_address]
pipeline_stage: "Model validation (CompanyName.validate(), CompanyAddress.validate())"
date_start: "2026-07-04"
date_end: "2026-08-23"
status: fixed
fix_commit: 92b37742
campaigns:
  turboship: cleaned
  roadmap: cleaned
---

# 002: CompanyName/CompanyAddress stripped legitimate apostrophes

- **Model(s):** `GoogleMapsProspect` (via `name`, `full_address`,
  `street_address`); also `Company` and `Person` (same `OptionalCompanyName`/
  `OptionalCompanyAddress` types, `cocli/models/companies/company.py`,
  `cocli/models/people/person.py`)
- **Field(s) affected:** `name`, `full_address`, `street_address`
- **Date range live:** 2026-07-04 (commit `94194943`, `CompanyName`/
  `CompanyAddress` introduced) → 2026-08-23 (fixed)
- **Pipeline stage / queue:** Pydantic model validation -
  `CompanyName.validate()` (`cocli/models/company_name.py`),
  `CompanyAddress.validate()` (`cocli/models/company_address.py`) - runs on
  every model construction, i.e. every fresh scrape, not a queue/compaction
  step.
- **Discovered:** 2026-08-23, directly from user pushback while reviewing
  incident 001's historical-cleanup scope: "I think we might have
  constrained some of the Pydantic models to not allow quotes on several
  fields... company names should not have quote characters at all."

## Mechanism

`CompanyName.validate()` and `CompanyAddress.validate()` both ran
`v.replace('"', '').replace("'", '')` - stripping *all* quote characters,
single and double, unconditionally. The intent was removing CSV-quoting
artifacts. The actual effect: any name or address containing a genuine
apostrophe (a normal, common feature of English business names - "John's
Flooring", "Lowe's", possessives generally) got silently corrupted on
every single scrape, turning "John's Flooring Inc." into "Johns Flooring
Inc." This ran on every fresh `GoogleMapsProspect` construction for 7 weeks
before being caught - it is not a compaction-time or historical-only issue
like incidents 001/003, it corrupts data at the point of creation.

## Evidence

Checked directly against the live checkpoint (16,777 rows, post-incident-001
fix): of 197 rows with a quote character in `name`, only **4** contained a
literal double-quote (all 4 confirmed as real corruption, e.g.
`"""# 1 Hardwood Flooring"""` - the same repeated-quote-wrapping pattern
from incident 001). The other **193** contained only single-quotes, and
every sampled case ("John's Flooring Inc.", "RJ's Flooring Installation,
LLC", "Bill's Property Maintenance LLC", "Lowe's Home Improvement",
"Buddy's Flooring America") was a legitimate possessive - real business
name content, not an artifact.

## Fix

Commit `92b37742`. Both validators now run `v.replace('"', '')` only -
double-quotes are still stripped unconditionally (zero legitimate uses
found anywhere in the sample), single-quotes/apostrophes are left
untouched entirely. Two existing tests
(`test_remove_outer_single_quotes`, `test_remove_mixed_quotes` in
`tests/test_company_name.py` and `tests/test_company_address.py`) asserted
the old apostrophe-stripping behavior and were updated to lock in the new
one; the doubled-double-quote and complex-legacy-data tests were unaffected
since double-quote stripping stayed global and unconditional.

## Recovery status

**Going forward: fully fixed.** New scrapes preserve apostrophes correctly.

**Historical damage: cleaned on turboship.** 966 of the checkpoint's 16,777
rows had a literal double-quote in a target field (name/address/website/
city/etc.) and were cleaned in place using the same double-quote-only rule,
verified against a spot-check ("John's Flooring Inc." confirmed unchanged
post-cleanup) before pushing to S3. Note this cleanup only *removes*
already-corrupted double-quote characters going forward from
2026-08-23 - it cannot restore an apostrophe that was already stripped by
this bug before that date (e.g. if "John's Flooring" was scraped fresh
during the bug window and written as "Johns Flooring" with no other record
of the original spelling, that specific loss is not recoverable from
within the pipeline - only re-scraping the same listing would fix it,
and there's no signal distinguishing "always had no apostrophe" from
"had one stripped").

**Roadmap: cleaned 2026-08-23** via the same `cocli index clean-quote-corruption`
command incident 001 promoted to a real tool - 1,450 of 31,570 rows (4.6%)
had double-quote corruption, cleaned with 0 remaining on a follow-up
dry-run. Same caveat as turboship applies: an apostrophe already stripped
by this bug before the fix landed is not recoverable from within the
pipeline.
