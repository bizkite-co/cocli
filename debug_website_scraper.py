import argparse
import asyncio
import logging
from playwright.async_api import async_playwright
from cocli.enrichment.website_scraper import WebsiteScraper

logger = logging.getLogger(__name__)

async def main() -> None:
    parser = argparse.ArgumentParser(description="Debug Website Scraper")
    parser.add_argument("--domain", type=str, required=True, help="Domain to scrape")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode")
    parser.add_argument("--devtools", action="store_true", help="Open browser devtools")
    
    args = parser.parse_args()

    logger.info("--- Starting Website Scraper Debug Session ---")
    logger.info(f"Domain: {args.domain}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed, devtools=args.devtools)
        scraper = WebsiteScraper()
        website_data = await scraper.run(
            browser=browser,
            domain=args.domain,
            debug=True,
        )
        await browser.close()

    if website_data:
        logger.info("\n--- Scraped Data ---")
        logger.info(website_data.model_dump_json(indent=2))
        logger.info("--- End of Scraped Data ---")
    else:
        logger.warning("--- No data scraped ---")

if __name__ == "__main__":
    asyncio.run(main())

