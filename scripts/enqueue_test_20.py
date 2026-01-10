import asyncio
from cocli.models.company import Company
from cocli.core.queue.factory import get_queue_manager
from cocli.models.queue import QueueMessage
from rich.console import Console

console = Console()

async def main() -> None:
    campaign_name = "turboship"
    console.print(f"Enqueuing 20 companies from [bold]{campaign_name}[/bold]...")
    
    # Get enrichment queue
    queue = get_queue_manager("enrichment", use_cloud=True, queue_type="enrichment", campaign_name=campaign_name)
    
    # Get companies
    count = 0
    for company in Company.get_all():
        if campaign_name in company.tags and company.domain:
            msg = QueueMessage(
                domain=company.domain,
                company_slug=company.slug,
                campaign_name=campaign_name,
                force_refresh=True,
                ack_token=None
            )
            queue.push(msg)
            console.print(f"Enqueued: {company.slug} ({company.domain})")
            count += 1
            if count >= 4:
                break
    
    console.print(f"[green]Successfully enqueued {count} companies.[/green]")

if __name__ == "__main__":
    asyncio.run(main())
