# POLICY: frictionless-data-policy-enforcement
import pytest
import json
import re
from pathlib import Path
from datetime import datetime, timedelta, UTC
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from cocli.scrapers.google.gm_scraper.scanner import SidebarScraper
from cocli.scrapers.google.google_maps_parsers.extract_rating_reviews_gm_list import extract_rating_reviews_gm_list

GROUND_TRUTH_DIR = Path("tests/data/maps.google.com")
HTML_PATH = GROUND_TRUTH_DIR / "gm-list.html"
JSON_PATH = GROUND_TRUTH_DIR / "ground_truth.json"
ITEM_DIR = GROUND_TRUTH_DIR / "gm-list"

@pytest.mark.asyncio
async def test_gm_list_ground_truth_and_parsing():
    """
    PHASED TEST with implementation logging.
    """
    if not JSON_PATH.exists():
        pytest.skip("ground_truth.json missing.")

    with open(JSON_PATH, "r") as f:
        truth = json.load(f)

    # --- Setup Run Recording ---
    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(f"temp/tests/{run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)

    # Use production stealth utility
    from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT
    
    metadata = {
        "id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "search_url": truth["search_url"],
        "browser_settings": {
            "browser_type": "chromium",
            "viewport": {"width": 1280, "height": 1024},
            "user_agent": USER_AGENT,
            "headers": ANTI_BOT_HEADERS,
            "stealth_v3": "Navigator/CSS/WebGL/Canvas Masking",
            "wait_until": "load"
        },
        "hydration_timeout_max": 10000,
        "scroll_method": "mouse_wheel_optimized"
    }

    # --- PHASE 1 & 2: Refresh if stale ---
    is_stale = not HTML_PATH.exists() or (datetime.now(UTC) - datetime.fromtimestamp(HTML_PATH.stat().st_mtime, tz=UTC)) > timedelta(days=7)
    
    if is_stale:
        # Save intent early
        with open(run_dir / "run_metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)


        async with async_playwright() as p:
            # HEADLESS for automated tests
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport=metadata["browser_settings"]["viewport"],
                user_agent=metadata["browser_settings"]["user_agent"]
            )
            
            from cocli.utils.playwright_utils import setup_stealth_context
            await setup_stealth_context(context)
            
            page = await context.new_page()
            from cocli.scrapers.google.gm_scraper.navigator import Navigator
            nav = Navigator(page)
            
            success = await nav.goto(34.2499, -118.2605, 2.0, 1.0, query="auto parts")
            assert success, "Production Human navigation flow failed."
            
            scraper = SidebarScraper(page)
            listings = await page.locator('div[role="article"]').all()
            

            
            captured_html_blocks = []
            for i, div in enumerate(listings):
                # Optimization: Only wait for the first 3 items to hydrate to prove the point
                # This saves massive time while still ensuring we get high-fidelity data in the file
                if i < 3:
                    try:
                        await div.scroll_into_view_if_needed()
                        await scraper.wait_for_hydration(div)
                    except Exception:
                        pass
                
                html = await scraper.capture_listing_html(div)
                captured_html_blocks.append(html)
            
            # Save Snapshot to run dir
            snapshot_path = run_dir / "snapshot.png"
            await page.screenshot(path=str(snapshot_path), full_page=True)
            
            full_doc = "<html><body>\n" + "\n".join(captured_html_blocks) + "\n</body></html>"
            with open(HTML_PATH, "w", encoding="utf-8") as f:
                f.write(full_doc)
            

            await browser.close()
    else:
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            full_doc = f.read()


    # --- PHASE 3: Validate RECORDED Fidelity ---
    high_fidelity_pattern = re.compile(r'aria-label="\d\.\d\s*stars?\s*[\d,]+\s*Reviews?"', re.IGNORECASE)
    matches = high_fidelity_pattern.findall(full_doc)
    

    assert len(matches) > 0, "Current settings failed to hydrate reviews. See snapshot in run dir."

    # --- PHASE 4: Verify Parser against the recorded HTML ---
    soup = BeautifulSoup(full_doc, "html.parser")
    listing_divs = soup.find_all("div", attrs={"role": "article"})
    
    results_found = 0
    for listing in listing_divs:
        inner_text = listing.get_text(separator=" ", strip=True)
        parsed = extract_rating_reviews_gm_list(listing, inner_text, debug=False)
        if parsed["Average_rating"] and parsed["Reviews_count"]:
            results_found += 1
            

    assert results_found >= 1, f"Parser failed to extract data even from hydrated items. Found only {results_found}."
