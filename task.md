# Task: Fix `cocli lead-scrape` for Zero-Row CSVs and Improve Scraper Robustness

## Goal
The primary goal is to fix the `cocli lead-scrape` command, which is currently producing CSV files with zero rows of actual business data. This involves improving the robustness of the Google Maps scraper by moving away from reliance on obfuscated HTML class names and adopting a more resilient parsing strategy, primarily using `innerText` and generic HTML attributes. The scraping logic will also be refactored into a more modular structure.

## Achievements So Far

1.  **Corrected `scrape_google_maps` call stack**: Identified and fixed the issue where `cocli/commands/lead_scrape.py` was incorrectly calling the `scrape_google_maps` Typer command instead of the underlying function in `cocli/scrapers/google_maps.py`.
2.  **Improved Error Handling**:
    *   Modified `cocli/scrapers/google_maps.py` to return `None` on scraping errors.
    *   Adjusted `cocli/commands/lead_scrape.py` to handle this `None` return gracefully.
    *   Updated error message redirection to `stderr` in both `cocli/commands/scrape.py` and `cocli/commands/lead_scrape.py` for better testability and user feedback.
3.  **Enhanced Test Coverage**:
    *   Created a new test file `tests/test_lead_scrape.py` to specifically test the `lead-scrape` command.
    *   Implemented tests for successful execution, cleanup functionality, and various error scenarios.
    *   Updated test mocks and assertions to align with the corrected function call signatures.
4.  **Refactored Scraping Logic**:
    *   Created a new module `cocli/scrapers/google_maps_parser.py`.
    *   Moved the data extraction logic (`_extract_business_data`) into this new module and renamed it to `parse_business_listing_html`.
    *   Updated `cocli/scrapers/google_maps.py` to import and utilize this new parser function.
5.  **Initial Selector Updates & Debugging**:
    *   Added extensive debug logging to `parse_business_listing_html` to show the raw HTML, `innerText`, and extracted data for each field.
    *   Made initial attempts to update selectors in `parse_business_listing_html` to be more generic and prioritize `innerText` parsing.
    *   Confirmed `Name`, `GMB_URL`, `Coordinates`, `Place_ID`, `Average_rating`, `Reviews_count`, `Phone_1`, `Website`, and `Domain` are now being extracted correctly.

## Issues Faced

1.  **Tool Application Failures**: Persistent issues with `apply_diff` and `write_to_file` tools, often due to subtle content mismatches, requiring careful manual verification and re-attempts.
2.  **Environment Setup**: Encountered `pytest: not found` and `source: not found` errors, resolved by explicitly activating the virtual environment and using `bash -c` for command execution.
3.  **Outdated Selectors**: The primary and recurring issue is that Google Maps' HTML structure frequently changes, rendering hardcoded class-based selectors obsolete. This led to all data fields being empty initially.
4.  **Fragile `innerText` Parsing**: Even with the `innerText`-first approach, initial regex patterns for `Full_Address`, `Categories`, and `Hours` were not robust enough, leading to incorrect or empty extractions (e.g., `Full_Address` picking up `Average_rating`).
5.  **Obfuscated Class Names**: The user explicitly highlighted the problem of relying on "random obfuscation strings" as class selectors, emphasizing the need for a more resilient strategy.

## Next Steps

1.  **Refine `parse_business_listing_html` in `cocli/scrapers/google_maps_parser.py`**:
    *   **Critical**: Completely remove reliance on obfuscated class names for *all* fields.
    *   **Prioritize `innerText`**: Focus solely on `innerText` parsing using highly robust regex patterns for `Name`, `Rating`, `Reviews`, `Address`, `Phone`, `Categories`, `Business Status`, and `Hours`.
    *   **Generic HTML Fallbacks**: For fields that *must* come from HTML attributes (like `GMB_URL` and `Website` hrefs), use more generic attribute selectors (e.g., `a[href*='google.com/maps/place']` for GMB URL, and `a[data-value='Website']` or `a[href*='http']` for website) or structural relationships that are less likely to change.
2.  **Update `tests/test_lead_scrape.py`**: Adjust mocks and assertions to reflect the new, more generic parsing strategy, ensuring tests accurately validate the extraction logic.
3.  **Run Tests**: Execute the updated test suite to confirm that the new parsing logic works as expected and does not introduce regressions.
4.  **Request Re-run with Debug**: After all changes and successful tests, ask the user to re-run the `cocli lead-scrape` command with the `--debug` flag to verify the new selectors and inspect the `item_html` and `innerText` processing for accurate data extraction.

## Current `cocli find` Flow (Mermaid Diagram)

```mermaid
graph TD
    A[User runs cocli find [query]] --> B{Multiple Matches?};
    B -- Yes --> C{Interactive Selection};
    C -- User Navigates/Selects --> D[Display Details for Selected Item];
    B -- No, Single Match --> D;
    B -- No Matches --> E[Display "No matches found"];