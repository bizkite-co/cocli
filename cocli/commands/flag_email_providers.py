import typer
from typing import List

from ..core.website_cache import WebsiteCache

def flag_email_providers(
    domains: List[str] = typer.Argument(..., help="A list of email provider domains to flag in the cache.")
):
    """
    Flags a list of domains as email providers in the website cache.
    """
    cache = WebsiteCache()
    for domain in domains:
        cache.flag_as_email_provider(domain)
        print(f"Flagged {domain} as an email provider.")
    cache.save()
    print("Email provider list saved to cache.")