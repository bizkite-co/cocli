import typer
import json
import subprocess
import os
import boto3
from datetime import datetime
from typing import Optional
from pathlib import Path
from rich.console import Console
from cocli.core.config import get_campaign, get_campaign_dir
from ..application.services import ServiceContainer

app = typer.Typer(no_args_is_help=True, help="Manage web deployment.")
console = Console()

@app.command()
def deploy(
    campaign_name: Optional[str] = typer.Option(None, "--campaign-name", "--campaign", help="Campaign name. Defaults to current context."),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use. Defaults to 'aws-profile' in config.toml."),
    bucket_name: Optional[str] = typer.Option(None, "--bucket", help="S3 bucket name. Defaults to cocli-web-assets-<domain-slug>."),
    domain: Optional[str] = typer.Option(None, "--domain", help="Web domain. Defaults to cocli.<hosted-zone-domain>.")
) -> None:
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
        console.print(f"[red]Campaign directory not found for {campaign_name}[/red]")
        raise typer.Exit(1)

    config_path = campaign_dir / "config.toml"

    services = ServiceContainer(campaign_name=campaign_name)
    try:
        cfg = services.web_service.resolve_deployment_config(
            profile=profile,
            bucket_name=bucket_name,
            domain=domain,
        )
        profile = cfg["profile"]
        domain = cfg["domain"]
        bucket_name = cfg["bucket_name"]
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print("[bold blue]Deploying to:[/bold blue]")
    console.print(f"  Campaign: [cyan]{campaign_name}[/cyan]")
    console.print(f"  Domain:   [cyan]{domain}[/cyan]")
    console.print(f"  Bucket:   [cyan]{bucket_name}[/cyan]")

    source_web_dir = Path(__file__).parent.parent.parent / "cocli" / "web"
    build_dir = Path(__file__).parent.parent.parent / "build" / "web"

    # 0. Build Web Shell
    console.print("[bold blue]Building web dashboard with Eleventy...[/bold blue]")
    if source_web_dir.exists():
        try:
            # Pass CAMPAIGN and CDK outputs as env vars to eleventy
            env = os.environ.copy()
            env["CAMPAIGN"] = campaign_name
            env["AWS_PROFILE"] = profile
            
            session = boto3.Session(profile_name=profile)
            env["AWS_REGION"] = session.region_name or "us-east-1"

            # Fetch CDK outputs from CloudFormation
            env.update(services.web_service.fetch_cdk_outputs(profile=profile))

            subprocess.run(["npm", "run", "build"], cwd=source_web_dir, check=True, env=env)
            console.print("[green]Build successful.[/green]")
        except subprocess.CalledProcessError:
            console.print("[red]Error: Web build failed. Aborting deployment.[/red]")
            raise typer.Exit(1)
    else:
        console.print(f"[yellow]Source web directory {source_web_dir} not found. Skipping build.[/yellow]")

    session = boto3.Session(profile_name=profile)
    s3 = session.client("s3")

    # 1. Sync Static Assets (Shell)
    console.print(f"[bold]Syncing web shell from {build_dir} to s3://{bucket_name}...[/bold]")
    if build_dir.exists():
        for file_path in build_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(build_dir)
                if file_path.suffix == ".css":
                    content_type = "text/css"
                elif file_path.suffix == ".js":
                    content_type = "application/javascript"
                elif file_path.suffix == ".json":
                    content_type = "application/json"
                elif file_path.suffix == ".html":
                    content_type = "text/html"
                else:
                    content_type = "application/octet-stream"

                # No Cache-Control means browsers/CloudFront fall back to
                # heuristic caching (RFC 7234) and can silently serve a stale
                # shell after a deploy. Force revalidation on every load.
                s3.upload_file(
                    str(file_path),
                    bucket_name,
                    str(rel_path),
                    ExtraArgs={"ContentType": content_type, "CacheControl": "no-cache, must-revalidate"},
                )
                console.print(f"  Uploaded {rel_path}")
    else:
        console.print(f"[yellow]Build directory {build_dir} not found. Skipping shell sync.[/yellow]")

    # 2. Generate & Upload Report
    console.print(f"[bold]Generating reports for {campaign_name}...[/bold]")
    
    # 2.0 Force regeneration of the export CSV to pick up name changes
    try:
        console.print("  Regenerating export CSV...")
        # Use the absolute path to the script relative to project root
        script_path = Path(__file__).parent.parent.parent / "scripts" / "export_enriched_emails.py"
        export_env = os.environ.copy()
        export_env["AWS_PROFILE"] = profile
        subprocess.run(["uv", "run", str(script_path), campaign_name], check=True, env=export_env)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not regenerate export CSV: {e}[/yellow]")

    reports = services.web_service.get_campaign_reports()
    stats = reports["stats"]
    
    # 2a. Main Report
    report_key = f"reports/{campaign_name}.json"
    s3.put_object(Bucket=bucket_name, Key=report_key, Body=json.dumps(stats, indent=2), ContentType="application/json")
    console.print(f"  Uploaded main report to s3://{bucket_name}/{report_key}")

    # 2b. Granular Reports (for faster worker-driven updates)
    granular = {
        "exclusions.json": reports["exclusions"],
        "queries.json": reports["queries"],
        "locations.json": reports["locations"]
    }
    for filename, data in granular.items():
        key = f"reports/{filename}"
        s3.put_object(Bucket=bucket_name, Key=key, Body=json.dumps(data, indent=2), ContentType="application/json")
        console.print(f"  Uploaded {key}")

    # 2c. Upload Config to both web and data buckets
    if config_path.exists():
        # 1. Upload to Web Bucket (as config/config.toml for web viewing or as campaigns/...)
        config_key = f"campaigns/{campaign_name}/config.toml"
        s3.upload_file(str(config_path), bucket_name, config_key, ExtraArgs={"ContentType": "application/toml"})
        console.print(f"[green]Config uploaded to s3://{bucket_name}/{config_key}[/green]")
        
        # 2. Upload to Data Bucket (for workers)
        data_bucket = f"cocli-data-{campaign_name}"
        try:
            s3.upload_file(str(config_path), data_bucket, "config.toml", ExtraArgs={"ContentType": "application/toml"})
            s3.upload_file(str(config_path), data_bucket, config_key, ExtraArgs={"ContentType": "application/toml"})
            console.print(f"[green]Config uploaded to s3://{data_bucket}/config.toml (and {config_key})[/green]")
        except Exception as e:
            console.print(f"[yellow]Note: Could not upload to data bucket {data_bucket}: {e}[/yellow]")
    else:
        console.print(f"[yellow]Config file not found at {config_path}. Skipping upload.[/yellow]")

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

    # 4. Invalidate CloudFront Cache
    try:
        cf = session.client("cloudfront")
        dists = cf.list_distributions().get("DistributionList", {}).get("Items", [])
        dist_id = next((d["Id"] for d in dists if domain in d.get("Aliases", {}).get("Items", [])), None)
        
        if dist_id:
            console.print(f"[bold]Invalidating CloudFront cache for {dist_id}...[/bold]")
            cf.create_invalidation(
                DistributionId=dist_id,
                InvalidationBatch={
                    'Paths': {
                        'Quantity': 1,
                        'Items': ['/*']
                    },
                    'CallerReference': str(datetime.now().timestamp())
                }
            )
            console.print("[green]Invalidation request sent.[/green]")
    except Exception as e:
        console.print(f"[yellow]Note: Could not invalidate CloudFront cache: {e}[/yellow]")

    console.print(f"[bold green]Deployment complete! Visit https://{domain}/[/bold green]")

@app.command()
def report(
    campaign_name: Optional[str] = typer.Option(None, "--campaign-name", "--campaign", help="Campaign name. Defaults to current context."),
    output: Optional[Path] = typer.Option(None, help="Output file path (JSON). If not provided, prints JSON to stdout.")
) -> None:
    """
    Generates a JSON report for the campaign.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    services = ServiceContainer(campaign_name=campaign_name)
    stats = services.web_service.get_campaign_reports()["stats"]
    
    if output:
        with open(output, "w") as f:
            json.dump(stats, f, indent=2)
        console.print(f"[green]Report saved to {output}[/green]")
    if stats:
        console.print(json.dumps(stats, indent=2))

