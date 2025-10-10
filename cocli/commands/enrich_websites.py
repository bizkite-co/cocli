import typer
from pathlib import Path
import yaml
import asyncio
import logging

from cocli.core.config import get_companies_dir
from cocli.enrichment.website_scraper import WebsiteScraper
from cocli.models.company import Company
from cocli.compilers.website_compiler import WebsiteCompiler

logger = logging.getLogger(__name__)

async def _enrich_company(
    company_dir: Path,
    force: bool,
    ttl_days: int,
    headed: bool,
    devtools: bool,
    debug: bool
):
    company = Company.from_directory(company_dir)
    if not company or not company.domain:
        return

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

    if website_data:
        enrichment_dir = company_dir / "enrichments"
        website_md_path = enrichment_dir / "website.md"
        website_data.associated_company_folder = company_dir.name
        enrichment_dir.mkdir(parents=True, exist_ok=True)
        with open(website_md_path, "w") as f:
            f.write("---")
            yaml.dump(website_data.model_dump(exclude_none=True), f, sort_keys=False, default_flow_style=False, allow_unicode=True)
            f.write("---")
        logger.info(f"Saved website enrichment for {company.name}")

        compiler = WebsiteCompiler()
        compiler.compile(company_dir)

def enrich_websites(
    force: bool = typer.Option(False, "--force", "-f", help="Force enrichment of all companies, even if they have fresh data."),
    ttl_days: int = typer.Option(30, "--ttl-days", help="Time-to-live for cached data in days."),
    headed: bool = typer.Option(False, "--headed", help="Run the browser in headed mode."),
    devtools: bool = typer.Option(False, "--devtools", help="Open browser with devtools open."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode with breakpoints."),
    workers: int = typer.Option(4, "--workers", "-w", help="Number of parallel workers to use."),
):
    """
    Enriches all companies with website data, using a cache-first strategy.
    """
    async def main():
        companies_dir = get_companies_dir()
        company_dirs = [d for d in companies_dir.iterdir() if d.is_dir()]
        
        semaphore = asyncio.Semaphore(workers)

        async def run_with_semaphore(company_dir):
            async with semaphore:
                await _enrich_company(
                    company_dir,
                    force,
                    ttl_days,
                    headed,
                    devtools,
                    debug
                )

        tasks = [run_with_semaphore(company_dir) for company_dir in company_dirs]
        await asyncio.gather(*tasks)

    asyncio.run(main())
