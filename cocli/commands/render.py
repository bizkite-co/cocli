
import typer

from ..renderers.kml import render_kml_for_campaign

app = typer.Typer()

@app.command()
def kml(
    campaign_name: str = typer.Argument(..., help="Name of the campaign to render.")
):
    """
    Render a KML file for a campaign.
    """
    render_kml_for_campaign(campaign_name)
