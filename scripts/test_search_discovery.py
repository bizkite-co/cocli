import asyncio
import logging
from cocli.scrapers.event_search_scraper import EventSearchScraper
from cocli.core.config import set_campaign

logging.basicConfig(level=logging.INFO)

async def test_search_live() -> None:
    set_campaign("fullertonian")
    scraper = EventSearchScraper(debug=True)
    
    query = "Current local events and restaurant openings in Fullerton CA March 2026"
    print(f"\n--- RUNNING WEB SEARCH DISCOVERY: '{query}' ---")
    
    events = await scraper.search_and_extract(query)
    print(f"Found {len(events)} potential events.")
    
    for event in events:
        path = event.save()
        print(f"Saved: {event.name} -> {path}")

if __name__ == "__main__":
    asyncio.run(test_search_live())
