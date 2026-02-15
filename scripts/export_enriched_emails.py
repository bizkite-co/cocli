import typer
import csv
import yaml
import json
from typing import Optional
from datetime import datetime
from pathlib import Path
import logging

from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign, get_campaigns_dir
from cocli.core.text_utils import is_valid_email
from cocli.models.website import Website
from cocli.core.exclusions import ExclusionManager

app = typer.Typer()
console = Console()

def setup_export_logging(campaign_name: str) -> Path:
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"export_emails_{campaign_name}_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file)],
        force=True
    )
    # Also silence the standard cocli logger to terminal
    for logger_name in ["cocli.models.company", "root"]:
        lgr = logging.getLogger(logger_name)
        lgr.setLevel(logging.ERROR)
        lgr.propagate = False
        lgr.addHandler(logging.FileHandler(log_file))
        
    return log_file

def get_website_data(company_slug: str) -> Optional[Website]:
    """Helper to load the website.md data for a company."""
    website_md_path = get_companies_dir() / company_slug / "enrichments" / "website.md"
    if not website_md_path.exists():
        return None
    
    try:
        content = website_md_path.read_text()
        # Extract YAML frontmatter
        from cocli.core.text_utils import parse_frontmatter
        frontmatter_str = parse_frontmatter(content)
        if frontmatter_str:
            data = yaml.safe_load(frontmatter_str)
            
            # Hotfix for legacy/malformed personnel data
            if data and "personnel" in data and isinstance(data["personnel"], list):
                sanitized_personnel = []
                for p in data["personnel"]:
                    if isinstance(p, str):
                        sanitized_personnel.append({"raw_entry": p})
                    elif isinstance(p, dict):
                        sanitized_personnel.append(p)
                data["personnel"] = sanitized_personnel

            if data:
                return Website.model_validate(data)
    except Exception:
        pass
    return None

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    keywords: bool = typer.Option(False, "--keywords", help="Only export companies that have found keywords (enriched)."),
    include_all: bool = typer.Option(False, "--all", "-a", help="Include all prospects even if they have no emails.")
) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    log_file = setup_export_logging(campaign_name)
    console.print(f"Exporting leads for [bold]{campaign_name}[/bold]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    campaign_dir = get_campaigns_dir() / campaign_name
    email_index_dir = campaign_dir / "indexes" / "emails"
    exclusion_manager = ExclusionManager(campaign_name)
    
    from cocli.core.config import get_campaign_exports_dir
    from cocli.models.company import Company
    export_dir = get_campaign_exports_dir(campaign_name)
    output_file = export_dir / f"enriched_emails_{campaign_name}.csv"
    
    # 1. Load Email Providers and Enriched Domains via DomainIndexManager
    from cocli.core.domain_index_manager import DomainIndexManager
    from cocli.models.campaign import Campaign
    campaign = Campaign.load(campaign_name)
    domain_manager = DomainIndexManager(campaign)
    
    # Query all domains to identify providers and get enriched metadata
    all_domains = domain_manager.query()
    
    email_providers = {d.domain for d in all_domains if d.is_email_provider}
    email_providers.update({"gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "aol.com", "icloud.com", "msn.com", "me.com", "live.com", "googlemail.com"})

    # 2. Load Emails from Index
    domain_emails = {}
    if email_index_dir.exists():
        for domain_dir in email_index_dir.iterdir():
            if domain_dir.is_dir():
                domain = domain_dir.name
                if domain in email_providers:
                    continue
                    
                deduped = {}
                for email_file in domain_dir.iterdir():
                    try:
                        file_content = email_file.read_text().strip()
                        if email_file.suffix == '.json':
                            data = json.loads(file_content)
                            email_val = data.get("email")
                        else:
                            email_val = file_content
                            
                        if email_val and is_valid_email(str(email_val)):
                            email_str = str(email_val).strip()
                            e_lower = email_str.lower()
                            for prefix in ["mailto:", "mail:", "email:"]:
                                if e_lower.startswith(prefix):
                                    email_str = email_str[len(prefix):]
                                    e_lower = email_str.lower()
                            
                            if e_lower not in deduped:
                                deduped[e_lower] = email_str
                    except Exception:
                        pass
                
                if deduped:
                    domain_emails[domain] = sorted(list(deduped.values()))

    # 3. Load Prospects for cross-referencing
    from cocli.core.prospects_csv_manager import ProspectsIndexManager
    manager = ProspectsIndexManager(campaign_name)
    target_place_ids = set()
    target_slugs = set()
    
    # Map for enrichment lookup
    prospect_data_map = {} # slug -> prospect_obj
    
    for prospect in manager.read_all_prospects():
        if prospect.place_id:
            target_place_ids.add(prospect.place_id)
        if prospect.company_slug:
            target_slugs.add(prospect.company_slug)
            # Prioritize prospects with more data
            if prospect.company_slug not in prospect_data_map or prospect.average_rating:
                prospect_data_map[prospect.company_slug] = prospect

    results = []
    skipped_count = 0
    
    # 4. Iterate all companies
    for company_obj in track(Company.get_all(), description="Scanning companies..."):
        if not company_obj:
            skipped_count += 1
            continue

        # Check if company belongs to this campaign via tags (hydration target)
        in_campaign = campaign_name in company_obj.tags
        
        # Primary matching via Place ID or Slug (index target)
        in_index = (
            (company_obj.place_id and company_obj.place_id in target_place_ids) or 
            (company_obj.slug in target_slugs)
        )

        if not in_campaign and not in_index:
            continue

        domain = company_obj.domain or company_obj.slug
        if exclusion_manager.is_excluded(domain=domain, slug=company_obj.slug):
            continue

        if domain in email_providers:
            continue

        emails = domain_emails.get(domain, [])
        if not emails and company_obj.email:
            e = str(company_obj.email).strip()
            if is_valid_email(e):
                emails = [e]

        # REQUIREMENT: Domain, Phone, and Email must all be present
        phone = str(company_obj.phone_number or company_obj.phone_1 or "").strip()
        
        if not domain or not phone or not emails:
            continue

        website_data = get_website_data(company_obj.slug)
        if keywords:
            if not website_data or not website_data.found_keywords:
                continue

        # ENRICHMENT: Pull from index map if missing in company object
        idx_prospect = prospect_data_map.get(company_obj.slug)
        
        gmb_url = company_obj.gmb_url
        if not gmb_url and idx_prospect:
            gmb_url = idx_prospect.gmb_url
            
        rating = str(company_obj.average_rating or "")
        if (not rating or rating == "0.0") and idx_prospect:
            rating = str(idx_prospect.average_rating or "")
            
        reviews = str(company_obj.reviews_count or "0")
        if reviews == "0" and idx_prospect:
            reviews = str(idx_prospect.reviews_count or "0")

        # Combine Tags and Keywords, filtering out the campaign name
        combined_tags = set(company_obj.tags)
        if website_data and website_data.found_keywords:
            combined_tags.update(website_data.found_keywords)
        if idx_prospect and idx_prospect.keyword:
            combined_tags.add(idx_prospect.keyword)
            
        # Filter out common/campaign tags
        filtered_tags = sorted([t for t in combined_tags if t.lower() not in [campaign_name.lower(), "prospect", "customer"]])

        city = company_obj.city or (idx_prospect.city if idx_prospect else "")
        state = company_obj.state or (idx_prospect.state if idx_prospect else "")

        results.append({
            "company": company_obj.name,
            "domain": domain,
            "emails": "; ".join(emails),
            "phone": phone,
            "website": domain,
            "city": city,
            "state": state,
            "categories": "; ".join(sorted(list(set(company_obj.categories)))),
            "services": "; ".join(sorted(list(set(company_obj.services)))),
            "products": "; ".join(sorted(list(set(company_obj.products)))),
            "tags": "; ".join(filtered_tags),
            "gmb_url": gmb_url or "",
            "rating": rating,
            "reviews": reviews
        })

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "domain", "emails", "phone", "website", "city", "state", "categories", "services", "products", "tags", "gmb_url", "rating", "reviews"])
        writer.writeheader()
        writer.writerows(results)
        
    console.print("\n[bold green]Success![/bold green]")
    console.print(f"Exported: [bold]{len(results)}[/bold] companies")
    if skipped_count:
        console.print(f"Skipped: [bold red]{skipped_count}[/bold red] malformed records (check log)")
    console.print(f"Output: [cyan]{output_file}[/cyan]")

    json_output_file = export_dir / f"enriched_emails_{campaign_name}.json"
    with open(json_output_file, "w") as f:
        json.dump(results, f, indent=2)

    from cocli.core.reporting import get_boto3_session, load_campaign_config
    config = load_campaign_config(campaign_name)
    s3_config = config.get("aws", {})
    bucket_name = s3_config.get("cocli_web_bucket_name") or "cocli-web-assets-turboheat-net"
    
    try:
        session = get_boto3_session(config)
        s3 = session.client("s3")
        s3.upload_file(str(output_file), bucket_name, f"exports/{campaign_name}-emails.csv")
        s3.upload_file(str(json_output_file), bucket_name, f"exports/{campaign_name}-emails.json")
        console.print("[bold green]Successfully uploaded exports to S3.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to upload to S3: {e}[/bold red]")

if __name__ == "__main__":
    app()