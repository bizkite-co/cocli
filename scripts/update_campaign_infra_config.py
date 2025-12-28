import typer
import boto3 # type: ignore
import toml
from typing import Optional
from rich.console import Console
from cocli.core.config import get_campaign, load_campaign_config, get_campaigns_dir

app = typer.Typer()
console = Console()

@app.command()
def update_config(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name"),
    stack_name: str = typer.Option("CdkScraperDeploymentStack", help="CloudFormation stack name")
) -> None:
    """
    Queries CloudFormation for stack outputs and updates the campaign's config.toml.
    """
    effective_campaign = campaign_name
    if not effective_campaign:
        effective_campaign = get_campaign()
    
    if not effective_campaign:
        console.print("[bold red]No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    campaign_dir = get_campaigns_dir() / effective_campaign
    config_path = campaign_dir / "config.toml"
    
    if not config_path.exists():
        console.print(f"[bold red]Config file not found at {config_path}[/bold red]")
        raise typer.Exit(1)

    # 1. Load config to get AWS profile
    config = load_campaign_config(campaign_name)
    aws_config = config.get("aws", {})
    profile = aws_config.get("profile") or aws_config.get("aws_profile")
    
    if not profile:
        console.print("[bold red]No AWS profile found in config.toml. Cannot query CloudFormation.[/bold red]")
        raise typer.Exit(1)

    console.print(f"[bold blue]Updating infrastructure config for campaign: {campaign_name}[/bold blue]")
    console.print(f"  Using AWS Profile: [cyan]{profile}[/cyan]")
    console.print(f"  Querying Stack:    [cyan]{stack_name}[/cyan]")

    # 2. Query CloudFormation
    try:
        session = boto3.Session(profile_name=profile)
        cf = session.client("cloudformation")
        response = cf.describe_stacks(StackName=stack_name)
        outputs = response['Stacks'][0].get('Outputs', [])
    except Exception as e:
        console.print(f"[bold red]Failed to query CloudFormation: {e}[/bold red]")
        raise typer.Exit(1)

    output_map = {o['OutputKey']: o['OutputValue'] for o in outputs}
    
    # 3. Map Outputs to Config Keys
    # Mapping based on cdk_scraper_deployment_stack.py CfnOutput keys
    mapping = {
        "ScrapeTasksQueueUrl": "cocli_scrape_tasks_queue_url",
        "EnrichmentQueueUrl": "cocli_enrichment_queue_url",
        "GmListItemQueueUrl": "cocli_gm_list_item_queue_url",
        "BucketName": "cocli_data_bucket_name",
        "WebBucketName": "cocli_web_bucket_name",
        "WebDomainName": "hosted-zone-domain" # Optional, might keep user's manual entry
    }

    updates_made = False
    for cf_key, config_key in mapping.items():
        val = output_map.get(cf_key)
        if val:
            # Special case for hosted-zone-domain: don't overwrite if it looks like a full subdomain
            # or if the user already has it set correctly.
            if config_key == "hosted-zone-domain" and config.get("aws", {}).get(config_key):
                continue
                
            if config.get("aws", {}).get(config_key) != val:
                config["aws"][config_key] = val
                console.print(f"  [green]Updating {config_key}[/green] -> {val}")
                updates_made = True

    # 4. Save Config
    if updates_made:
        with open(config_path, "w") as f:
            toml.dump(config, f)
        console.print("[bold green]✓ Config updated successfully![/bold green]")
        
        console.print("\n[bold yellow]⚠️  IMPORTANT: Infrastructure endpoints have changed![/bold yellow]")
        console.print("1. Run [bold]cocli web deploy[/bold] to push this new config to S3.")
        console.print("2. Run [bold]make deploy-rpi[/bold] to update and restart your Raspberry Pi workers.")
    else:
        console.print("[green]Config is already up to date with AWS infrastructure.[/green]")

if __name__ == "__main__":
    app()
