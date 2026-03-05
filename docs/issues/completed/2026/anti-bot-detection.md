# Anti-Bot Detection & High-Fidelity Scraping Breakthrough

## The Problem: The "Limited View" Trap
During the `turboship` and `roadmap` campaigns, we identified a persistent failure state where Google Maps would serve a "Limited View" to our automated scrapers. 

### Symptoms:
- **Missing Review Counts**: Listing items showed only names and addresses; review counts were completely absent from the DOM.
- **Empty Map Tiles**: The map area remained gray or failed to render tiles.
- **Simplified DOM**: Many semantic markers used by our parsers were stripped or replaced with obfuscated placeholders.
- **Persistence**: Traditional bypasses (User-Agent rotation, basic stealth plugins) failed to resolve the issue.

## Root Cause Analysis
We discovered that Google's bot detection was triggered by two primary signals:
1. **Direct-to-Search Navigation**: Starting a session directly at a long latitude/longitude search URL is a high-confidence indicator of automated activity.
2. **Resource Blocking**: To save bandwidth, we were blocking images, fonts, and media. This created an "impossible" browser fingerprint that Google's modern telemetry immediately flagged as a "headless" or "limited" environment.

## The Multi-Layered Solution

The technical resolution for the "Limited View" trap has been formalized into our core scraping strategy. For detailed architectural documentation, see:

- [**Scraping Strategy: Multi-Stage Simulation**](../../data-management/scraping/strategy.md)
- [**Quality Control & Testing**](../../data-management/scraping/quality-control.md)

### 1. "Human Flow" Navigation (`navigator.py`)
We abandoned direct URL navigation in favor of a simulated human search flow:
- **Home Page Start**: The session begins at `https://www.google.com/maps`.
- **Simulated Interaction**: The scraper locates the search box, simulates realistic typing of the search phrase, and triggers the search with an `Enter` keypress.
- **Session Trust**: This establishes a "Human-like" session origin, significantly reducing initial bot suspicion.

### 2. Maximum Fidelity Stealth (`playwright_utils.py`)
We transitioned from "Optimization" to "Absolute Fidelity":
- **Full Asset Rendering**: Removed all resource blocking. The browser now loads all images, fonts, and media, creating a believable, heavy browser fingerprint.
- **Hardware Unmasking**: Implemented deep WebGL and Canvas unmasking to provide consistent, non-synthetic hardware signals to Google's telemetry.
- **Browser Channel**: Prioritized the `msedge` channel (or high-fidelity Chromium) for more realistic telemetry.

### 3. Semantic Hydration Waiting & Session-Heal (`scanner.py`)
Listing data is hydrated asynchronously. Capturing too early resulted in empty fields. 
- **Hydration Marker**: We implemented a production-grade wait for the combined ARIA label pattern: `\d\.\d\s*stars?\s*[\d,]+\s*Reviews?`.
- **Session-Heal**: The scraper now performs "jitter" and clicks on review elements to trigger hydration (see the `hydrating` state in `GoogleMapsDetailsScraper`).

### 4. Specialized Parser (`extract_rating_reviews_gm_list.py`)
We decoupled the List and Details parsers. The new `gm-list` parser aggressively targets the high-fidelity semantic labels discovered in the hydrated DOM, ensuring we capture both ratings and counts accurately.

## Verification & Results
- **Success Rate**: 100% of tested listings now show hydrated review counts.
- **Parser Accuracy**: 7/8 items in the ground-truth set now extract BOTH rating and reviews (compared to 0/8 previously).
- **Quality Audits**: We use `scripts/audit_prospect_quality.py` as a production QC practice to detect regressions in hydration coverage.

## Implementation Details
- **Codebase Integrity**: All trace files and models (e.g., `GoogleMapsListItem`) now follow the **Frictionless Data Mandate** using `BaseUsvModel`.
- **Cluster Ready**: These fixes have been deployed via hotfix to all nodes in the RPi cluster (`cocli5x1.pi`, etc.) for the 5,000-item rollout.
