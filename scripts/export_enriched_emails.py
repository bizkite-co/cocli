import typer
import csv
import yaml
import json
from typing import Optional

from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign, get_campaigns_dir
from cocli.core.text_utils import is_valid_email
from cocli.models.website import Website
from cocli.core.exclusions import ExclusionManager

app = typer.Typer()
console = Console()

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
    target_hashes = set()
    
    for prospect in manager.read_all_prospects():
        if prospect.place_id:
            target_place_ids.add(prospect.place_id)
        if prospect.company_slug:
            target_slugs.add(prospect.company_slug)
        if prospect.company_hash:
            target_hashes.add(prospect.company_hash)

    results = []
    
    # 4. Iterate all companies
    for company_obj in track(Company.get_all(), description="Scanning companies..."):
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

        if not emails and not include_all:
            continue

        website_data = get_website_data(company_obj.slug)
        if keywords:
            if not website_data or not website_data.found_keywords:
                continue

        # Get keywords from website data if available
        found_keywords = []
        if website_data and website_data.found_keywords:
            found_keywords = website_data.found_keywords

        results.append({
            "company": company_obj.name,
            "domain": domain,
            "emails": "; ".join(emails),
            "phone": str(company_obj.phone_number or company_obj.phone_1 or ""),
            "website": domain,
            "categories": "; ".join(sorted(list(set(company_obj.categories)))),
            "services": "; ".join(sorted(list(set(company_obj.services)))),
            "products": "; ".join(sorted(list(set(company_obj.products)))),
            "keywords": "; ".join(sorted(list(set(found_keywords))))
        })

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "domain", "emails", "phone", "website", "categories", "services", "products", "keywords"])
        writer.writeheader()
        writer.writerows(results)
        
    console.print(f"[bold green]Exported {len(results)} companies to {output_file}[/bold green]")

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