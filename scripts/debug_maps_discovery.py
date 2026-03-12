import asyncio
import logging
from playwright.async_api import async_playwright
from cocli.scrapers.google_maps import scrape_google_maps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_discovery() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        
        search_phrases = ["public library Fullerton CA"]
        campaign_name = "fullertonian"
        
        print(f"Starting debug discovery for: {search_phrases}")
        
        prospect_generator = scrape_google_maps(
            browser=browser,
            location_param={"city": "Fullerton, CA"},
            search_strings=search_phrases,
            campaign_name=campaign_name,
            debug=True
        )
        
        count = 0
        async for item in prospect_generator:
            count += 1
            print(f"FOUND [{count}]: {item.name} ({item.place_id})")
            
        print(f"Discovery complete. Total found: {count}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_discovery())
