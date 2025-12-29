import typer
import csv
import yaml
from typing import Optional
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign, get_campaigns_dir
from cocli.core.text_utils import slugify

app = typer.Typer()
console = Console()

@app.command()
def main(campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context.")) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    companies_dir = get_companies_dir()
    campaign_dir = get_campaigns_dir() / campaign_name
    campaign_dir.mkdir(parents=True, exist_ok=True)
        
    export_dir = campaign_dir / "exports"
    export_dir.mkdir(exist_ok=True)
    output_file = export_dir / f"enriched_emails_{campaign_name}.csv"
    
    # Load slugs from campaign prospects to filter
    from cocli.core.prospects_csv_manager import ProspectsIndexManager
    manager = ProspectsIndexManager(campaign_name)
    target_slugs = set()
    
    console.print("Loading prospects from index...")
    for prospect in manager.read_all_prospects():
        if prospect.Domain:
            target_slugs.add(slugify(prospect.Domain))
    
    console.print(f"Found {len(target_slugs)} targets in campaign prospects.")

    results = []
    
    # Iterate all companies
    # We list explicitly to get a count for track()
    company_paths = [p for p in companies_dir.iterdir() if p.is_dir()]
    
    for company_path in track(company_paths, description="Scanning companies..."):
        # Filter by campaign
        if target_slugs and company_path.name not in target_slugs:
            continue

        website_md = company_path / "enrichments" / "website.md"
        if not website_md.exists(): 
            continue
        
        try:
            # Parse YAML frontmatter
            content = website_md.read_text()
            if content.startswith("---"):
                parts = content.split("---")
                if len(parts) >= 3:
                    data = yaml.safe_load(parts[1])
                    
                    if not data: 
                        continue

                    email = data.get("email")
                    personnel = data.get("personnel", [])
                    
                    emails = set()
                    if email: 
                        emails.add(email)
                    
                    if personnel:
                        for p in personnel:
                            if isinstance(p, dict) and p.get("email"):
                                emails.add(p["email"])
                            elif isinstance(p, str) and "@" in p: # fallback
                                 emails.add(p)
                    
                    if emails:
                        results.append({
                            "company": data.get("company_name") or company_path.name,
                            "domain": data.get("domain") or company_path.name,
                            "emails": "; ".join(emails),
                            "phone": data.get("phone"),
                            "website": data.get("url")
                        })
        except Exception:
            pass

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "domain", "emails", "phone", "website"])
        writer.writeheader()
        writer.writerows(results)
        
    console.print(f"[bold green]Exported {len(results)} companies with emails to {output_file}[/bold green]")

    # --- S3 Upload ---
    from cocli.core.reporting import get_boto3_session, load_campaign_config
    config = load_campaign_config(campaign_name)
    s3_config = config.get("aws", {})
    bucket_name = s3_config.get("cocli_web_bucket_name") or "cocli-web-assets-turboheat-net"
    s3_key = f"exports/{campaign_name}-emails.csv"

    try:
        session = get_boto3_session(config)
        s3 = session.client("s3")
        console.print(f"Uploading to s3://{bucket_name}/{s3_key}...")
        s3.upload_file(str(output_file), bucket_name, s3_key)
        console.print(f"[bold green]Successfully uploaded export to S3.[/bold green]")
        console.print(f"Download URL: https://{bucket_name}/{s3_key}")
    except Exception as e:
        console.print(f"[bold red]Failed to upload to S3: {e}[/bold red]")

if __name__ == "__main__":
    app()
