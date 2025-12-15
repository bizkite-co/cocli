import typer
import os
from rich.console import Console

from ..core.config import get_context, get_campaign

app = typer.Typer()
console = Console()

@app.command()
def status() -> None:
    """
    Displays the current status of the cocli environment, including context, campaign, and scrape strategy.
    """
    console.rule("[bold blue]Cocli Environment Status[/bold blue]")

    # Context
    context_filter = get_context()
    if context_filter:
        console.print(f"Current Context: [bold green]{context_filter}[/]")
    else:
        console.print("Current Context: [dim]None[/dim]")

    # Campaign
    campaign_name = get_campaign()
    if campaign_name:
        console.print(f"Current Campaign: [bold green]{campaign_name}[/]")
    else:
        console.print("Current Campaign: [dim]None[/dim]")

    console.print("")
    console.rule("[bold blue]Scrape Strategy[/bold blue]")

    # Scrape Strategy Detection
    is_fargate = os.getenv("COCLI_RUNNING_IN_FARGATE") == "true"
    aws_profile = os.getenv("AWS_PROFILE")
    local_dev = os.getenv("LOCAL_DEV")
    
    strategy = "Unknown"
    details = []

    if is_fargate:
        strategy = "Cloud / Fargate"
        details.append("Running inside AWS Fargate container")
        details.append("Using IAM Task Role for permissions")
    elif local_dev:
        strategy = "Local Docker (Hybrid)"
        details.append("Running in local Docker container")
        if aws_profile:
             details.append(f"Using AWS Profile: [cyan]{aws_profile}[/cyan]")
    else:
        strategy = "Local Host"
        details.append("Running directly on host machine")
        if aws_profile:
             details.append(f"Using AWS Profile: [cyan]{aws_profile}[/cyan]")
        else:
             details.append("Using default AWS credentials chain")

    console.print(f"Current Strategy: [bold yellow]{strategy}[/bold yellow]")
    for detail in details:
        console.print(f"  - {detail}")

    # Queue Config
    queue_url = os.getenv("COCLI_ENRICHMENT_QUEUE_URL")
    if queue_url:
        console.print(f"Enrichment Queue: [dim]{queue_url}[/dim]")

