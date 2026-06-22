"""
Campaign audit tools: Hierarchical exploration of campaign data and scrape results.

Supports drill-down navigation:
  Locations → Tiles → Companies → Details
"""

import typer
from typing import Optional, List, Dict, Any, Annotated
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from cocli.core.paths import paths
from cocli.core.config import get_campaign
from cocli.models.campaigns.tiles import TileRecord

logger = __import__("logging").getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)


def _load_target_locations(campaign_name: str) -> List[Dict[str, Any]]:
    """Load target locations from USV file."""
    dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
    inputs_path = dg_queue.inputs / "target_locations.usv"

    locations = []
    if inputs_path.exists():
        with open(inputs_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    parts = line.strip().split("\x1f")
                    if len(parts) >= 3:
                        locations.append(
                            {
                                "name": parts[0],
                                "lat": float(parts[1]),
                                "lon": float(parts[2]),
                            }
                        )
    return locations


def _load_tiles(campaign_name: str) -> List[Dict[str, Any]]:
    """Load tiles from USV file."""
    dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
    tiles_path = dg_queue.path / "tiles" / "tiles.usv"

    tiles = []
    if tiles_path.exists():
        with open(tiles_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        tile = TileRecord.from_usv(line)
                        tiles.append(
                            {
                                "id": tile.id,
                                "lat": float(tile.center_lat),
                                "lon": float(tile.center_lon),
                                "zoom": tile.zoom_level,
                            }
                        )
                    except Exception:
                        pass
    return tiles


def _tiles_for_location(
    location: Dict[str, Any], tiles: List[Dict[str, Any]], radius_degrees: float = 0.2
) -> List[Dict[str, Any]]:
    """Filter tiles near a location (within radius_degrees)."""
    loc_lat, loc_lon = location["lat"], location["lon"]
    nearby = []

    for tile in tiles:
        lat_diff = abs(tile["lat"] - loc_lat)
        lon_diff = abs(tile["lon"] - loc_lon)
        if lat_diff <= radius_degrees and lon_diff <= radius_degrees:
            nearby.append(tile)

    return sorted(nearby, key=lambda t: (t["lat"], t["lon"]))


def _load_companies_for_tile(campaign_name: str, tile_id: str) -> List[Dict[str, Any]]:
    """Load companies found in a tile from the Google Maps prospects index."""
    index_path = (
        paths.campaign(campaign_name).index("google_maps_prospects").path / "active"
    )

    companies = []
    if index_path.exists():
        # Search for any company records that have this tile_id reference
        for usv_file in index_path.glob("*.usv"):
            try:
                with open(usv_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip() and tile_id in line:
                            # Parse the line - format depends on index schema
                            parts = line.strip().split("\x1f")
                            if len(parts) >= 2:
                                companies.append(
                                    {
                                        "place_id": parts[0],
                                        "name": parts[1] if len(parts) > 1 else "Unknown",
                                        "raw": line.strip(),
                                    }
                                )
            except Exception:
                pass

    return companies


@app.command(name="locations")
def list_locations(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
) -> None:
    """List all target locations for a campaign."""
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    locations = _load_target_locations(campaign_name)

    if not locations:
        console.print("[yellow]No target locations found.[/yellow]")
        return

    table = Table(title=f"Target Locations - {campaign_name}")
    table.add_column("Index", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Latitude", style="yellow")
    table.add_column("Longitude", style="yellow")

    for idx, loc in enumerate(locations):
        table.add_row(str(idx), loc["name"], f"{loc['lat']:.4f}", f"{loc['lon']:.4f}")

    console.print(table)
    console.print(f"\n[bold]Total: {len(locations)} locations[/bold]")


@app.command(name="tiles")
def list_tiles_for_location(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
    location_index: Annotated[
        Optional[int], typer.Option(help="Target location index (0-based)")
    ] = None,
) -> None:
    """List tiles for a specific location."""
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    locations = _load_target_locations(campaign_name)
    if not locations:
        console.print("[yellow]No target locations found.[/yellow]")
        return

    # Select location
    if location_index is None:
        for idx, loc in enumerate(locations[:10]):
            console.print(f"  {idx}: {loc['name']}")
        if len(locations) > 10:
            console.print(f"  ... and {len(locations) - 10} more")
        location_index = int(Prompt.ask("Select location index"))

    if location_index < 0 or location_index >= len(locations):
        console.print("[red]Invalid location index.[/red]")
        raise typer.Exit(1)

    location = locations[location_index]
    tiles = _load_tiles(campaign_name)
    nearby_tiles = _tiles_for_location(location, tiles)

    if not nearby_tiles:
        console.print(f"[yellow]No tiles found near {location['name']}[/yellow]")
        return

    table = Table(title=f"Tiles near {location['name']}")
    table.add_column("Index", style="cyan")
    table.add_column("Tile ID", style="green")
    table.add_column("Latitude", style="yellow")
    table.add_column("Longitude", style="yellow")

    for idx, tile in enumerate(nearby_tiles):
        table.add_row(str(idx), tile["id"], f"{tile['lat']:.4f}", f"{tile['lon']:.4f}")

    console.print(table)
    console.print(
        f"\n[bold]Total: {len(nearby_tiles)} tiles near {location['name']}[/bold]"
    )


@app.command(name="companies")
def list_companies_for_tile(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
    tile_id: Annotated[Optional[str], typer.Option(help="Tile ID (e.g., 25.8_-80.2)")] = None,
) -> None:
    """List companies found in a specific tile."""
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    if tile_id is None:
        tiles = _load_tiles(campaign_name)
        if not tiles:
            console.print("[yellow]No tiles found.[/yellow]")
            return

        for tile in tiles[:10]:
            console.print(f"  {tile['id']}")
        if len(tiles) > 10:
            console.print(f"  ... and {len(tiles) - 10} more")
        tile_id = Prompt.ask("Select tile ID")

    companies = _load_companies_for_tile(campaign_name, tile_id)

    if not companies:
        console.print(f"[yellow]No companies found in tile {tile_id}[/yellow]")
        return

    table = Table(title=f"Companies in Tile {tile_id}")
    table.add_column("Index", style="cyan")
    table.add_column("Place ID", style="green")
    table.add_column("Name", style="yellow")

    for idx, company in enumerate(companies[:50]):
        table.add_row(str(idx), company["place_id"], company["name"])

    console.print(table)
    if len(companies) > 50:
        console.print(f"\n[dim]Showing 50 of {len(companies)} companies[/dim]")
    console.print(f"\n[bold]Total: {len(companies)} companies[/bold]")


@app.command(name="company")
def show_company_details(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
    place_id: Annotated[Optional[str], typer.Option(help="Place ID")] = None,
) -> None:
    """Show detailed information for a company."""
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    if place_id is None:
        place_id = Prompt.ask("Enter place ID (ChIJ...)")

    # Load company data from indexes
    index_path = (
        paths.campaign(campaign_name).index("google_maps_prospects").path / "active"
    )

    found = False
    if index_path.exists():
        for usv_file in index_path.glob("*.usv"):
            try:
                with open(usv_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip() and place_id in line:
                            console.print("\n[bold green]Company Data Found[/bold green]")
                            console.print(f"[dim]Place ID:[/dim] {place_id}")
                            console.print(f"[dim]File:[/dim] {usv_file.name}")
                            console.print("\n[dim]Raw Record:[/dim]")
                            console.print(f"[cyan]{line.strip()}[/cyan]")
                            found = True
                            break
            except Exception:
                pass

    if not found:
        console.print(f"[yellow]Company not found: {place_id}[/yellow]")


@app.command(name="summary")
def show_campaign_summary(
    campaign_name: Annotated[
        Optional[str], typer.Argument(help="Campaign name")
    ] = None,
    cluster: Annotated[
        bool, typer.Option("--cluster", help="Fetch live data from PI cluster")
    ] = False,
) -> None:
    """Show overall campaign audit summary."""
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    locations = _load_target_locations(campaign_name)
    tiles = _load_tiles(campaign_name)

    dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
    mission_path = dg_queue.master
    mission_count = 0
    if mission_path.exists():
        with open(mission_path, "r") as f:
            mission_count = sum(1 for _ in f)

    console.print(f"\n[bold blue]Campaign Audit Summary: {campaign_name}[/bold blue]")
    console.print(f"[dim]{'─' * 60}[/dim]")
    console.print(f"  Target Locations: [cyan]{len(locations)}[/cyan]")
    console.print(f"  Tiles Generated: [cyan]{len(tiles)}[/cyan]")
    console.print(f"  Mission Tasks: [cyan]{mission_count}[/cyan]")

    # Count companies - check both active index and WAL (Write-Ahead Log)
    company_count = 0

    # Check active index (local hub)
    index_path = (
        paths.campaign(campaign_name).index("google_maps_prospects").path / "active"
    )
    if index_path.exists():
        for usv_file in index_path.glob("*.usv"):
            try:
                with open(usv_file, "r") as f:
                    company_count += sum(1 for _ in f)
            except Exception:
                pass

    # Check WAL (results being written)
    wal_path = (
        paths.campaign(campaign_name).index("google_maps_prospects").path / "wal"
    )
    wal_count = 0
    if wal_path.exists():
        for usv_file in wal_path.glob("*/*.usv"):
            try:
                with open(usv_file, "r") as f:
                    wal_count += sum(1 for _ in f)
            except Exception:
                pass

    total_found = company_count + wal_count
    console.print(f"  Companies Found (Local): [cyan]{company_count}[/cyan]")
    if wal_count > 0:
        console.print(f"  Companies in WAL (Active): [yellow]{wal_count}[/yellow]")
        console.print(f"  Total Found: [green]{total_found}[/green]")

    console.print(f"[dim]{'─' * 60}[/dim]\n")

    console.print("[dim]Navigate with:[/dim]")
    console.print("  cocli campaign audit locations")
    console.print("  cocli campaign audit tiles --location-index 0")
    console.print("  cocli campaign audit companies --tile-id 25.8_-80.2")
    console.print("  cocli campaign audit company --place-id ChIJ...\n")
