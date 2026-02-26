import asyncio
import os
import sys
from playwright.async_api import async_playwright

# Ensure we can import from cocli
sys.path.append(os.getcwd())

from cocli.scrapers.gm_scraper.coordinator import ScrapeCoordinator
from cocli.application.processors.gm_list import GmListProcessor
from cocli.models.campaigns.queues.gm_list import ScrapeTask

async def reproduce_list_scrape() -> None:
    campaign = "roadmap"
    lat, lon = 34.1176, -118.3002
    phrase = "griffith"
    
    print("\n--- Reproducing Scrape for " + phrase + " at " + str(lat) + ", " + str(lon) + " ---")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # coordinator creates its own optimized context
        coordinator = ScrapeCoordinator(browser, campaign_name=campaign, debug=True)
        print("Starting Scrape Coordinator...")
        
        task = ScrapeTask(
            latitude=lat,
            longitude=lon,
            zoom=15,
            search_phrase=phrase,
            campaign_name=campaign,
            force_refresh=True,
            ack_token="repro-token"
        )
        
        items = []
        async for item in coordinator.run(
            start_lat=lat,
            start_lon=lon,
            search_phrases=[phrase],
            force_refresh=True
        ):
            print("  [DISCOVERED] " + str(item.name) + " | Rating: " + str(item.average_rating) + " (" + str(item.reviews_count) + " reviews)")
            items.append(item)
            if len(items) >= 5:
                break
            
        if items:
            print("\nDiscovered " + str(len(items)) + " items. Saving trace...")
            processor = GmListProcessor(processed_by="repro-script")
            await processor.process_results(task, items)
            
            from cocli.core.sharding import get_geo_shard, get_grid_tile_id
            from cocli.core.text_utils import slugify
            lat_shard = get_geo_shard(lat)
            grid_id = get_grid_tile_id(lat, lon)
            lat_tile, lon_tile = grid_id.split("_")
            phrase_slug = slugify(phrase)
            trace_path = "data/campaigns/" + campaign + "/queues/gm-list/completed/results/" + lat_shard + "/" + lat_tile + "/" + lon_tile + "/" + phrase_slug + ".usv"
            print("Trace saved to: " + trace_path)
        else:
            print("No items discovered.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(reproduce_list_scrape())
