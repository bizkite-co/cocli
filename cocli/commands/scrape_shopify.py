from pathlib import Path
from typing import Optional
import typer

from cocli.scrapers.myip_ms import scrape_myip_ms
from cocli.core.config import get_scraped_data_dir

app = typer.Typer()

@app.command()
def scrape_shopify_myip(
    ip_index: int = typer.Option(0, "--ip-index", "-i", help="Index of the IP address to use (0-3)."),
    start_page: int = typer.Option(1, "--start-page", "-s", help="Page number to start scraping from."),
    end_page: int = typer.Option(10, "--end-page", "-e", help="Page number to end scraping at."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Directory to save the scraped CSV file."),
    debug: bool = typer.Option(False, "--debug", help="Enable debug output for scraping."),
) -> None:
    """
    Scrapes Shopify store information from myip.ms.
    Requires manual CAPTCHA solving in the opened browser window.
    """
    ip_addresses = [
        "23.227.38.32",
        "23.227.38.36",
        "23.227.38.65",
        "23.227.38.74",
    ]

    if not 0 <= ip_index < len(ip_addresses):
        typer.echo(f"Error: Invalid IP index. Please choose a number between 0 and {len(ip_addresses) - 1}.", err=True)
        raise typer.Exit(code=1)

    ip_address = ip_addresses[ip_index]

    typer.echo(f"Starting myip.ms Shopify scrape for IP: '{ip_address}' (index: {ip_index})")

    if not output_dir:
        output_dir = get_scraped_data_dir() / "shopify_csv"

    scraped_csv_path = scrape_myip_ms(
        ip_address=ip_address,
        start_page=start_page,
        end_page=end_page,
        output_dir=output_dir,
        debug=debug,
    )

    if scraped_csv_path:
        typer.echo(f"myip.ms Shopify scraping completed. Results saved to {scraped_csv_path}")
    else:
        typer.echo("myip.ms Shopify scraping failed.", err=True)
        raise typer.Exit(code=1)
