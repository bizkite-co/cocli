import typer
from typing import Optional
from rich.console import Console
from cocli.core.infrastructure.rpi import deploy_rpi_credentials
from cocli.core.config import get_campaign, load_campaign_config

app = typer.Typer(help="Manage cocli infrastructure (Raspberry Pis, AWS).")
console = Console()

@app.command()
def deploy_creds(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name to use for profile resolution."),
    host: Optional[str] = typer.Option(None, "--host", help="Specific RPi host to deploy to."),
    user: str = typer.Option("mstouffer", "--user", "-u", help="SSH user for the RPi.")
) -> None:
    """
    Deploys AWS credentials for the active campaign to Raspberry Pi cluster members.
    """
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[bold red]Error:[/bold red] No campaign specified and no active context.")
        raise typer.Exit(1)

    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    profile = aws_config.get("profile") or aws_config.get("aws_profile")

    if not profile:
        console.print(f"[bold red]Error:[/bold red] No AWS profile configured for campaign '{campaign_name}'.")
        raise typer.Exit(1)

    # Determine hosts
    hosts = [host] if host else ["octoprint.local", "cocli5x0.local"]
    
    success = True
    for h in hosts:
        if not deploy_rpi_credentials(profile, h, user):
            success = False
    
    if not success:
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
