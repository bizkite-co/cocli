import typer
import csv
import yaml
import json
from typing import Optional, Any

from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaign, get_campaigns_dir
from cocli.core.text_utils import slugify, is_valid_email
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
        if content.startswith("---"):
            parts = content.split("---")
            if len(parts) >= 3:
                data = yaml.safe_load(parts[1])
                
                # Hotfix for legacy/malformed personnel data
                if "personnel" in data and isinstance(data["personnel"], list):
                    sanitized_personnel = []
                    for p in data["personnel"]:
                        if isinstance(p, str):
                            sanitized_personnel.append({"raw_entry": p})
                        elif isinstance(p, dict):
                            sanitized_personnel.append(p)
                    data["personnel"] = sanitized_personnel

                return Website.model_validate(data)
    except Exception:
        # logging.error(f"Error loading website data for {company_slug}: {e}")
        pass
    return None

@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    keywords: bool = typer.Option(False, "--keywords", help="Only export companies that have found keywords (enriched).")
) -> None:
    if not campaign_name:
        campaign_name = get_campaign()
    
    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    companies_dir = get_companies_dir()
    campaign_dir = get_campaigns_dir() / campaign_name
    email_index_dir = campaign_dir / "indexes" / "emails"
    exclusion_manager = ExclusionManager(campaign_name)
    
    export_dir = campaign_dir / "exports"
    export_dir.mkdir(exist_ok=True)
    output_file = export_dir / f"enriched_emails_{campaign_name}.csv"
    
    # 1. Load Email Providers to filter out the COMPANY domains (preventing 'gmail.com' as a company)
    from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager
    domain_manager = WebsiteDomainCsvManager()
    email_providers = {d.domain for d in domain_manager.data.values() if d.is_email_provider}
    email_providers.update({"gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "aol.com", "icloud.com", "msn.com", "me.com", "live.com", "googlemail.com"})

    # 2. Load Emails from Index
    domain_emails = {}
    if email_index_dir.exists():
        console.print(f"Loading emails from index: {email_index_dir}")
        for domain_dir in email_index_dir.iterdir():
            if domain_dir.is_dir():
                domain = domain_dir.name
                # WE SKIP THE DOMAIN IF IT IS AN EMAIL PROVIDER (The company shouldn't be 'gmail.com')
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
                            # Strip prefixes
                            for prefix in ["mailto:", "mail:", "email:"]:
                                if e_lower.startswith(prefix):
                                    email_str = email_str[len(prefix):]
                                    e_lower = email_str.lower()
                            
                            # DEDUPLICATE CASE-INSENSITIVELY, BUT KEEP ALL GMAIL/ETC. ADDRESSES
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
    
    console.print("Loading prospects from index...")
    for prospect in manager.read_all_prospects():
        if prospect.Place_ID:
            target_place_ids.add(prospect.Place_ID)
        if prospect.Domain:
            target_slugs.add(slugify(prospect.Domain))

    results = []
    
    # 4. Iterate all companies
    company_paths = [p for p in companies_dir.iterdir() if p.is_dir()]
    
    for company_path in track(company_paths, description="Scanning companies..."):
        # Filter by campaign tag
        tags_path = company_path / "tags.lst"
        has_tag = False
        if tags_path.exists():
            try:
                tags = tags_path.read_text().strip().splitlines()
                if campaign_name in tags:
                    has_tag = True
            except Exception:
                pass
        
        # Filter by Place ID or Slug
        index_md = company_path / "_index.md"
        idx_data: dict[str, Any] = {}
        if index_md.exists():
            try:
                parts = index_md.read_text().split("---")
                if len(parts) >= 3:
                    idx_data = yaml.safe_load(parts[1]) or {}
            except Exception:
                pass

        place_id = idx_data.get("place_id")
        in_index = (place_id and place_id in target_place_ids) or (company_path.name in target_slugs)

        if not has_tag and not in_index:
            continue

        domain = idx_data.get("domain") or company_path.name
        
        # Filter by exclusions
        if exclusion_manager.is_excluded(domain=domain, slug=company_path.name):
            continue

        # SKIP if the company itself is a provider
        if domain in email_providers:
            continue

        emails = domain_emails.get(domain, [])
        
        # Fallback to _index.md ONLY if index is empty
        if not emails and idx_data.get("email"):
            e = str(idx_data["email"]).strip()
            e_lower = e.lower()
            for prefix in ["mailto:", "mail:", "email:"]:
                if e_lower.startswith(prefix):
                    e = e[len(prefix):]
                    break
            if is_valid_email(e):
                emails = [e]

        if not emails:
            continue

        # Filter by Keywords if requested
        if keywords:
            website_data = get_website_data(company_path.name)
            if not website_data or not website_data.found_keywords:
                continue

        # Get categories and services
        categories = idx_data.get("categories", [])
        services = idx_data.get("services", [])
        products = idx_data.get("products", [])
        
        # Load Website data for keywords
        website_data = get_website_data(company_path.name)
        found_keywords = website_data.found_keywords if website_data else []

        def clean_list(items: list[Any]) -> list[str]:
            cleaned: list[str] = []
            if not items:
                return cleaned
            for item in items:
                item_str = str(item).strip()
                # Just remove if it matches an email perfectly to clean up lists
                if is_valid_email(item_str):
                    continue
                cleaned.append(item_str)
            return cleaned

        results.append({
            "company": idx_data.get("name") or company_path.name,
            "domain": domain,
            "emails": "; ".join(emails),
            "phone": idx_data.get("phone_1") or idx_data.get("phone_number"),
            "website": domain,
            "categories": "; ".join(sorted(list(set(clean_list(categories))))),
            "services": "; ".join(sorted(list(set(clean_list(services))))),
            "products": "; ".join(sorted(list(set(clean_list(products))))),
            "keywords": "; ".join(sorted(list(set(found_keywords))))
        })

    # Write CSV
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "domain", "emails", "phone", "website", "categories", "services", "products", "keywords"])
        writer.writeheader()
        writer.writerows(results)
        
    console.print(f"[bold green]Exported {len(results)} companies with emails to {output_file}[/bold green]")

    # Write JSON
    json_output_file = export_dir / f"enriched_emails_{campaign_name}.json"
    with open(json_output_file, "w") as f:
        json.dump(results, f, indent=2)

    # --- S3 Upload ---
    from cocli.core.reporting import get_boto3_session, load_campaign_config
    config = load_campaign_config(campaign_name)
    s3_config = config.get("aws", {})
    bucket_name = s3_config.get("cocli_web_bucket_name") or "cocli-web-assets-turboheat-net"
    s3_key_csv = f"exports/{campaign_name}-emails.csv"
    s3_key_json = f"exports/{campaign_name}-emails.json"

    try:
        session = get_boto3_session(config)
        s3 = session.client("s3")
        console.print(f"Uploading to s3://{bucket_name}/exports/...")
        s3.upload_file(str(output_file), bucket_name, s3_key_csv)
        s3.upload_file(str(json_output_file), bucket_name, s3_key_json)
        console.print("[bold green]Successfully uploaded exports to S3.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to upload to S3: {e}[/bold red]")

if __name__ == "__main__":
    app()
