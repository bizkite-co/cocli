import typer
import json
import logging
import math
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from typing_extensions import Annotated
from rich.console import Console
from ...core.config import get_campaign_dir, get_campaign
from ...core.scrape_index import ScrapeIndex
from ...core.text_utils import slugify
from ...renderers.kml import render_kml_for_campaign
import toml

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)

@app.command(name="visualize-coverage")
def visualize_coverage(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign to visualize. If not provided, uses the current campaign context."),
) -> None:
    """
    Generates KML files to visualize the scraped areas for a campaign.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        logger.error("Error: No campaign name provided and no campaign context is set.")
        raise typer.Exit(code=1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign directory not found for {campaign_name}")
        raise typer.Exit(code=1)

    export_dir = campaign_dir / "exports"
    export_dir.mkdir(exist_ok=True)

    config_path = campaign_dir / "config.toml"
    with open(config_path, "r") as f:
        config = toml.load(f)
    
    search_phrases = config.get("prospecting", {}).get("queries", [])
    scrape_index = ScrapeIndex()
    scraped_areas = scrape_index.get_all_areas_for_phrases(search_phrases)

    if not scraped_areas:
        console.print("[yellow]No scraped areas found.[/yellow]")
        return

    # Group and Generate KMLs
    # (Aggregated logic truncated for brevity, same as in original campaign.py)
    # ... logic for coverage_{phrase}.kml and coverage_grid_aggregated.kml ...
    # Since I'm decomposing, I'll include the full logic here for completeness as it was in the source.

    # Group areas by phrase
    areas_by_phrase: Dict[str, List[Any]] = {}
    for area in scraped_areas:
        if area.phrase not in areas_by_phrase:
            areas_by_phrase[area.phrase] = []
        areas_by_phrase[area.phrase].append(area)

    phrases = sorted(list({area.phrase for area in scraped_areas}))
    colors = ["ff0000ff", "ff00ff00", "ffff0000", "ff00ffff", "ffff00ff", "ffffff00"]
    phrase_colors = {phrase: colors[i % len(colors)] for i, phrase in enumerate(phrases)}

    for phrase, areas in areas_by_phrase.items():
        kml_placemarks = []
        for area in areas:
            coordinates = (
                f"{area.lon_min},{area.lat_min},0 "
                f"{area.lon_max},{area.lat_min},0 "
                f"{area.lon_max},{area.lat_max},0 "
                f"{area.lon_min},{area.lat_max},0 "
                f"{area.lon_min},{area.lat_min},0"
            )
            color = phrase_colors.get(phrase, 'ffffffff')
            placemark = f'''        <Placemark>
                <name>{phrase}</name>
                <Style><LineStyle><width>0</width></LineStyle><PolyStyle><color>80{color[2:]}</color></PolyStyle></Style>
                <Polygon><outerBoundaryIs><LinearRing><coordinates>{coordinates}</coordinates></LinearRing></outerBoundaryIs></Polygon>
            </Placemark>'''
            kml_placemarks.append(placemark)

        kml_body = "\n".join(kml_placemarks)
        kml_content = f'''<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>{kml_body}</Document></kml>'''
        with open(export_dir / f"coverage_{slugify(phrase)}.kml", 'w') as f:
            f.write(kml_content)

    # Aggregated Grid
    aggregated_tiles: Dict[str, Dict[str, Any]] = {}
    for area in scraped_areas:
        # Use center point for more robust grid alignment
        # Viewports are centered on tiles, so bottom edge might bleed into previous tile
        center_lat = (area.lat_min + area.lat_max) / 2
        center_lon = (area.lon_min + area.lon_max) / 2
        
        # Round to 0.1 degree grid
        grid_lat = math.floor(round(center_lat, 6) * 10) / 10.0
        grid_lon = math.floor(round(center_lon, 6) * 10) / 10.0
        tile_id = f"{grid_lat:.1f}_{grid_lon:.1f}"
        
        if tile_id not in aggregated_tiles:
            aggregated_tiles[tile_id] = {
                "lat": grid_lat, 
                "lon": grid_lon, 
                "total_items": 0,
                "phrases": {}
            }
        
        aggregated_tiles[tile_id]["total_items"] += area.items_found
        if area.phrase not in aggregated_tiles[tile_id]["phrases"]:
            aggregated_tiles[tile_id]["phrases"][area.phrase] = 0
        aggregated_tiles[tile_id]["phrases"][area.phrase] += area.items_found

    agg_placemarks = []
    for tile_id, data in aggregated_tiles.items():
        lat_min, lon_min = data["lat"], data["lon"]
        lat_max, lon_max = lat_min + 0.1, lon_min + 0.1
        coordinates = f"{lon_min},{lat_min},0 {lon_max},{lat_min},0 {lon_max},{lat_max},0 {lon_min},{lat_max},0 {lon_min},{lat_min},0"
        
        # Build description table
        desc_parts = [
            f"<b>Tile: {tile_id}</b><br><br>",
            "<table border='1' cellspacing='0' cellpadding='3'>",
            "<tr><th align='left'>Search Phrase</th><th align='right'>Found</th></tr>"
        ]
        
        # Sort phrases by count descending
        sorted_phrases = sorted(data["phrases"].items(), key=lambda x: x[1], reverse=True)
        for phrase, count in sorted_phrases:
            desc_parts.append(f"<tr><td>{phrase}</td><td align='right'>{count}</td></tr>")
        
        desc_parts.append(f"<tr><td><b>Total</b></td><td align='right'><b>{data['total_items']}</b></td></tr>")
        desc_parts.append("</table>")
        description = "".join(desc_parts)

        # Color: Green if items found, Grey if zero
        color = "ff00ff00" if data["total_items"] > 0 else "ff808080"
        
        placemark = f'''        <Placemark>
            <name>{tile_id}</name>
            <description><![CDATA[{description}]]></description>
            <Style>
                <LineStyle><width>0</width></LineStyle>
                <PolyStyle><color>40{color[2:]}</color></PolyStyle>
            </Style>
            <Polygon>
                <outerBoundaryIs><LinearRing><coordinates>{coordinates}</coordinates></LinearRing></outerBoundaryIs>
            </Polygon>
        </Placemark>'''
        agg_placemarks.append(placemark)

    agg_body = "\n".join(agg_placemarks)
    with open(export_dir / "coverage_grid_aggregated.kml", 'w') as f:
        f.write(f'''<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>{agg_body}</Document></kml>''')

    console.print(f"[bold green]Coverage visualization complete. Files saved in: {export_dir}[/bold green]")

@app.command(name="visualize-legacy-scrapes")
def visualize_legacy_scrapes(
    campaign_name: Optional[str] = typer.Argument(None, help="Name of the campaign. If not provided, uses the current campaign context."),
) -> None:
    """
    Generates a KML file for all legacy (non-grid-aligned) scraped areas.
    """
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        return

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        return

    export_dir = campaign_dir / "exports"
    export_dir.mkdir(exist_ok=True)
    scrape_index = ScrapeIndex()
    legacy_areas = [a for a in scrape_index.get_all_scraped_areas() if not a.tile_id]

    if not legacy_areas:
        console.print("[yellow]No legacy scraped areas found.[/yellow]")
        return

    kml_placemarks = []
    for area in legacy_areas:
        coordinates = f"{area.lon_min},{area.lat_min},0 {area.lon_max},{area.lat_min},0 {area.lon_max},{area.lat_max},0 {area.lon_min},{area.lat_max},0 {area.lon_min},{area.lat_min},0"
        placemark = f'''<Placemark><name>Legacy: {area.phrase}</name><Style><LineStyle><color>ffffaa00</color></LineStyle><PolyStyle><color>20ffaa00</color></PolyStyle></Style><Polygon><outerBoundaryIs><LinearRing><coordinates>{coordinates}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>'''
        kml_placemarks.append(placemark)

    legacy_body = "\n".join(kml_placemarks)
    with open(export_dir / "legacy_scrapes.kml", 'w') as f:
        f.write(f'''<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>{legacy_body}</Document></kml>''')
    console.print("[bold green]Legacy coverage KML saved.[/bold green]")

@app.command("publish-kml")
def publish_kml(
    campaign_name: Annotated[Optional[str], typer.Argument(help="Name of the campaign. If not provided, uses the current campaign context.")] = None,
    bucket_name: Optional[str] = typer.Option(None, "--bucket", help="S3 bucket name."),
    domain: Optional[str] = typer.Option(None, "--domain", help="Public domain name for KML URLs (required by Google Maps)."),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use.")
) -> None:
    """
    Generates all KMLs (Customers, Prospects, Coverage) and uploads them to S3.
    """
    import boto3
    if campaign_name is None:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]Error: No campaign specified.[/red]")
        raise typer.Exit(code=1)

    logging.getLogger("cocli").setLevel(logging.WARNING)
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Error: Campaign dir not found for {campaign_name}[/red]")
        raise typer.Exit(code=1)

    # Load Config for defaults
    config_path = campaign_dir / "config.toml"
    config: Dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            config = toml.load(f)

    # Resolve Profile
    aws_config = config.get("aws", {})
    if not profile:
        profile = aws_config.get("profile") or aws_config.get("aws-profile") or config.get("aws-profile")

    if not profile:
        console.print("[red]Error: AWS profile required (--profile or '[aws] profile' in config.toml).[/red]")
        raise typer.Exit(code=1)

    # Resolve Domain & Bucket
    hosted_zone_domain = aws_config.get("hosted-zone-domain") or config.get("hosted-zone-domain")

    if not domain:
        if hosted_zone_domain:
            domain = f"cocli.{hosted_zone_domain}"
        else:
            console.print("[red]Error: Domain required (--domain or config 'hosted-zone-domain').[/red]")
            raise typer.Exit(code=1)

    if not bucket_name:
        if hosted_zone_domain:
            bucket_slug = str(hosted_zone_domain).replace(".", "-")
            bucket_name = f"cocli-web-assets-{bucket_slug}"
        else:
             console.print("[red]Error: Bucket required (--bucket or derived from config 'hosted-zone-domain').[/red]")
             raise typer.Exit(code=1)

    # 1. Generate KMLs via subprocess
    console.print("[dim]Generating KML files...[/dim]")
    try:
        subprocess.run(["cocli", "campaign", "set", campaign_name], check=True, capture_output=True)
        subprocess.run(["cocli", "campaign", "generate-grid"], check=True, capture_output=True)
        subprocess.run(["cocli", "campaign", "visualize-coverage", campaign_name], check=True, capture_output=True)
        subprocess.run(["cocli", "campaign", "visualize-legacy-scrapes", campaign_name], check=True, capture_output=True)
        subprocess.run(["cocli", "render-prospects-kml", campaign_name], check=True, capture_output=True)
        subprocess.run(["cocli", "render", "kml", campaign_name], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error generating KMLs: {e}[/bold red]")
        raise typer.Exit(code=1)

    # 2. Upload to S3
    files_to_upload = [
        (campaign_dir / "exports" / "coverage_grid_aggregated.kml", f"kml/{campaign_name}_aggregated.kml"),
        (campaign_dir / "exports" / "target-areas.kml", f"kml/{campaign_name}_targets.kml"),
        (campaign_dir / "exports" / "legacy_scrapes.kml", f"kml/{campaign_name}_legacy.kml"),
        (campaign_dir / f"{campaign_name}_prospects.kml", f"kml/{campaign_name}_prospects.kml"),
        (campaign_dir / f"{campaign_name}_customers.kml", f"kml/{campaign_name}_customers.kml"), 
    ]

    session = boto3.Session(profile_name=profile)
    s3 = session.client("s3")

    for local_path, remote_key in files_to_upload:
        if local_path.exists():
            s3.upload_file(str(local_path), bucket_name, remote_key, ExtraArgs={'ContentType': 'application/vnd.google-earth.kml+xml'})
            console.print(f"[green]✓ Uploaded {remote_key}[/green]")

    # 3. layers.json
    layers = [
        {"name": "Target Areas", "url": f"https://{domain}/kml/{campaign_name}_targets.kml", "default": True},
        {"name": "Scraped Areas", "url": f"https://{domain}/kml/{campaign_name}_aggregated.kml", "default": True},
        {"name": "Legacy Scrapes", "url": f"https://{domain}/kml/{campaign_name}_legacy.kml", "default": False},
        {"name": "Prospects", "url": f"https://{domain}/kml/{campaign_name}_prospects.kml", "default": True},
        {"name": "Customers", "url": f"https://{domain}/kml/{campaign_name}_customers.kml", "default": True}
    ]
    s3.put_object(Bucket=bucket_name, Key="kml/layers.json", Body=json.dumps(layers, indent=2), ContentType="application/json")
    console.print("[green]Published layers.json[/green]")

@app.command("upload-kml-coverage")
def upload_kml_coverage_for_turboship(
    campaign_name: str = typer.Argument("turboship", help="Name of the campaign."),
    turboship_kml_exports_path: Path = typer.Option("../turboheatweldingtools/turboship/data/kml-exports", "--turboship-kml-exports-path"),
    kml_filename: str = typer.Option("turboship_coverage.kml", "--filename"),
    kml_type: str = typer.Option("customers", "--type")
) -> None:
    """
    Legacy command for manual placement into turboship repo.
    """
    resolved_exports_dir = (Path.cwd() / turboship_kml_exports_path).resolve()
    resolved_exports_dir.mkdir(parents=True, exist_ok=True)
    
    if not campaign_name:
        raise typer.Exit(code=1)

    campaign_data_dir = get_campaign_dir(campaign_name)
    if not campaign_data_dir:
        raise typer.Exit(code=1)

    if kml_type == "grid": 
        source_path = campaign_data_dir / "exports" / "target-areas.kml"
    elif kml_type == "result-grid": 
        source_path = campaign_data_dir / "exports" / "coverage_grid_aggregated.kml"
    else:
        render_kml_for_campaign(campaign_name, output_dir=resolved_exports_dir)
        source_path = resolved_exports_dir / f"{campaign_name}_customers.kml"

    final_kml_path = resolved_exports_dir / kml_filename
    if source_path.exists():
        shutil.copy(str(source_path), str(final_kml_path))
        console.print(f"[green]KML placed at {final_kml_path}[/green]")
