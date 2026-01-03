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
    
    # Load Place IDs from campaign prospects to filter
    from cocli.core.prospects_csv_manager import ProspectsIndexManager
    manager = ProspectsIndexManager(campaign_name)
    target_place_ids = set()
    target_slugs = set() # Secondary matching
    
    console.print("Loading prospects from index for cross-referencing...")
    for prospect in manager.read_all_prospects():
        if prospect.Place_ID:
            target_place_ids.add(prospect.Place_ID)
        if prospect.Domain:
            target_slugs.add(slugify(prospect.Domain))
    
    console.print(f"Found {len(target_place_ids)} unique Place IDs in campaign prospects index.")

    results = []
    
    # Iterate all companies
    company_paths = [p for p in companies_dir.iterdir() if p.is_dir()]
    
    for company_path in track(company_paths, description="Scanning companies..."):
        # 1. Filter by campaign tag (Source of Truth)
        tags_path = company_path / "tags.lst"
        has_tag = False
        if tags_path.exists():
            try:
                tags = tags_path.read_text().strip().splitlines()
                if campaign_name in tags:
                    has_tag = True
            except Exception:
                pass
        
        # 2. Filter by Place ID or Slug (Fallback)
        # We need the Place ID from the _index.md to check against our target list
        index_md = company_path / "_index.md"
        place_id = None
        if index_md.exists():
            try:
                parts = index_md.read_text().split("---")
                if len(parts) >= 3:
                    idx_data = yaml.safe_load(parts[1])
                    if idx_data:
                        place_id = idx_data.get("place_id")
            except: pass

        in_index = (place_id and place_id in target_place_ids) or (company_path.name in target_slugs)

        if not has_tag and not in_index:
            continue

        website_md = company_path / "enrichments" / "website.md"
        index_md = company_path / "_index.md"
        
        if not website_md.exists() and not index_md.exists(): 
            continue
        
        emails = set()

        # Check _index.md (Compiled data)
        if index_md.exists():
            try:
                content = index_md.read_text()
                if content.startswith("---"):
                    parts = content.split("---")
                    if len(parts) >= 3:
                        data = yaml.safe_load(parts[1])
                        if data and data.get("email"):
                            # Filter out placeholders
                            e = data.get("email")
                            if e and e not in ["null", "''", ""]:
                                emails.add(e)
            except Exception:
                pass

        # Check website.md (Raw enrichment data)
        if website_md.exists():
            try:
                content = website_md.read_text()
                if content.startswith("---"):
                    parts = content.split("---")
                    if len(parts) >= 3:
                        data = yaml.safe_load(parts[1])
                        if data:
                            email = data.get("email")
                            personnel = data.get("personnel", [])
                            
                            if email and email not in ["null", "''", ""]: 
                                emails.add(email)
                            
                            if personnel:
                                for p in personnel:
                                    if isinstance(p, dict) and p.get("email"):
                                        emails.add(p["email"])
                                    elif isinstance(p, str) and "@" in p: 
                                         emails.add(p)
            except Exception:
                pass
                    
        if emails:
            # Get basic info from _index.md or website.md
            company_name = company_path.name
            domain = company_path.name
            phone = None
            
            # Try to get better info from _index.md
            if index_md.exists():
                try:
                    parts = index_md.read_text().split("---")
                    if len(parts) >= 3:
                        idx_data = yaml.safe_load(parts[1])
                        if idx_data:
                            company_name = idx_data.get("name") or company_name
                            domain = idx_data.get("domain") or domain
                            phone = idx_data.get("phone_1") or idx_data.get("phone_number")
                except Exception:
                    pass

            results.append({
                "company": company_name,
                "domain": domain,
                "emails": "; ".join(sorted(list(emails))),
                "phone": phone,
                "website": domain
            })

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
        console.print("[bold green]Successfully uploaded export to S3.[/bold green]")
        console.print(f"Download URL: https://{bucket_name}/{s3_key}")
    except Exception as e:
        console.print(f"[bold red]Failed to upload to S3: {e}[/bold red]")

if __name__ == "__main__":
    app()
