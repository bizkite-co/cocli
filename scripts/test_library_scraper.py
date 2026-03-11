import asyncio
import logging
from cocli.scrapers.calendar_scraper import CalendarScraper
from cocli.core.config import set_campaign

logging.basicConfig(level=logging.INFO)

async def test_scrapers_live() -> None:
    set_campaign("fullertonian")
    scraper = CalendarScraper(debug=False)
    
    print("\n--- SCRAPING FULLERTON OBSERVER ---")
    observer_events = await scraper.scrape_fullerton_observer()
    print(f"Found {len(observer_events)} Observer events.")
    for event in observer_events[:3]:
        path = event.save()
        print(f"Saved: {event.name} -> {path}")

    print("\n--- SCRAPING FULLERTON LIBRARY ---")
    library_events = await scraper.scrape_fullerton_library()
    print(f"Found {len(library_events)} Library events.")
    for event in library_events[:3]:
        path = event.save()
        print(f"Saved: {event.name} -> {path}")

if __name__ == "__main__":
    asyncio.run(test_scrapers_live())
