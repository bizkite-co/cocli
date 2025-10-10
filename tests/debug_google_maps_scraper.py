import argparse
import logging
from cocli.scrapers.google_maps import scrape_google_maps

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug Google Maps Scraper")
    parser.add_argument("--search", type=str, required=True, help="Search string for Google Maps")
    parser.add_argument("--zip-code", type=str, help="ZIP code for the location")
    parser.add_argument("--city", type=str, help="City for the location")
    parser.add_argument("--max-results", type=int, default=1, help="Maximum number of results to scrape")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode (non-headless)")
    parser.add_argument("--devtools", action="store_true", help="Open browser devtools")
    
    args = parser.parse_args()

    location = {}
    if args.zip_code:
        location["zip_code"] = args.zip_code
    elif args.city:
        location["city"] = args.city
    else:
        location["zip_code"] = "90210"
        logger.info("No location provided, defaulting to zip code 90210.")


    logger.info(f"--- Starting Google Maps Scraper Debug Session ---")
    logger.info(f"Search Query: {args.search}")
    logger.info(f"Location: {location}")

    scraped_data = scrape_google_maps(
        location_param=location,
        search_string=args.search,
        max_results=args.max_results,
        debug=True,  # Always in debug mode for this script
        headless=not args.headed,
        devtools=args.devtools,
    )

    logger.info(f"\n--- Scraped Data ---")
    for item in scraped_data:
        logger.info(item.model_dump_json(indent=2))
    logger.info(f"--- End of Scraped Data ---")

    if scraped_data:
        assert len(scraped_data) > 0
        assert scraped_data[0].Name is not None