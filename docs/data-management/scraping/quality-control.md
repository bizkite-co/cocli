# Quality Control & Testing

High-fidelity scraping requires a multi-stage testing and audit strategy to ensure the production code correctly navigates, hydrates, and parses data in the face of ever-changing anti-bot measures.

## 1. Multi-Stage Testing

We distinguish between **Unit/Parser Testing** and **Browser/Alignment Testing**.

### Unit/Parser Testing
Testing the logic that extracts data from raw HTML.
- **Goal**: Ensure the parser accurately targets hydrated semantic elements.
- **Example**: `scripts/debug_review_extraction.py`.
- **Method**: Use saved "Raw Witness" files (ground-truth HTML) to test the `extract_rating_reviews_gm_list` parser without a live browser.

### Browser/Alignment Testing
Testing the simulation and hydration logic in a live browser.
- **Goal**: Verify that the "Session-Heal" interactions correctly trigger hydration of the DOM.
- **Example**: `scripts/debug_rating_wait.py`, `scripts/repro_hydration.py`.
- **Method**: Run the full state machine against live targets and monitor for hydration markers (e.g., the appearance of review counts).

## 2. Production QC (Audit Scripts)

Quality Control is a standard practice integrated into our production campaigns.

### Statistical Quality Audits
We perform regular audits of collected data using scripts like `scripts/audit_prospect_quality.py`.
- **Logic**: Use DuckDB to analyze the collected `RawWitness` metadata.
- **Canary Success Metrics**: A rollout is considered successful if it meets the following "High-Fidelity" thresholds:
  - **Reviews Coverage**: >40% of discovered items must have a review count.
  - **Ratings Coverage**: >60% of discovered items must have a rating value.
- **Alerts**: We monitor for specific "Limited View" failure markers if these thresholds are not met.

### Feedback Loop for Optimization
These audit reports act as the primary trigger for scraping optimization.
- **Degradation Detection**: When audit thresholds are breached, the system alerts the team to "Limited View" detection.
- **Hotfix Validation**: We use the same audit scripts to verify that hotfixes (e.g., a new "Session-Heal" click) restore high-fidelity data capture across the cluster.

## 3. Best Practices for Scraping Optimization

1. **Verify Hydration First**: Never optimize for speed until the "High-Fidelity" hydration is 100% reliable.
2. **Ground-Truth Benchmarking**: Use a set of "Known Good" targets (e.g., highly-reviewed businesses) to baseline the scraper's performance.
3. **Cluster-Aware Audits**: Ensure that quality is consistent across all residential nodes (RPis), as local IP reputations can vary.
