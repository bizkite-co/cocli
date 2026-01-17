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

    companies_dir = get_companies_dir()
    campaign_dir = get_campaigns_dir() / campaign_name
    email_index_dir = campaign_dir / "indexes" / "emails"
    exclusion_manager = ExclusionManager(campaign_name)
    
    export_dir = campaign_dir / "exports"
    export_dir.mkdir(exist_ok=True)
    output_file = export_dir / f"enriched_emails_{campaign_name}.csv"
    
    # 1. Load Email Providers
    from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager
    domain_manager = WebsiteDomainCsvManager()
    email_providers = {d.domain for d in domain_manager.data.values() if d.is_email_provider}
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
    
    for prospect in manager.read_all_prospects():
        if prospect.Place_ID:
            target_place_ids.add(prospect.Place_ID)
        if prospect.Domain:
            target_slugs.add(slugify(prospect.Domain))

    results = []
    
    # 4. Iterate all companies
    company_paths = [p for p in companies_dir.iterdir() if p.is_dir()]
    
    for company_path in track(company_paths, description="Scanning companies..."):
        tags_path = company_path / "tags.lst"
        has_tag = False
        if tags_path.exists():
            try:
                tags = tags_path.read_text().strip().splitlines()
                if campaign_name in [t.strip() for t in tags]:
                    has_tag = True
            except Exception:
                pass
        
        index_md = company_path / "_index.md"
        idx_data: dict[str, Any] = {}
        if index_md.exists():
            try:
                content = index_md.read_text()
                if "---" in content:
                    parts = content.split("---")
                    if len(parts) >= 3:
                        idx_data = yaml.safe_load(parts[1]) or {}
            except Exception:
                pass

        place_id = idx_data.get("place_id")
        in_index = (place_id and place_id in target_place_ids) or (company_path.name in target_slugs)

        if not has_tag and not in_index:
            continue

        domain = idx_data.get("domain") or company_path.name
        if exclusion_manager.is_excluded(domain=domain, slug=company_path.name):
            continue

        if domain in email_providers:
            continue

        emails = domain_emails.get(domain, [])
        if not emails and idx_data.get("email"):
            e = str(idx_data["email"]).strip()
            if is_valid_email(e):
                emails = [e]

        if not emails and not include_all:
            continue

        if keywords:
            website_data = get_website_data(company_path.name)
            if not website_data or not website_data.found_keywords:
                continue

        results.append({
            "company": idx_data.get("name") or company_path.name,
            "domain": domain,
            "emails": "; ".join(emails),
            "phone": idx_data.get("phone_1") or idx_data.get("phone_number") or "",
            "website": domain,
            "categories": "; ".join(sorted(list(set(idx_data.get("categories", []))))),
            "services": "; ".join(sorted(list(set(idx_data.get("services", []))))),
            "products": "; ".join(sorted(list(set(idx_data.get("products", []))))),
            "keywords": "; ".join(sorted(list(set(idx_data.get("keywords", [])))))
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