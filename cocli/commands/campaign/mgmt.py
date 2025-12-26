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
        print(f"Campaign '{name}' created successfully.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise typer.Exit(code=1)

@app.command(name="set")
def set_default_campaign(campaign_name: str = typer.Argument(..., help="The name of the campaign to set as the current context.")) -> None:
    """
    Sets the current campaign context.
    """
    set_campaign(campaign_name)
    workflow = CampaignWorkflow(campaign_name)
    console.print(f"[green]Campaign context set to:[/][bold]{campaign_name}[/]")
    console.print(f"[green]Current workflow state for '{campaign_name}':[/][bold]{workflow.state}[/]")

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

