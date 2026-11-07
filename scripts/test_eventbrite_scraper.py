import asyncio
import logging

from cocli.core.config import set_campaign
from cocli.scrapers.eventbrite_scraper import EventbriteScraper

logging.basicConfig(level=logging.INFO)

async def test_eventbrite_live() -> None:
    # Ensure context is fullertonian
    set_campaign("fullertonian")
    
    scraper = EventbriteScraper(debug=False)
    events = await scraper.scrape_fullerton()
    
    print(f"\n--- SCRAPED {len(events)} EVENTS ---")
    for event in events:
        path = event.save()
        print(f"Saved: {event.name} -> {path}")

if __name__ == "__main__":
    asyncio.run(test_eventbrite_live())
