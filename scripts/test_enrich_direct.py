import asyncio
import logging
import typer
from cocli.core.enrichment import enrich_company_website
from cocli.models.company import Company
from cocli.models.campaign import Campaign
from cocli.core.config import load_campaign_config
from playwright.async_api import async_playwright
from rich.console import Console

app = typer.Typer()
console = Console()

async def run_test(domain: str, campaign_name: str, debug: bool = True) -> None:
    config = load_campaign_config(campaign_name)
    # Prepare Campaign object
    campaign_data = config.get('campaign', {})
    campaign_data.update(config) # Merge sections
    campaign = Campaign.model_validate(campaign_data)
    
    company = Company(name=domain, domain=domain, slug=domain)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            console.print(f"[bold blue]Enriching {domain}...[/bold blue]")
            website_data = await enrich_company_website(
                browser=browser,
                company=company,
                campaign=campaign,
                force=True,
                debug=debug
            )
            
            if website_data:
                console.print("[bold green]Success![/bold green]")
                console.print(website_data.model_dump(exclude_none=True))
            else:
                console.print("[bold red]Failed to enrich (None returned)[/bold red]")
                
        finally:
            await browser.close()

@app.command()
def test_domain(
    domain: str, 
    campaign: str = "turboship", 
    debug: bool = True
) -> None:
    asyncio.run(run_test(domain, campaign, debug))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app()
