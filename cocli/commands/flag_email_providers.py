import typer
from typing import List
import logging

from ..core.website_cache import WebsiteCache

logger = logging.getLogger(__name__)

def flag_email_providers(
    domains: List[str] = typer.Argument(..., help="A list of email provider domains to flag in the cache.")
):
    """
    Flags a list of domains as email providers in the website cache.
    """
    cache = WebsiteCache()
    for domain in domains:
        cache.flag_as_email_provider(domain)
        logger.info(f"Flagged {domain} as an email provider.")
    cache.save()
    logger.info("Email provider list saved to cache.")