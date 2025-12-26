import typer
from typing import Optional
from rich.console import Console
from ...core.config import get_campaign
from ...core.campaign_workflow import CampaignWorkflow

console = Console()
app = typer.Typer(no_args_is_help=True)

@app.command(name="start-workflow")
def start_workflow(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to start the workflow for. If not provided, uses the current campaign context.")
) -> None:
    """
    Starts the campaign workflow.
    """
    effective_campaign_name = campaign_name
    if effective_campaign_name is None:
        effective_campaign_name = get_campaign()

    if effective_campaign_name is None:
        console.print("[bold red]Error: No campaign name provided and no campaign context is set. Please provide a campaign name or set a campaign context using 'cocli campaign set <campaign_name>'.[/bold red]")
        raise typer.Exit(code=1)

    workflow = CampaignWorkflow(effective_campaign_name)
    if workflow.state == 'idle':
        workflow.start_import()  # type: ignore
    else:
        console.print(f"[bold yellow]Workflow for '{effective_campaign_name}' is already in state '{workflow.state}'. Cannot start from idle.[/bold yellow]")

@app.command(name="next-step")
def next_step(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to advance the workflow for. If not provided, uses the current campaign context.")
) -> None:
    """
    Advances the campaign workflow to the next logical step.
    """
    effective_campaign_name = campaign_name
    if effective_campaign_name is None:
        effective_campaign_name = get_campaign()

    if effective_campaign_name is None:
        console.print("[bold red]Error: No campaign name provided and no campaign context is set. Please provide a campaign name or set a campaign context using 'cocli campaign set <campaign_name>'.[/bold red]")
        raise typer.Exit(code=1)

    workflow = CampaignWorkflow(effective_campaign_name)
    current_state = workflow.state

    if current_state == 'idle':
        workflow.start_import()  # type: ignore
    elif current_state == 'import_customers':
        workflow.start_prospecting()  # type: ignore
    elif current_state == 'prospecting_scraping':
        workflow.finish_scraping()  # type: ignore
    elif current_state == 'prospecting_ingesting':
        workflow.finish_ingesting()  # type: ignore
    elif current_state == 'prospecting_importing':
        workflow.finish_prospecting_import()  # type: ignore
    elif current_state == 'prospecting_enriching':
        workflow.finish_enriching()  # type: ignore
    elif current_state == 'outreach':
        console.print("[bold yellow]Campaign is in outreach phase. Use specific outreach commands.[/bold yellow]")
    elif current_state == 'completed':
        console.print("[bold green]Campaign is already completed.[/bold green]")
    elif current_state == 'failed':
        console.print("[bold red]Campaign is in a failed state. Please review logs.[/bold red]")
    else:
        console.print(f"[bold yellow]No automatic next step defined for current state: {current_state}.[/bold yellow]")
