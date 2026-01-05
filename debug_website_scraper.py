import argparse
import asyncio
import logging
from playwright.async_api import async_playwright
from cocli.enrichment.website_scraper import WebsiteScraper
from cocli.models.company import Company
from cocli.application.company_service import update_company_from_website_data
from cocli.models.campaign import Campaign

logger = logging.getLogger(__name__)

async def main() -> None:
    parser = argparse.ArgumentParser(description="Debug Website Scraper")
    parser.add_argument("--domain", type=str, required=True, help="Domain to scrape")
    parser.add_argument("--company-slug", type=str, help="Update local company record")
    parser.add_argument("--campaign", type=str, help="Campaign context for S3 sync")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode")
    parser.add_argument("--devtools", action="store_true", help="Open browser devtools")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (breakpoints)")
    parser.add_argument("--force", action="store_true", help="Force refresh (ignore cache)")
    
    args = parser.parse_args()

    logger.info("--- Starting Website Scraper Debug Session ---")
    logger.info(f"Domain: {args.domain}")

    company = None
    campaign = None
    if args.company_slug:
        company = Company.get(args.company_slug)
        if not company:
            logger.error(f"Company {args.company_slug} not found.")
            return
        if args.campaign:
            # Simple campaign object for sync
            from cocli.core.config import load_campaign_config
            try:
                config_data = load_campaign_config(args.campaign)
                if 'campaign' in config_data:
                    flat_config = config_data.pop('campaign')
                    flat_config.update(config_data)
                else:
                    flat_config = config_data
                campaign = Campaign.model_validate(flat_config)
            except Exception as e:
                logger.warning(f"Could not load campaign {args.campaign}: {e}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed, devtools=args.devtools)
        scraper = WebsiteScraper()
        website_data = await scraper.run(
            browser=browser,
            domain=args.domain,
            debug=args.debug,
            force_refresh=args.force,
            campaign=campaign
        )
        await browser.close()

    if website_data:
        if args.company_slug:
            website_data.associated_company_folder = args.company_slug
            
        logger.info("\n--- Scraped Data ---")
        logger.info(website_data.model_dump_json(indent=2))
        logger.info("--- End of Scraped Data ---")
        
        if company:
            logger.info(f"Updating company record for {args.company_slug}...")
            await update_company_from_website_data(company, website_data, campaign=campaign)
            logger.info("Local update complete.")
    else:
        logger.warning("--- No data scraped ---")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

