import logging
from typing import Optional

from playwright.async_api import Browser, BrowserContext

from ..models.companies.company import Company
from ..models.campaigns.campaign import Campaign # New import
from ..enrichment.website_scraper import WebsiteScraper
from ..models.companies.website import Website

logger = logging.getLogger(__name__)

async def enrich_company_website(
    browser: Browser | BrowserContext,
    company: Company,
    campaign: Optional[Campaign] = None,
    force: bool = False,
    ttl_days: int = 30,
    debug: bool = False,
    navigation_timeout_ms: Optional[int] = None # New parameter
) -> Optional[Website]:
    """
    Enriches a single Company object with data scraped from its website.

    This function is the core, reusable logic for website enrichment.
    It does not have side effects like writing files.
    
    Uses a pre-existing browser instance.

    Args:
        browser: The shared Playwright browser instance.
        company: The Company object to enrich.
        campaign: The Campaign object associated with the enrichment.
        force: Force re-scraping even if fresh data is in the cache.
        ttl_days: Time-to-live for cached data in days.
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
        browser=browser,
        domain=company.domain,
        company_slug=company.slug,
        campaign=campaign, # Pass the campaign object
        force_refresh=force,
        ttl_days=ttl_days,
        debug=debug,
        navigation_timeout_ms=navigation_timeout_ms or 30000 # Pass new param
    )

    return website_data
