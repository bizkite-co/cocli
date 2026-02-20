import typer
import subprocess
import toml
import logging
from typing import Optional
from rich.console import Console
from typing_extensions import Annotated

from ...core.config import get_campaign_dir, get_cocli_base_dir, get_all_campaign_dirs, get_editor_command, get_campaign, set_campaign
from ...models.campaign import Campaign
from ...renderers.campaign_view import display_campaign_view
from ...core.campaign_workflow import CampaignWorkflow
from ...core.utils import run_fzf

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True)

@app.command()
def edit(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign to edit.")] = None
) -> None:
    """
    Edits an existing campaign's configuration.
    """
    if campaign_name is None:
        campaign_dirs = get_all_campaign_dirs()
        if not campaign_dirs:
            console.print("[bold red]No campaigns found.[/bold red]")
            raise typer.Exit(code=1)
        
        campaign_names = [d.name for d in campaign_dirs]
        fzf_input = "\n".join(campaign_names)
        selected_campaign = run_fzf(fzf_input)
        
        if not selected_campaign:
            console.print("No campaign selected.")
            raise typer.Exit(code=1)
        campaign_name = selected_campaign

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(code=1)

    config_path = campaign_dir / "config.toml"
    readme_path = campaign_dir / "README.md"

    editor_command = get_editor_command()

    if editor_command:
        files_to_edit = []
        if config_path.exists():
            files_to_edit.append(str(config_path))
        else:
            console.print(f"[bold red]Configuration file not found for campaign '{campaign_name}'.[/bold red]")

        if readme_path.exists():
            files_to_edit.append(str(readme_path))

        if not files_to_edit:
            console.print(f"[bold red]No files to edit for campaign '{campaign_name}'.[/bold red]")
            raise typer.Exit(code=1)

        command = [editor_command]
        # For vim/nvim, use -o for horizontal split
        if "vim" in editor_command or "nvim" in editor_command:
            command.append("-o")
        
        command.extend(files_to_edit)
        
        subprocess.run(command)
    else:
        if config_path.exists():
            typer.edit(filename=str(config_path))
        else:
            console.print(f"[bold red]Configuration file not found for campaign '{campaign_name}'.[/bold red]")

        if readme_path.exists():
            console.print("[yellow]To edit the README.md as well, please configure an editor in your cocli_config.toml.[/yellow]")

@app.command()
def add(
    name: Annotated[str, typer.Argument(help="The name of the campaign.")],
    company: Annotated[str, typer.Argument(help="The name of the company.")],
) -> None:
    """
    Adds a new campaign.
    """
    data_home = get_cocli_base_dir()
    try:
        Campaign.create(name, company, data_home)
        console.print(f"[green]Campaign '{name}' created successfully.[/green]")
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]An unexpected error occurred: {e}[/red]")
        raise typer.Exit(code=1)

@app.command(name="set")
def set_default_campaign(campaign_name: str = typer.Argument(..., help="The name of the campaign to set as the current context.")) -> None:
    """Sets the current campaign context."""
    from ...application.campaign_service import CampaignService
    
    try:
        service = CampaignService(campaign_name)
        service.activate()
        
        workflow = CampaignWorkflow(campaign_name)
        console.print(f"[green]Campaign context set to:[/][bold]{campaign_name}[/]")
        console.print(f"[green]Current workflow state for '{campaign_name}':[/][bold]{workflow.state}[/]")
    except Exception as e:
        console.print(f"[red]Error setting campaign: {e}[/red]")
        raise typer.Exit(code=1)

@app.command()
def unset() -> None:
    """
    Clears the current campaign context.
    """
    set_campaign(None)
    console.print("[green]Campaign context cleared.[/]")

@app.command()
def show() -> None:
    """
    Displays the current campaign context.
    """
    campaign_name = get_campaign()
    if campaign_name:
        campaign_dir = get_campaign_dir(campaign_name)
        if not campaign_dir:
            console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
            raise typer.Exit(code=1)

        config_path = campaign_dir / "config.toml"
        if not config_path.exists():
            console.print(f"[bold red]Configuration file not found for campaign '{campaign_name}'.[/bold red]")
            raise typer.Exit(code=1)

        with open(config_path, "r") as f:
            config_data = toml.load(f)
        
        # Flatten config
        flat_config = config_data.pop('campaign')
        flat_config.update(config_data)

        try:
            campaign = Campaign.model_validate(flat_config)
        except Exception as e:
            console.print(f"[bold red]Error validating campaign configuration for '{campaign_name}': {e}[/bold red]")
            raise typer.Exit(code=1)

        display_campaign_view(console, campaign)
    else:
        console.print("No campaign context is set.")

@app.command()
def status(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to show status for. If not provided, uses the current campaign context.")
) -> None:
    """
    Displays the current state of the campaign workflow.
    """
    effective_campaign_name = campaign_name
    if effective_campaign_name is None:
        effective_campaign_name = get_campaign()

    if effective_campaign_name is None:
        console.print("[bold red]Error: No campaign name provided and no campaign context is set. Please provide a campaign name or set a campaign context using 'cocli campaign set <campaign_name>'.[/bold red]")
        raise typer.Exit(code=1)

    workflow = CampaignWorkflow(effective_campaign_name)
    console.print(f"[green]Current workflow state for '{effective_campaign_name}':[/][bold]{workflow.state}[/]")

@app.command()
def add_query(
    query: Annotated[str, typer.Argument(help="The search query to add.")],
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name.")
) -> None:
    """Adds a search query to the campaign configuration."""
    if not campaign_name:
        campaign_name = get_campaign()
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    try:
        from ...application.campaign_service import CampaignService
        service = CampaignService(campaign_name)
        if service.add_query(query):
            console.print(f"[green]Added query:[/green] {query}")
        else:
            console.print(f"[yellow]Query already exists:[/yellow] {query}")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)

@app.command()
def remove_query(
    query: Annotated[str, typer.Argument(help="The search query to remove.")],
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name.")
) -> None:
    """Removes a search query from the campaign configuration."""
    if not campaign_name:
        campaign_name = get_campaign()
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    try:
        from ...application.campaign_service import CampaignService
        service = CampaignService(campaign_name)
        if service.remove_query(query):
            console.print(f"[green]Removed query:[/green] {query}")
        else:
            console.print(f"[yellow]Query not found:[/yellow] {query}")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)

@app.command()
def add_location(
    location: Annotated[str, typer.Argument(help="The location name/city to add.")],
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name.")
) -> None:
    """Adds a target location to the campaign."""
    if not campaign_name:
        campaign_name = get_campaign()
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    try:
        from ...application.campaign_service import CampaignService
        service = CampaignService(campaign_name)
        if service.add_location(location):
            console.print(f"[green]Added location:[/green] {location}")
        else:
            console.print(f"[yellow]Location already exists:[/yellow] {location}")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)

@app.command()
def remove_location(
    location: Annotated[str, typer.Argument(help="The location name/city to remove.")],
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name.")
) -> None:
    """Removes a target location from the campaign."""
    if not campaign_name:
        campaign_name = get_campaign()
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    try:
        from ...application.campaign_service import CampaignService
        service = CampaignService(campaign_name)
        if service.remove_location(location):
            console.print(f"[green]Removed location:[/green] {location}")
        else:
            console.print(f"[yellow]Location not found:[/yellow] {location}")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)

@app.command()
def geocode_locations(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign.")] = None
) -> None:
    """
    Scans the campaign's target locations CSV and fills in missing geocoordinates.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    try:
        from ...application.campaign_service import CampaignService
        service = CampaignService(campaign_name)
        updated_count = service.geocode_locations()
        
        if updated_count > 0:
            console.print(f"[bold green]Successfully updated {updated_count} locations.[/bold green]")
        else:
            console.print("[yellow]No locations were updated.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)

@app.command()
def bucket(

    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name.")

) -> None:

    """

    Displays the S3 bucket root and campaign path.

    """

    if not campaign_name:

        campaign_name = get_campaign()

    if not campaign_name:

        console.print("[bold red]Error: No campaign specified.[/bold red]")

        raise typer.Exit(1)



    campaign_dir = get_campaign_dir(campaign_name)

    if not campaign_dir:

        console.print(f"[bold red]Error: Campaign directory not found for {campaign_name}[/bold red]")

        raise typer.Exit(1)



    config_path = campaign_dir / "config.toml"

    if not config_path.exists():

        console.print(f"[bold red]Error: config.toml not found for {campaign_name}[/bold red]")

        raise typer.Exit(1)

        

    with open(config_path, "r") as f:

        config = toml.load(f)

    

    aws_config = config.get("aws", {})

    bucket_name = aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name")

    

    if bucket_name:

        console.print(f"s3://{bucket_name}/campaigns/{campaign_name}/")

    else:

        # Fallback to default pattern

        console.print(f"s3://cocli-data-{campaign_name}/campaigns/{campaign_name}/")

@app.command(name="compile-lifecycle")
def compile_lifecycle(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign.")] = None
) -> None:
    """
    Compiles the lifecycle index from local completed queues.
    Mandate: Sync 'queues/' before running.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    try:
        from ...application.campaign_service import CampaignService
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
        
        service = CampaignService(campaign_name)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("[dim]{task.fields[label]}"),
            console=console
        ) as progress:
            task = progress.add_task("Compiling lifecycle index...", total=None, label="")
            
            generator = service.compile_lifecycle_index()
            final_count = 0
            
            for update in generator:
                if isinstance(update, dict):
                    progress.update(
                        task, 
                        description=f"Compiling: {update['phase']}", 
                        total=update['total'], 
                        completed=update['current'], 
                        label=update['label']
                    )
                else:
                    final_count = update
                    
        console.print(f"[bold green]Successfully compiled lifecycle index with {final_count} records.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)

@app.command(name="restore-names")
def restore_names(
    campaign_name: Annotated[Optional[str], typer.Argument(help="The name of the campaign.")] = None,
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't save changes.")
) -> None:
    """
    Restores company names from the Google Maps index and writes provenance receipts.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified.[/bold red]")
        raise typer.Exit(1)

    try:
        from ...application.campaign_service import CampaignService
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
        
        service = CampaignService(campaign_name)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("[dim]{task.fields[slug]}"),
            console=console
        ) as progress:
            task = progress.add_task("Restoring names...", total=None, slug="")
            
            generator = service.restore_names_from_index(dry_run=dry_run)
            final_stats = {}
            
            for update in generator:
                if "total" in update:
                    progress.update(task, total=update["total"], completed=update["current"], slug=update["slug"])
                else:
                    final_stats = update
            
        if dry_run:
            console.print(f"[yellow]DRY RUN: Would restore {final_stats.get('restored', 0)} names.[/yellow]")
        else:
            console.print(f"[bold green]Successfully restored {final_stats.get('restored', 0)} names.[/bold green]")
            console.print(f"[bold green]Wrote {final_stats.get('receipts_written', 0)} provenance receipts.[/bold green]")
            
        if final_stats.get("errors", 0) > 0:
            console.print(f"[bold red]Encoutered {final_stats['errors']} errors.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)
