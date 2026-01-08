import typer
import subprocess
import toml
import logging
import csv
from typing import Optional, List
from rich.console import Console
from typing_extensions import Annotated

from ...core.config import get_campaign_dir, get_cocli_base_dir, get_all_campaign_dirs, get_editor_command, get_campaign, set_campaign
from ...core.geocoding import get_coordinates_from_city_state, get_coordinates_from_address
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

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Error: Campaign directory not found for {campaign_name}[/bold red]")
        raise typer.Exit(1)

    config_path = campaign_dir / "config.toml"
    
    with open(config_path, "r") as f:
        config = toml.load(f)
    
    queries = config.setdefault("prospecting", {}).get("queries", [])
    if query not in queries:
        queries.append(query)
        queries.sort()
        config["prospecting"]["queries"] = queries
        with open(config_path, "w") as f:
            toml.dump(config, f)
        console.print(f"[green]Added query:[/green] {query}")
    else:
        console.print(f"[yellow]Query already exists:[/yellow] {query}")

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

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Error: Campaign directory not found for {campaign_name}[/bold red]")
        raise typer.Exit(1)

    config_path = campaign_dir / "config.toml"
    
    with open(config_path, "r") as f:
        config = toml.load(f)
    
    queries = config.get("prospecting", {}).get("queries", [])
    if query in queries:
        queries.remove(query)
        config["prospecting"]["queries"] = queries
        with open(config_path, "w") as f:
            toml.dump(config, f)
        console.print(f"[green]Removed query:[/green] {query}")
    else:
        console.print(f"[yellow]Query not found:[/yellow] {query}")

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

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Error: Campaign directory not found for {campaign_name}[/bold red]")
        raise typer.Exit(1)

    config_path = campaign_dir / "config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)

    target_csv = config.get("prospecting", {}).get("target-locations-csv")
    if target_csv:
        csv_path = campaign_dir / target_csv
        rows = []
        exists = False
        fieldnames: List[str] = ["name", "beds", "lat", "lon", "city", "state", "csv_name", "saturation_score", "company_slug"]
        
        if csv_path.exists():
            with open(csv_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames:
                    fieldnames = list(reader.fieldnames)
                for row in reader:
                    if row.get("name") == location or row.get("city") == location:
                        exists = True
                    rows.append(row)
        
        if not exists:
            new_row = {fn: "" for fn in fieldnames}
            # Try to be smart: if it has a comma, maybe it's "City, ST"
            if "," in location:
                city, state = [part.strip() for part in location.split(",", 1)]
                new_row["city"] = city
                new_row["state"] = state
                new_row["name"] = location
                
                # Proactive geocoding
                coords = get_coordinates_from_city_state(location)
                if coords:
                    new_row["lat"] = str(coords["latitude"])
                    new_row["lon"] = str(coords["longitude"])
                    console.print(f"[dim]Geocoded {location}: {new_row['lat']}, {new_row['lon']}[/dim]")
            else:
                new_row["name"] = location
                new_row["city"] = location
                
                # Proactive geocoding
                coords = get_coordinates_from_address(location)
                if coords:
                    new_row["lat"] = str(coords["latitude"])
                    new_row["lon"] = str(coords["longitude"])
                    console.print(f"[dim]Geocoded {location}: {new_row['lat']}, {new_row['lon']}[/dim]")
            
            rows.append(new_row)
            # Sort by name
            rows.sort(key=lambda x: x.get("name") or x.get("city") or "")
            
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            console.print(f"[green]Added location to CSV:[/green] {location}")
        else:
            console.print(f"[yellow]Location already exists in CSV:[/yellow] {location}")
    else:
        # Fallback to config.toml locations list
        locations = config.setdefault("prospecting", {}).get("locations", [])
        if location not in locations:
            locations.append(location)
            locations.sort()
            config["prospecting"]["locations"] = locations
            with open(config_path, "w") as f:
                toml.dump(config, f)
            console.print(f"[green]Added location to config:[/green] {location}")
        else:
            console.print(f"[yellow]Location already exists in config:[/yellow] {location}")

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

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Error: Campaign directory not found for {campaign_name}[/bold red]")
        raise typer.Exit(1)

    config_path = campaign_dir / "config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)

    target_csv = config.get("prospecting", {}).get("target-locations-csv")
    if not target_csv:
        console.print("[yellow]No target-locations-csv configured for this campaign.[/yellow]")
        return

    csv_path = campaign_dir / target_csv
    if not csv_path.exists():
        console.print(f"[red]CSV file not found at {csv_path}[/red]")
        return

    rows = []
    updated_count = 0
    fieldnames = []
    
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        for row in reader:
            if not row.get("lat") or not row.get("lon"):
                name = row.get("name") or row.get("city")
                if name:
                    console.print(f"Geocoding: [bold cyan]{name}[/bold cyan]...")
                    coords = None
                    if "," in name:
                        coords = get_coordinates_from_city_state(name)
                    else:
                        coords = get_coordinates_from_address(name)
                    
                    if coords:
                        row["lat"] = str(coords["latitude"])
                        row["lon"] = str(coords["longitude"])
                        updated_count += 1
                        console.print(f"  [green]Found: {row['lat']}, {row['lon']}[/green]")
                    else:
                        console.print(f"  [yellow]Could not geocode.[/yellow]")
            rows.append(row)

    if updated_count > 0:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        console.print(f"[bold green]Successfully updated {updated_count} locations in {target_csv}[/bold green]")
    else:
        console.print("[yellow]No missing geocoordinates found.[/yellow]")

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

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[bold red]Error: Campaign directory not found for {campaign_name}[/bold red]")
        raise typer.Exit(1)

    config_path = campaign_dir / "config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)

    target_csv = config.get("prospecting", {}).get("target-locations-csv")
    removed = False
    
    if target_csv:
        csv_path = campaign_dir / target_csv
        if csv_path.exists():
            rows = []
            with open(csv_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames) if reader.fieldnames else []
                for row in reader:
                    if row.get("name") == location or row.get("city") == location:
                        removed = True
                        continue
                    rows.append(row)
            
            if removed and fieldnames:
                with open(csv_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                console.print(f"[green]Removed location from CSV:[/green] {location}")
    
    if not removed:
        locations = config.get("prospecting", {}).get("locations", [])
        if location in locations:
            locations.remove(location)
            config["prospecting"]["locations"] = locations
            with open(config_path, "w") as f:
                toml.dump(config, f)
            console.print(f"[green]Removed location from config:[/green] {location}")
            removed = True
            
    if not removed:
        console.print(f"[yellow]Location not found:[/yellow] {location}")