import asyncio
import os
import sys
import logging
from pathlib import Path
from cocli.models.campaigns.queues.gm_list import ScrapeTask
from cocli.core.queue.factory import get_queue_manager
from cocli.application.worker_service import WorkerService

# Configure logging
os.makedirs("temp", exist_ok=True)
log_file = "temp/re_enqueue_test.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=log_file,
    filemode='w'
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

async def re_enqueue_targeted():
    campaign = "roadmap"
    lat = 30.2
    lon = -81.2
    phrase = "financial-planner"
    
    # 1. Manually trigger the scrape for this tile bypass regular polling
    print(f"--- TARGETED SCRAPE: {phrase} @ {lat}, {lon} ---")
    
    service = WorkerService(campaign, role="full")
    # We'll use a dummy task to trigger the loop logic manually
    task = ScrapeTask(
        latitude=lat,
        longitude=lon,
        zoom=15,
        search_phrase=phrase,
        campaign_name=campaign,
        tile_id=f"{lat}_{lon}",
        ack_token=f"3/{lat}/{lon}/{phrase}.csv",
        force_refresh=True
    )

    from playwright.async_api import async_playwright
    from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT
    from cocli.utils.playwright_utils import setup_optimized_context

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use the same setup as WorkerService
        context = await browser.new_context(
            ignore_https_errors=True, 
            user_agent=USER_AGENT, 
            extra_http_headers=ANTI_BOT_HEADERS
        )
        tracker = await setup_optimized_context(context)
        
        print("Starting targeted task execution...")
        # We call the loop logic directly for our specific task
        # We need a mock queue that doesn't poll but can ack
        class MockQueue:
            def ack(self, t): print(f"ACK: {t.ack_token}")
            def nack(self, t): print(f"NACK: {t.ack_token}")
            def heartbeat(self, t): pass

        # We need a dummy s3 client
        import boto3
        s3 = boto3.client('s3')
        
        # We wrap our task in a list so poll logic would see it
        # Actually, let's just use the internal method with a tiny modification
        # Or better: just use ScrapeCoordinator directly like the worker does
        from cocli.scrapers.gm_scraper.coordinator import ScrapeCoordinator
        from cocli.application.processors.gm_list import GmListProcessor
        
        coordinator = ScrapeCoordinator(browser, campaign_name=campaign, debug=True)
        
        items = []
        async for item in coordinator.run(
            start_lat=lat,
            start_lon=lon,
            search_phrases=[phrase],
            force_refresh=True
        ):
            print(f"  [FOUND] {item.name} | Rating: {item.average_rating} ({item.reviews_count} reviews)")
            items.append(item)
            if len(items) >= 10: break
            
        if items:
            print(f"Captured {len(items)} items. Saving witness trace...")
            processor = GmListProcessor(processed_by="targeted-repro", bucket_name="roadmap-cocli-data-use1")
            await processor.process_results(task, items, s3_client=s3)
            
            # Show path
            from cocli.core.sharding import get_geo_shard, get_grid_tile_id
            from cocli.core.text_utils import slugify
            lat_shard = get_geo_shard(lat)
            grid_id = get_grid_tile_id(lat, lon)
            lat_tile, lon_tile = grid_id.split("_")
            phrase_slug = slugify(phrase)
            trace_path = f"data/campaigns/{campaign}/queues/gm-list/completed/results/{lat_shard}/{lat_tile}/{lon_tile}/{phrase_slug}.usv"
            print(f"Verification path: {trace_path}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(re_enqueue_targeted())
