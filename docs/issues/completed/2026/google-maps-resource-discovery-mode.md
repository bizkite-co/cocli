# Task: Extend Google Maps scraper for Resource Discovery mode

## Objective
Enhance the existing `google-maps` scraping command to specifically target and categorize public and non-commercial local resources (e.g., parks, libraries, bike trails).

## Requirements
- **Target Filtering**: Implement logic to prioritize non-commercial categories (e.g., `park`, `library`, `recreation_center`).
- **Nominal-Fee Detection**: Use LLM-based analysis of scraper descriptions to flag "nominal-fee" vs "subscription-based" entries.
- **Categorization**: Automatically map discovered entities into the `content-curation-strategy.md` categories.
- **Output**: Export results directly to sharded TOML/USV files optimized for Astro ingestion.

## Rationale
To fulfill the "Value-First" mission, we need to efficiently discover and categorize thousands of local resources across multiple municipalities. Stretching the current `google-maps` scraper ensures we reuse our existing anti-bot and residential worker infrastructure.

---
**Completed in commit:** `72acc66`
