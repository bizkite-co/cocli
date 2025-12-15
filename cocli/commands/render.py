
import typer
from pathlib import Path
from typing import Optional # Import Optional

from ..renderers.kml import render_kml_for_campaign

app = typer.Typer()

@app.command()
def kml(
    campaign_name: str = typer.Argument(..., help="Name of the campaign to render."),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o",
        help="Optional directory to save the KML file. Defaults to campaign data directory."
    )
) -> None:
    """
    Render a KML file for a campaign.
    """
    render_kml_for_campaign(campaign_name, output_dir)

@app.command("kml-coverage")
def kml_coverage_for_turboship(
    campaign_name: str = typer.Argument("turboship", help="Name of the campaign to render."),
    # Path to the turboship kml-exports directory
    turboship_kml_exports_path: Path = typer.Option(
        "../../turboheatweldingtools/turboship/data/kml-exports", # Default relative path
        "--turboship-kml-exports-path",
        help="Path to the turboship project's data/kml-exports directory for deploying KMLs."
    )
) -> None:
    """
    Render a KML file for the 'turboship' campaign and place it in the turboship project's
    kml-exports directory for deployment via its CDK stack.
    """
    # Resolve the path relative to the current working directory of cocli
    resolved_output_dir = Path.cwd() / turboship_kml_exports_path
    render_kml_for_campaign(campaign_name, resolved_output_dir)
