# POLICY: frictionless-data-policy-enforcement
import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright

# Add project root to path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from cocli.scrapers.google.google_maps_parser import parse_business_listing_html

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def refresh_ground_truth() -> None:
    output_base = Path("tests/data/maps.google.com")
    html_out = output_base / "gm-list.html"
    items_dir = output_base / "gm-list"
    items_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Ground Truth URL (Auto Parts Search)
        url = "https://www.google.com/maps/search/auto+parts/@34.2499124,-118.2605756,13z"
        logger.info(f"Navigating to {url}...")
        
        try:
            await page.goto(url, wait_until="load", timeout=60000)
            
            # Wait for the scrollable feed
            scrollable_div_selector = 'div[role="feed"]'
            await page.wait_for_selector(scrollable_div_selector, timeout=30000)
            
            # HYDRATION WAIT (Replicating SidebarScraper logic)
            # Wait for at least one semantic star rating to appear
            await page.locator('span[aria-label^="4"], span[aria-label^="5"]').first.wait_for(timeout=15000)
            await asyncio.sleep(2) # Stabilize
            
            # 1. Save Full Page HTML
            full_html = await page.content()
            with open(html_out, "w", encoding="utf-8") as f:
                f.write(full_html)
            logger.info(f"Saved full page to {html_out}")

            # 2. Extract and Save Individual Items (Trace logic)
            listing_divs = await page.locator('div[role="feed"] > div').all()
            logger.info(f"Found {len(listing_divs)} potential listing divs.")
            
            count = 0
            for div in listing_divs:
                try:
                    html_content = await div.evaluate("el => el.outerHTML")
                    if not html_content or "All filters" in html_content:
                        continue
                        
                    # Use production parser to get Place ID for naming
                    # We use a dummy phrase since it's just for naming
                    data = parse_business_listing_html(html_content, "auto parts")
                    place_id = data.get("Place_ID")
                    
                    if place_id:
                        item_path = items_dir / f"{place_id}.html"
                        with open(item_path, "w", encoding="utf-8") as f:
                            f.write(html_content)
                        count += 1
                except Exception:
                    continue
            
            logger.info(f"Saved {count} individual items to {items_dir}")

        except Exception as e:
            logger.error(f"Refresh failed: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(refresh_ground_truth())
