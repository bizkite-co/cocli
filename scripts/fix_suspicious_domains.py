import asyncio
import json
import logging
from pathlib import Path

from typing import List, Dict, Any
from playwright.async_api import Browser

import typer
from playwright.async_api import async_playwright
from rich.console import Console
from rich.progress import track

from cocli.enrichment.website_scraper import WebsiteScraper
from cocli.models.campaign import Campaign
from cocli.models.company import Company
from cocli.core.config import load_campaign_config
from cocli.application.company_service import update_company_from_website_data

app = typer.Typer()
console = Console()

# Configure logging to capture scraper output but keep it minimal on console
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

async def process_entry(scraper: WebsiteScraper, browser: Browser, entry: Dict[str, Any], dry_run: bool, campaign: Campaign) -> str:
    file_path_str = entry.get("file_path")
    if not file_path_str:
        return "skipped_no_file_path"
        
    old_file_path = Path(file_path_str)
    
    # 1. Get company_slug from the email index file
    company_slug = None
    if old_file_path.exists():
        try:
            with open(old_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                company_slug = data.get("company_slug")
        except Exception as e:
            logger.error(f"Could not read {old_file_path}: {e}")

    if not company_slug:
        return "skipped_no_company_slug"

    # 2. Load the Company to get the authoritative website URL
    try:
        company = Company.get(company_slug)
    except Exception as e:
        logger.error(f"Error loading company {company_slug}: {e}")
        return "error_loading_company"

    if not company:
        return "skipped_company_not_found"

    target_url = company.website_url or company.domain
    if not target_url:
        return "skipped_company_has_no_website"

    # Scraper.run expects a DOMAIN, not a URL with scheme, as it prepends the scheme itself.
    target_domain = target_url
    if "://" in target_domain:
        target_domain = target_domain.split("://")[-1]
    
    # Remove trailing slashes
    target_domain = target_domain.rstrip('/')

    try:
        if dry_run:
            return "dry_run"

        # Force refresh to test CURRENT scraper logic against this target
        # PASS CAMPAIGN so it saves the email!
        website_data = await scraper.run(
            browser=browser,
            domain=target_domain,
            force_refresh=True, # Force refresh to ensure we are testing current logic
            debug=False,
            campaign=campaign,
            navigation_timeout_ms=60000 # Explicit timeout for navigation
        )

        if not website_data or not website_data.email:
            return "scraped_no_email"
            
        # Check if the NEW email is compliant
        new_email = website_data.email
        domain_part = new_email.split('@')[-1]
        
        if any(c.isupper() for c in domain_part):
             return "failed_still_broken"

        # Success! The code handled this case correctly.
        # The scraper has ALREADY saved the new data to the correct path because we passed 'campaign'.
        
        # PERMANENT FIX: Update the Company record itself via centralized service
        try:
            await update_company_from_website_data(
                company=company,
                website_data=website_data,
                campaign=campaign
            )
        except Exception as e:
            logger.error(f"Failed to update Company record for {company_slug}: {e}")

        # Now we can safely remove the old bad file.
        if old_file_path.exists():
            old_file_path.unlink()
            try:
                # Remove parent dir if empty
                if not any(old_file_path.parent.iterdir()):
                    old_file_path.parent.rmdir()
            except OSError:
                pass 
            return "fixed"
        
        return "fixed_recovered"

    except Exception as e:
        logger.error(f"Error processing {target_url}: {e}")
        return "error"

async def run_fix(input_file: str, dry_run: bool, concurrency: int, campaign_name: str, limit: int = 0) -> None:
    try:
        config_data = load_campaign_config(campaign_name)
        if config_data and 'campaign' in config_data:
            flat_config = config_data.pop('campaign')
            flat_config.update(config_data)
        else:
            flat_config = config_data or {}
        
        campaign = Campaign.model_validate(flat_config)
    except Exception as exc:
        console.print(f"[red]Failed to load campaign '{campaign_name}': {exc}[/red]")
        raise typer.Exit(1)

    with open(input_file, 'r', encoding='utf-8') as f:
        entries: List[Dict[str, Any]] = json.load(f)

    # Filter out entries that match the limit
    entries_to_process = entries[:limit] if limit > 0 else entries

    console.print(f"Processing {len(entries_to_process)} anomalous items with concurrency={concurrency} for campaign '{campaign_name}'...")

    stats: Dict[str, int] = {
        "fixed": 0,
        "fixed_recovered": 0,
        "failed_still_broken": 0,
        "scraped_no_email": 0,
        "skipped_no_domain": 0,
        "skipped_no_company_slug": 0,
        "error_loading_company": 0,
        "skipped_company_not_found": 0,
        "skipped_company_has_no_website": 0,
        "error": 0,
        "timeout": 0,
        "dry_run": 0
    }

    semaphore = asyncio.Semaphore(concurrency)
    
    # Track which entries were fixed so we can remove them from the list
    fixed_indices: set[int] = set()

    async def bounded_process(scraper: WebsiteScraper, browser: Browser, entry: Dict[str, Any], i: int) -> str:
        async with semaphore:
            res = await process_entry(scraper, browser, entry, dry_run, campaign)
            if res == "fixed" or res == "fixed_recovered":
                fixed_indices.add(i)
            return res

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        scraper = WebsiteScraper()
        
        tasks = [bounded_process(scraper, browser, entry, i) for i, entry in enumerate(entries_to_process)]
        
        for result in track(asyncio.as_completed(tasks), total=len(tasks), description="Rescraping anomalies..."):
            res = await result
            if res in stats:
                stats[res] += 1
            else:
                stats["error"] += 1
            
        await browser.close()

    console.print("\n[bold]Summary:[/bold]")
    console.print(json.dumps(stats, indent=2))
    
    # Update the JSON file if there were fixes
    if not dry_run and (stats["fixed"] > 0 or stats["fixed_recovered"] > 0):
        # Build set of fixed keys from the processed slice
        fixed_keys = set()
        for idx in fixed_indices:
            e_item = entries_to_process[idx]
            fixed_keys.add((e_item.get("domain"), e_item.get("file_path")))
            
        # Create new list from original 'entries' to preserve order
        remaining_entries = []
        for e_entry in entries:
            # If it's fixed, skip it (remove)
            if (e_entry.get("domain"), e_entry.get("file_path")) in fixed_keys:
                continue
            
            remaining_entries.append(e_entry)
                
        with open(input_file, 'w', encoding='utf-8') as f:
            json.dump(remaining_entries, f, indent=2)
            
        console.print(f"[green]Updated {input_file}. Removed {len(entries) - len(remaining_entries)} fixed items.[/green]")

@app.command()
def main(
    input_file: str = "suspicious_domains.json", 
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without scraping or deleting"),
    concurrency: int = typer.Option(5, "--concurrency", "-c", help="Number of concurrent scrapes"),
    campaign: str = typer.Option("turboship", "--campaign", help="Campaign name"),
    limit: int = typer.Option(0, "--limit", "-l", help="Limit number of items to process (0 for all)")
) -> None:
    asyncio.run(run_fix(input_file, dry_run, concurrency, campaign, limit))

if __name__ == "__main__":
    app()
