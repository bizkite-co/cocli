import asyncio
import logging
from typing import Optional

from ..models.company import Company
from ..enrichment.website_scraper import WebsiteScraper
from ..models.website import Website

logger = logging.getLogger(__name__)

async def enrich_company_website(
    company: Company,
    force: bool = False,
    ttl_days: int = 30,
    headed: bool = False,
    devtools: bool = False,
    debug: bool = False
) -> Optional[Website]:
    """
    Enriches a single Company object with data scraped from its website.

    This function is the core, reusable logic for website enrichment.
    It does not have side effects like writing files.

    Args:
        company: The Company object to enrich.
        force: Force re-scraping even if fresh data is in the cache.
        ttl_days: Time-to-live for cached data in days.
        headed: Run the browser in headed mode.
        devtools: Open browser with devtools open.
        debug: Enable debug mode with breakpoints.

    Returns:
        A Website object if enrichment is successful, otherwise None.
    """
    if not company.domain:
        logger.info(f"Skipping {company.name} for website enrichment as it has no domain.")
        return None

    logger.info(f"Enriching website for {company.name}")
    scraper = WebsiteScraper()
    website_data = await scraper.run(
        domain=company.domain,
        force_refresh=force,
        ttl_days=ttl_days,
        headed=headed,
        devtools=devtools,
        debug=debug
    )

    return website_data
