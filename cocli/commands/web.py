import typer
import json
import subprocess
import boto3
from pathlib import Path
from rich.console import Console
from cocli.core.config import get_campaign, get_campaign_dir
from cocli.core.reporting import get_campaign_stats

app = typer.Typer(no_args_is_help=True, help="Manage web deployment.")
console = Console()

@app.command()
def deploy(
    campaign_name: str = typer.Option(None, help="Campaign name. Defaults to current context."),
    profile: str = typer.Option("bizkite-support", "--profile", help="AWS profile to use."),
    bucket_name: str = typer.Option("cocli-web-assets", "--bucket", help="S3 bucket name."),
    domain: str = typer.Option("cocli.turboheat.net", "--domain", help="Web domain for KML URLs.")
):
    """
    Deploys the web dashboard (shell) and campaign data (KMLs, Report) to S3.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified and no context set.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise typer.Exit(1)
        
    web_dir = Path(__file__).parent.parent.parent / "cocli" / "web" # cocli/web

    session = boto3.Session(profile_name=profile)
    s3 = session.client("s3")

    # 1. Sync Static Assets (Shell)
    console.print(f"[bold]Syncing web shell from {web_dir} to s3://{bucket_name}...[/bold]")
    if web_dir.exists():
        for file_path in web_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(web_dir)
                content_type = "text/html" if file_path.suffix == ".html" else "application/octet-stream"
                # Simple guess for other types
                if file_path.suffix == ".css":
                    content_type = "text/css"
                elif file_path.suffix == ".js":
                    content_type = "application/javascript"
                elif file_path.suffix == ".json":
                    content_type = "application/json"
                
                s3.upload_file(str(file_path), bucket_name, str(rel_path), ExtraArgs={"ContentType": content_type})
                console.print(f"  Uploaded {rel_path}")
    else:
        console.print(f"[yellow]Web directory {web_dir} not found. Skipping shell sync.[/yellow]")

    # 2. Generate & Upload Report
    console.print(f"[bold]Generating report for {campaign_name}...[/bold]")
    stats = get_campaign_stats(campaign_name)
    report_key = f"campaigns/{campaign_name}/report.json"
    s3.put_object(Bucket=bucket_name, Key=report_key, Body=json.dumps(stats, indent=2), ContentType="application/json")
    console.print(f"[green]Report uploaded to s3://{bucket_name}/{report_key}[/green]")

    # 3. Generate & Upload KMLs
    # We leverage the existing 'publish-kml' command in viz.py which generates and uploads.
    # We pass the --bucket argument to it.
    console.print(f"[bold]Publishing KMLs to s3://{bucket_name}...[/bold]")
    try:
        subprocess.run(
            ["cocli", "campaign", "publish-kml", campaign_name, "--bucket", bucket_name, "--domain", domain, "--profile", profile], 
            check=True
        )
    except subprocess.CalledProcessError:
        console.print("[red]Failed to publish KMLs.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold green]Deployment complete! Visit https://{domain}/kml-viewer.html[/bold green]")

@app.command()
def report(
    campaign_name: str = typer.Option(None, help="Campaign name. Defaults to current context."),
    output: Path = typer.Option(None, help="Output file path (JSON). If not provided, prints JSON to stdout.")
):
    """
    Generates a JSON report for the campaign.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    stats = get_campaign_stats(campaign_name)
    
    if output:
        with open(output, "w") as f:
            json.dump(stats, f, indent=2)
        console.print(f"[green]Report saved to {output}[/green]")
    else:
        print(json.dumps(stats, indent=2))
