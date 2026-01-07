import typer
import boto3
import os
from rich.console import Console
from rich.progress import track
from pathlib import Path
from typing import Optional

from cocli.core.config import get_companies_dir, get_campaign
from cocli.compilers.website_compiler import WebsiteCompiler

app = typer.Typer()
console = Console()

@app.command()
def main(
    tag: str = typer.Argument("batch-v6-test-1", help="Tag used for the test batch."),
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name."),
    bucket: Optional[str] = typer.Option(None, "--bucket", "-b", help="S3 bucket name."),
) -> None:
    """
    Syncs enrichment results from S3 for a specific batch of prospects.
    """
    if not campaign_name:
        campaign_name = get_campaign()
    
    s3_bucket = bucket or os.getenv("COCLI_S3_BUCKET_NAME")
    if not s3_bucket:
        console.print("[bold red]Error: No S3 bucket specified and COCLI_S3_BUCKET_NAME not set.[/bold red]")
        raise typer.Exit(1)

    console.print(f"[bold]Syncing results from S3 bucket: {s3_bucket}[/bold]")
    
    # Load enqueued reference to know which ones to check
    ref_path = Path(f"enqueued_{tag}.json")
    if not ref_path.exists():
        console.print(f"[bold red]Error: Reference file {ref_path} not found.[/bold red]")
        raise typer.Exit(1)
    
    import json
    enqueued_data = json.loads(ref_path.read_text())
    
    s3_client = boto3.client("s3")
    companies_dir = get_companies_dir()
    compiler = WebsiteCompiler()
    
    synced_count = 0
    
    for item in track(enqueued_data, description="Syncing from S3..."):
        slug = item["slug"]
        
        # S3 Paths (matching enrichment_service logic)
        s3_prefix = f"companies/{slug}"
        web_key = f"{s3_prefix}/enrichments/website.md"
        index_key = f"{s3_prefix}/_index.md"
        
        local_dir = companies_dir / slug
        local_enrichment_dir = local_dir / "enrichments"
        local_web_path = local_enrichment_dir / "website.md"
        local_index_path = local_dir / "_index.md"
        
        try:
            # 1. Download website.md if it exists
            try:
                s3_client.head_object(Bucket=s3_bucket, Key=web_key)
                local_enrichment_dir.mkdir(parents=True, exist_ok=True)
                s3_client.download_file(s3_bucket, web_key, str(local_web_path))
                
                # 2. Download _index.md if missing locally (unlikely but safe)
                if not local_index_path.exists():
                    try:
                        s3_client.download_file(s3_bucket, index_key, str(local_index_path))
                    except Exception:
                        pass
                
                # 3. Compile the result locally to update the Company model
                if local_web_path.exists():
                    compiler.compile(local_dir)
                    synced_count += 1
            except s3_client.exceptions.ClientError as e:
                if e.response['Error']['Code'] == "404":
                    # Not processed yet
                    continue
                else:
                    raise
                    
        except Exception as e:
            console.print(f"[red]Error syncing {slug}: {e}[/red]")

    console.print("\n[bold green]Sync Complete![/bold green]")
    console.print(f"Downloaded and compiled {synced_count} results from S3.")
    console.print(f"Run `PYTHONPATH=. ./.venv/bin/python scripts/evaluate_batch_results.py {tag}` to see the results.")

if __name__ == "__main__":
    app()
