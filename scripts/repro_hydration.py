import asyncio
import logging
from playwright.async_api import async_playwright
from cocli.scrapers.google_maps_details import capture_google_maps_raw
from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repro_hydration")

async def repro_hydration():
    # Target: Griffith Observatory (DEFINITELY has ratings)
    place_id = "ChIJ5X0j7DHDwogRvQgaGw0y4FM" 
    campaign = "roadmap"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # Headless for this environment
        context = await browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers=ANTI_BOT_HEADERS,
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        
        url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        logger.info(f"Navigating to {url}")
        
        try:
            # wait_until="networkidle" is often too slow/unreliable
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # Wait for the main pane to appear
            await page.wait_for_selector('div[role="main"]', timeout=30000)
            logger.info("Page loaded.")
            
            # Try the capture logic
            witness = await capture_google_maps_raw(page, place_id, campaign, debug=True)
            
            if witness:
                from cocli.scrapers.google_maps_parsers.extract_rating_reviews import extract_rating_reviews
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(witness.html, "html.parser")
                results = extract_rating_reviews(soup, soup.get_text(), debug=True)
                logger.info(f"Final Extraction: {results}")
            else:
                logger.error("Failed to capture raw witness.")
                
        except Exception as e:
            logger.error(f"Repro failed: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(repro_hydration())
