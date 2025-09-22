from pathlib import Path
from typing import Optional
import typer

from cocli.scrapers.myip_ms import scrape_myip_ms
from cocli.core.config import get_scraped_data_dir

app = typer.Typer()

@app.command()
def scrape_shopify_myip(
    ip_address: str = typer.Argument(..., help="IP address associated with Shopify stores (e.g., '23.227.38.32')."),
    # Removed start_segment as it's now handled internally by the scraper starting from page 1
    max_pages: int = typer.Option(10, "--max-pages", "-m", help="Maximum number of pages (segments) to scrape."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Directory to save the scraped CSV file."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output for scraping."),
):
    """
    Scrapes Shopify store information from myip.ms.
    Requires manual CAPTCHA solving in the opened browser window.
    """
    typer.echo(f"Starting myip.ms Shopify scrape for IP: '{ip_address}'")

    if not output_dir:
        output_dir = get_scraped_data_dir() / "shopify_csv"

    scraped_csv_path = scrape_myip_ms(
        ip_address=ip_address,
        # Removed start_segment from the function call
        max_pages=max_pages,
        output_dir=output_dir,
        debug=debug,
    )

    if scraped_csv_path:
        typer.echo(f"myip.ms Shopify scraping completed. Results saved to {scraped_csv_path}")
    else:
        typer.echo("myip.ms Shopify scraping failed.", err=True)
        raise typer.Exit(code=1)
