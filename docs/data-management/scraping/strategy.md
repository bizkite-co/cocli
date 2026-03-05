# Scraping Strategy: Multi-Stage Simulation

Our scraping architecture avoids the "Limited View" trap by utilizing a formalized, multi-stage state machine that mimics human interaction and browser behavior.

## The State Machine (Production Phase)

We treat every scrape as an auditable process managed by a state machine (see `GoogleMapsDetailsScraper`). This ensures that each step—Warmup, Navigation, Hydration (Heal), and Capture—is verified before moving forward.

### Phase 1: Warmup (Session Trust)
Instead of navigating directly to a deep URL, we begin by establishing session context.
- **Action**: Navigate to `https://www.google.com/maps`.
- **Purpose**: Establishes cookies, storage, and standard browser signals before the specific search occurs.

### Phase 2: Navigation (Human Flow)
We avoid direct URL jumps (e.g., `place_id:CID`).
- **Action**: Use the "Human Flow" pattern (see `navigator.py`):
  1. Click the search box.
  2. Simulate typing the search phrase/query.
  3. Press `Enter`.
- **Purpose**: Triggers the same event listeners and telemetry that a real user would, establishing high "Session Trust."

### Phase 3: Hydration / Session-Heal
Modern applications (like Google Maps) load secondary data (review counts, ratings, detailed attributes) asynchronously after the initial page load. If captured too early, the result is "hollow" data.
- **Action**: Perform "Session-Heal" interactions (see `scanner.py`):
  - **Mouse-Wheel Jitter**: Scroll slightly over listing divs to trigger lazy-loading.
  - **Interaction Clicks**: Click specific elements (e.g., the rating bar) to force hydration of review charts.
- **Wait Pattern**: We wait for high-fidelity semantic markers, such as the `ARIA label` pattern: `\d\.\d\s*stars?\s*[\d,]+\s*Reviews?`.

### Phase 4: Capture & Metadata
The final stage captures the hydrated HTML and packages it into a `RawWitness` model.
- **Metadata Logging**: We log critical session data including:
  - `strategy`: The specific version of the state machine (e.g., `state-machine-v1`).
  - `viewport`: The browser dimensions used.
  - `duration_seconds`: Total time taken for the simulation.
  - `final_state`: Confirms the scrape reached the terminal `completed` state.

## Absolute Fidelity (Browser Stealth)
We have transitioned from optimization (blocking images/fonts) to "Absolute Fidelity."
- **Full Asset Rendering**: All images, fonts, and media are loaded.
- **Hardware Unmasking**: Deep WebGL and Canvas unmasking provide consistent, non-synthetic hardware signals to telemetry.
- **Browser Channel**: We prioritize the `msedge` channel for more realistic telemetry profiles.
