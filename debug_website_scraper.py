import argparse
import asyncio
from cocli.enrichment.website_scraper import WebsiteScraper

async def main():
    parser = argparse.ArgumentParser(description="Debug Website Scraper")
    parser.add_argument("--domain", type=str, required=True, help="Domain to scrape")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode")
    parser.add_argument("--devtools", action="store_true", help="Open browser devtools")
    
    args = parser.parse_args()

    print(f"--- Starting Website Scraper Debug Session ---")
    print(f"Domain: {args.domain}")

    scraper = WebsiteScraper()
    website_data = await scraper.run(
        domain=args.domain,
        headed=args.headed,
        devtools=args.devtools,
        debug=True,
    )

    if website_data:
        print(f"\n--- Scraped Data ---")
        print(website_data.model_dump_json(indent=2))
        print(f"--- End of Scraped Data ---")
    else:
        print("--- No data scraped ---")

if __name__ == "__main__":
    asyncio.run(main())

