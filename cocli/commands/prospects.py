
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
from playwright.async_api import async_playwright, Browser

from cocli.models.company import Company
from cocli.models.hubspot import HubspotContactCsv
from cocli.core.config import get_campaign, get_campaigns_dir, get_companies_dir, get_enrichment_service_url
from cocli.core.queue.factory import get_queue_manager
from cocli.models.queue import QueueMessage # Added import
from cocli.models.website import Website
from cocli.compilers.website_compiler import WebsiteCompiler
from cocli.core.text_utils import slugify
from cocli.core.enrichment_service_utils import ensure_enrichment_service_ready
from cocli.core.logging_config import setup_file_logging
from cocli.core.enrichment import enrich_company_website


app = typer.Typer(no_args_is_help=True)

logger = logging.getLogger(__name__)
console = Console() # Instantiate console globally


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


async def enrich_prospect_docker(client: httpx.AsyncClient, prospect: Company, force: bool, ttl_days: int, console: Console) -> None:
    logger.info(f"Attempting to enrich domain: {prospect.domain} for company: {prospect.name}")
    try:
        logger.debug(f"Sending enrichment request for domain: {prospect.domain}")
        enrichment_service_url = get_enrichment_service_url()
        response = await client.post(
            f"{enrichment_service_url}/enrich",
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


async def enrich_prospect_local(
    prospect: Company,
    force: bool,
    ttl_days: int,
    console: Console,
    browser: Browser,
    semaphore: asyncio.Semaphore,
) -> None:
    """Enriches a single prospect locally using Playwright."""
    async with semaphore:
        logger.info(f"Attempting to enrich domain: {prospect.domain} for company: {prospect.name}")
        try:
            website_data = await enrich_company_website(
                browser=browser,
                company=prospect,
                force=force,
                ttl_days=ttl_days,
                debug=False,  # Assuming debug is false for batch processing
            )
            logger.debug(f"Received website_data for {prospect.domain}: {website_data}")

            if website_data and website_data.email:
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
        except Exception as e:
            logger.error(f"Unexpected Error enriching {prospect.name}: {e}", exc_info=True)
            console.print(f"  -> Error enriching {prospect.name}: {e}")


@app.command("enrich")
def enrich_prospects_command(
    force: Annotated[bool, typer.Option("--force", "-f", help="Force re-enrichment even if fresh data exists.")] = False,
    ttl_days: Annotated[int, typer.Option("--ttl-days", help="Time-to-live for cached data in days.")] = 30,
    runner: Annotated[str, typer.Option(help="Choose the execution runner.")] = "docker",
    workers: Annotated[int, typer.Option(help="Number of concurrent workers for local runner.")] = 4,
) -> None:
    """
    Enriches prospects for the current campaign with website data.

    You can choose between two runners:
    - `docker`: Uses the enrichment service running in a Docker container. (Default)
    - `local`: Runs the enrichment process locally using Playwright.
    """
    campaign_name = get_campaign()
    if not campaign_name:
        print("No campaign set. Please set a campaign using `cocli campaign set <campaign_name>`.")
        raise typer.Exit(1)

    console = Console()
    setup_file_logging(f"{campaign_name}-prospects-enrich", console_level=logging.INFO, file_level=logging.DEBUG)

    prospects = list(get_prospects(campaign_name, with_email=False, city=None, state=None))
    console.print(f"Found {len(prospects)} prospects to enrich using {runner} runner.")

    async def main_docker() -> None:
        ensure_enrichment_service_ready(console)
        console.print(f"Enriching prospects for campaign: [bold]{campaign_name}[/bold]")
        async with httpx.AsyncClient() as client:
            tasks = []
            for prospect in prospects:
                if prospect.domain:
                    tasks.append(enrich_prospect_docker(client, prospect, force, ttl_days, console))
            await asyncio.gather(*tasks)

    async def main_local() -> None:
        console.print(f"Enriching prospects for campaign: [bold]{campaign_name}[/bold] with {workers} workers.")
        semaphore = asyncio.Semaphore(workers)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                tasks = []
                for prospect in prospects:
                    if prospect.domain:
                        tasks.append(
                            enrich_prospect_local(
                                prospect=prospect,
                                force=force,
                                ttl_days=ttl_days,
                                console=console,
                                browser=browser,
                                semaphore=semaphore,
                            )
                        )
                await asyncio.gather(*tasks)
            finally:
                await browser.close()

    if runner == "docker":
        asyncio.run(main_docker())
    elif runner == "local":
        asyncio.run(main_local())
    else:
        console.print(f"[bold red]Invalid runner: {runner}. Please choose 'docker' or 'local'.[/bold red]")
        raise typer.Exit(1)


@app.command("enrich-from-queue")
def enrich_from_queue(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign. If not provided, uses current context."),
    runner: Annotated[str, typer.Option(help="Choose the execution runner.")] = "docker",
    batch_size: int = typer.Option(5, help="Number of messages to poll at once."),
    cloud_queue: bool = typer.Option(False, "--cloud-queue", help="Use the cloud SQS queue instead of local file queue."),
) -> None:
    """
    Consumes enrichment tasks from the campaign's queue.
    """
    console = Console() # Instantiate console at the beginning of the function
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]No campaign set. Please provide a campaign name.[/bold red]")
        raise typer.Exit(1)

    queue_manager = get_queue_manager(f"{campaign_name}_enrichment", use_cloud=cloud_queue)
    if hasattr(queue_manager, 'queue_url'):
        console.print(f"[blue]Using Queue URL: {queue_manager.queue_url}[/blue]") # Debug logging
    console.print(f"[bold blue]Starting Enrichment Consumer for '{campaign_name}' using {runner}...[/bold blue]")

    # Shared state for circuit breaker
    circuit_state = {"consecutive_errors": 0}
    MAX_CONSECUTIVE_ERRORS = 10 # Allow some failures, but stop if systematic

    async def process_message_docker(client: httpx.AsyncClient, msg: QueueMessage) -> bool:
        """Returns True if successful (even if no email found), False if error/exception."""
        try:
            enrichment_service_url = get_enrichment_service_url()
            target_url = f"{enrichment_service_url}/enrich"
            
            response = await client.post(
                target_url,
                json={
                    "domain": msg.domain,
                    "force": msg.force_refresh,
                    "ttl_days": msg.ttl_days,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            response_json = response.json()
            
            if response_json:
                website_data = Website(**response_json)
                
                # Create Company Skeleton if needed
                company_dir = get_companies_dir() / msg.company_slug
                if not (company_dir / "_index.md").exists():
                    # Check if the directory exists but is empty or corrupted?
                    # Just proceed with creation
                    company_dir.mkdir(parents=True, exist_ok=True)
                    with open(company_dir / "_index.md", "w") as f:
                        f.write("---\n")
                        yaml.dump({"name": msg.domain, "domain": msg.domain}, f)
                        f.write("---\n")
                        console.print(f"[yellow]Created skeleton company for {msg.company_slug}[/yellow]")

                # ALWAYS Save result (even if email is null) to mark as enriched
                enrichment_dir = company_dir / "enrichments"
                enrichment_dir.mkdir(parents=True, exist_ok=True)
                with open(enrichment_dir / "website.md", "w") as f:
                    f.write("---")
                    yaml.dump(website_data.model_dump(exclude_none=True), f)
                    f.write("---")
                
                compiler = WebsiteCompiler()
                compiler.compile(company_dir)

                if website_data.email:
                    console.print(f"[green]Found email for {msg.domain}: {website_data.email}[/green]")
                else:
                    console.print(f"[dim]No email for {msg.domain} (Saved result)[/dim]")
                
                queue_manager.ack(msg)
                return True
            else:
                console.print(f"[yellow]Empty response for {msg.domain}[/yellow]")
                queue_manager.ack(msg) # Treat empty as success (server responded)
                return True

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 404:
                console.print(f"[yellow]Service returned 404 (Not Found/Scrape Fail) for {msg.domain}. Saving empty result.[/yellow]")
                
                company_dir = get_companies_dir() / msg.company_slug
                if not (company_dir / "_index.md").exists():
                    company_dir.mkdir(parents=True, exist_ok=True)
                    with open(company_dir / "_index.md", "w") as f:
                        f.write("---\n")
                        yaml.dump({"name": msg.domain, "domain": msg.domain}, f)
                        f.write("---\n")

                enrichment_dir = company_dir / "enrichments"
                enrichment_dir.mkdir(parents=True, exist_ok=True)
                with open(enrichment_dir / "website.md", "w") as f:
                    f.write("---")
                    yaml.dump({"domain": msg.domain, "error": f"Service returned {status}"}, f)
                    f.write("---")
                
                compiler = WebsiteCompiler()
                compiler.compile(company_dir)
                
                queue_manager.ack(msg)
                return True
            
            elif status == 500:
                # For 500s, Nack with is_http_500 flag. If it exceeds threshold, it will be moved to failed.
                console.print(f"[bold red]HTTP Error 500 for {msg.domain} at {e.request.url}. Retrying.[/bold red]")
                queue_manager.nack(msg, is_http_500=True) # Pass the flag
                return False
            else:
                # Other HTTP errors (401, 403, etc.) - Nack
                console.print(f"[bold red]HTTP Error {status} for {msg.domain} at {e.request.url}. Retrying.[/bold red]")
                queue_manager.nack(msg)
                return False
        except Exception as e:
            console.print(f"[bold red]Error processing {msg.domain}: {e}[/bold red]")
            queue_manager.nack(msg)
            return False

    async def consumer_loop_docker() -> None:
        ensure_enrichment_service_ready(console)
        async with httpx.AsyncClient() as client:
            while True:
                if circuit_state["consecutive_errors"] >= MAX_CONSECUTIVE_ERRORS:
                    console.print(f"[bold red]Circuit Breaker Tripped! {MAX_CONSECUTIVE_ERRORS} consecutive errors. Stopping.[/bold red]")
                    break

                messages = queue_manager.poll(batch_size=batch_size)
                if not messages:
                    console.print("[dim]Queue empty. Waiting...[/dim]")
                    await asyncio.sleep(5)
                    continue
                
                console.print(f"Processing batch of {len(messages)}...")
                tasks = [process_message_docker(client, msg) for msg in messages]
                results = await asyncio.gather(*tasks)
                
                # Update circuit breaker
                failure_count = results.count(False)
                success_count = results.count(True)
                
                if failure_count == len(messages):
                    circuit_state["consecutive_errors"] += failure_count
                else:
                    # If at least one succeeded, reset (or reduce) the counter?
                    # Strict mode: reset only if ALL succeed? 
                    # Lenient mode: reset if ANY succeed.
                    if success_count > 0:
                        circuit_state["consecutive_errors"] = 0
                    else:
                        circuit_state["consecutive_errors"] += failure_count

    if runner == "docker":
        try:
            asyncio.run(consumer_loop_docker())
        except KeyboardInterrupt:
            console.print("[bold yellow]Consumer stopped by user.[/bold yellow]")
    else:
        console.print("[bold red]Only 'docker' runner is implemented for this command currently.[/bold red]")


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

    from ..core.prospects_csv_manager import ProspectsCSVManager
    manager = ProspectsCSVManager(campaign_name)

    if not manager.prospects_csv_path.exists():
        console.print(f"[bold red]Prospects CSV not found at: {manager.prospects_csv_path}[/bold red]")
        raise typer.Exit(code=1)

    companies_dir = get_companies_dir()
    updated_count = 0
    
    prospects = manager.read_all_prospects()
    
    for prospect in prospects:
        domain = prospect.Domain
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

