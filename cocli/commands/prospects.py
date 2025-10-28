import typer
import csv
import logging
from typing_extensions import Annotated
from typing import Optional, Iterator
import asyncio
import httpx
import yaml
from rich.console import Console

from pydantic import ValidationError

from cocli.models.company import Company
from cocli.models.hubspot import HubspotContactCsv
from cocli.core.config import get_campaign, get_campaigns_dir, get_companies_dir, get_scraped_data_dir
from cocli.models.website import Website
from cocli.compilers.website_compiler import WebsiteCompiler
from cocli.core.utils import slugify
from cocli.core.enrichment_service_utils import ensure_enrichment_service_ready
from cocli.core.logging_config import setup_file_logging

app = typer.Typer(no_args_is_help=True)

logger = logging.getLogger(__name__)

def get_prospects(campaign: str, with_email: bool, city: Optional[str], state: Optional[str]) -> Iterator[Company]:
    """Yields companies that match the filter criteria."""
    for company in Company.get_all():
        if campaign in company.tags:
            if with_email and not company.email:
                continue
            if city and company.city != city:
                continue
            if state and company.state != state:
                continue
            yield company

@app.command("to-hubspot-csv")
def to_hubspot_csv(
    with_email: Annotated[bool, typer.Option("--with-email", help="Only include prospects with email addresses.")] = True,
    city: Annotated[Optional[str], typer.Option(help="Filter by city.")] = None,
    state: Annotated[Optional[str], typer.Option(help="Filter by state.")] = None,
) -> None:
    """
    Exports campaign prospects to a HubSpot CSV file.
    """
    campaign = get_campaign()
    if not campaign:
        print("No campaign set. Please set a campaign using `cocli campaign set <campaign_name>`.")
        raise typer.Exit(1)

    prospects = get_prospects(campaign, with_email, city, state)

    campaigns_dir = get_campaigns_dir()
    output_dir = campaigns_dir / campaign / "prospects" / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"hubspot_export_{campaign}.csv"
    exported_count = 0

    with open(output_file, "w", newline="") as csvfile:
        fieldnames = HubspotContactCsv.model_fields.keys()
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for prospect in prospects:
            try:
                contact = HubspotContactCsv(
                    company=prospect.name,
                    phone=prospect.phone_1,
                    website=prospect.website_url,
                    city=prospect.city,
                    state=prospect.state,
                    email=prospect.email or "",
                )
                writer.writerow(contact.model_dump())
                exported_count += 1
            except ValidationError as e:
                logger.warning(f"Skipping prospect {prospect.name} due to invalid data: {e}")

    print(f"Exported {exported_count} prospects to {output_file}")


async def enrich_prospect(client: httpx.AsyncClient, prospect: Company, force: bool, ttl_days: int, console: Console) -> None:
    logger.info(f"Attempting to enrich domain: {prospect.domain} for company: {prospect.name}")
    try:
        logger.debug(f"Sending enrichment request for domain: {prospect.domain}")
        response = await client.post(
            "http://localhost:8000/enrich",
            json={
                "domain": prospect.domain,
                "force": force,
                "ttl_days": ttl_days,
            },
            timeout=120.0,
        )
        logger.debug(f"Received response for {prospect.domain}: Status {response.status_code}")
        response.raise_for_status()
        response_json = response.json()
        if response_json:
            website_data = Website(**response_json)
            if website_data.email:
                logger.info(f"  -> Found email for {prospect.name}: {website_data.email}")
                if prospect.slug is None:
                    logger.warning(f"Skipping enrichment data save for company {prospect.name} due to missing slug.")
                    return
                company_dir = get_companies_dir() / prospect.slug
                enrichment_dir = company_dir / "enrichments"
                website_md_path = enrichment_dir / "website.md"
                website_data.associated_company_folder = company_dir.name
                enrichment_dir.mkdir(parents=True, exist_ok=True)
                with open(website_md_path, "w") as f:
                    f.write("---")
                    yaml.dump(
                        website_data.model_dump(exclude_none=True),
                        f,
                        sort_keys=False,
                        default_flow_style=False,
                        allow_unicode=True,
                    )
                    f.write("---")
                compiler = WebsiteCompiler()
                compiler.compile(company_dir)
            else:
                console.print(f"  -> No new information found for {prospect.name}")
    except httpx.RequestError as e:
        logger.error(f"HTTP Request Error enriching {prospect.name}: {e}")
        console.print(f"  -> Error enriching {prospect.name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected Error enriching {prospect.name}: {e}")
        console.print(f"  -> Error enriching {prospect.name}: {e}")

@app.command("enrich")
def enrich_prospects_command(
    force: Annotated[bool, typer.Option("--force", "-f", help="Force re-enrichment even if fresh data exists.")] = False,
    ttl_days: Annotated[int, typer.Option("--ttl-days", help="Time-to-live for cached data in days.")] = 30,
) -> None:
    """
    Enriches prospects for the current campaign with website data.
    """
    campaign_name = get_campaign()
    if not campaign_name:
        print("No campaign set. Please set a campaign using `cocli campaign set <campaign_name>`.")
        raise typer.Exit(1)

    console = Console()
    setup_file_logging(f"{campaign_name}-prospects-enrich", console_level=logging.INFO, file_level=logging.DEBUG)
    ensure_enrichment_service_ready(console)
    console.print(f"Enriching prospects for campaign: [bold]{campaign_name}[/bold]")

    prospects = list(get_prospects(campaign_name, with_email=False, city=None, state=None))
    console.print(f"Found {len(prospects)} prospects to enrich.")

    async def main() -> None:
        async with httpx.AsyncClient() as client:
            tasks = []
            for prospect in prospects:
                if prospect.domain:
                    tasks.append(enrich_prospect(client, prospect, force, ttl_days, console))
            await asyncio.gather(*tasks)

    asyncio.run(main())

@app.command("tag-from-csv")
def tag_prospects_from_csv() -> None:
    """
    Updates company tags based on the prospects.csv file for the current campaign.
    This is a recovery tool to tag prospects that were imported without a campaign tag.
    """
    campaign_name = get_campaign()
    if not campaign_name:
        print("No campaign set. Please set a campaign using `cocli campaign set <campaign_name>`.")
        raise typer.Exit(1)

    console = Console()
    console.print(f"Tagging prospects from CSV for campaign: [bold]{campaign_name}[/bold]")

    prospects_csv_path = get_scraped_data_dir() / campaign_name / "prospects" / "prospects.csv"
    if not prospects_csv_path.exists():
        console.print(f"[bold red]Prospects CSV not found at: {prospects_csv_path}[/bold red]")
        raise typer.Exit(code=1)

    companies_dir = get_companies_dir()
    updated_count = 0
    with open(prospects_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain = row.get('Domain')
            if not domain:
                continue

            slug = slugify(domain)
            company_dir = companies_dir / slug
            if company_dir.is_dir():
                tags_path = company_dir / "tags.lst"
                tags = []
                if tags_path.exists():
                    with open(tags_path, 'r') as tags_file:
                        tags = [line.strip() for line in tags_file.readlines()]
                
                if campaign_name not in tags:
                    tags.append(campaign_name)
                    with open(tags_path, 'w') as tags_file:
                        tags_file.write("\n".join(tags))
                    updated_count += 1
                    console.print(f"Tagged {domain} with campaign '{campaign_name}'")

    console.print(f"[bold green]Tagging complete. Updated {updated_count} companies.[/bold green]")
