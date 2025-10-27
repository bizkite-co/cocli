
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ..models.campaign import Campaign

def _render_campaign_details(campaign: Campaign) -> Panel:
    """Renders campaign details."""
    output = ""

    for key, value in campaign.model_dump().items():
        if value is None or key == "name":
            continue

        key_str = key.replace('_', ' ').title()
        output += f"- {key_str}: {value}\n"

    return Panel(Markdown(output), title="Campaign Details", border_style="green")

def display_campaign_view(console: Console, campaign: Campaign):
    console.clear()

    if not campaign.name:
        console.print("[bold red]Error: Campaign name is missing.[/]")
        return

    # Render components
    details_panel = _render_campaign_details(campaign)

    # Display layout
    console.print(details_panel)

