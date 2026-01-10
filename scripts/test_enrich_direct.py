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
    
    # Correct resolution: Find existing company or use proper slugification
    from cocli.core.text_utils import slugify
    company_slug = slugify(domain)
    company = Company.get(company_slug)
    if not company:
        console.print(f"[yellow]No existing company found for slug '{company_slug}'. Creating temporary Company object.[/yellow]")
        company = Company(name=domain, domain=domain, slug=company_slug)
    
    console.print(f"Enriching [bold]{domain}[/bold] (Slug: [cyan]{company.slug}[/cyan])...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            website_data = await enrich_company_website(
                browser=browser,
                company=company,
                campaign=campaign,
                force=True,
                debug=debug
            )
            if website_data:
                # Save using the validated slug
                website_data.save(company.slug)
                console.print("[green]Success![/green]")
                console.print(website_data.model_dump(exclude={'sitemap_xml'}))
            else:
                console.print("[red]Enrichment failed.[/red]")
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
