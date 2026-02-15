import json
from pathlib import Path
from datetime import datetime, UTC
from typing import List, Any, Dict
import yaml
from rich.console import Console

from .base import BaseCompiler
from ..models.company import Company
from ..models.website import Website
from ..core.utils import create_company_files

console = Console()

class WebsiteCompiler(BaseCompiler):
    def __init__(self) -> None:
        self.errors: List[Dict[str, Any]] = []

    def log_error(self, company_slug: str, error: str) -> None:
        self.errors.append({
            "company_slug": company_slug,
            "error": error,
            "timestamp": datetime.now(UTC).isoformat()
        })

    def save_audit_report(self) -> None:
        if not self.errors:
            return
        
        from ..core.config import get_temp_dir
        report_path = get_temp_dir() / "audit_report.json"
        
        # Load existing if any
        existing = []
        if report_path.exists():
            try:
                with open(report_path, 'r') as f:
                    existing = json.load(f)
            except Exception:
                pass
        
        # Append new unique ones (based on slug and error message)
        seen = {(e["company_slug"], e["error"]) for e in existing}
        for e in self.errors:
            if (e["company_slug"], e["error"]) not in seen:
                existing.append(e)
        
        with open(report_path, 'w') as f:
            json.dump(existing, f, indent=2)
        
        console.print(f"[bold blue]Audit report saved to {report_path}[/bold blue]")

    def compile(self, company_dir: Path) -> None:
        website_md_path = company_dir / "enrichments" / "website.md"
        if not website_md_path.exists():
            return

        company = Company.from_directory(company_dir)
        if not company:
            console.print(f"[bold yellow]Warning:[/bold yellow] Could not load company data for {company_dir.name}")
            return

        with open(website_md_path, "r") as f:
            content = f.read().strip()
            
            # Robust split even if header is malformed like ---key: val
            from ..core.text_utils import parse_frontmatter
            frontmatter_str = parse_frontmatter(content)
            
            if frontmatter_str:
                try:
                    from ..utils.yaml_utils import resilient_safe_load
                    website_data_dict = resilient_safe_load(frontmatter_str) or {}
                    
                    # Resilience: Pre-filter junk data before model validation
                    from ..core.text_utils import is_valid_email
                    
                    # 1. Filter all_emails
                    if "all_emails" in website_data_dict and isinstance(website_data_dict["all_emails"], list):
                        website_data_dict["all_emails"] = [e for e in website_data_dict["all_emails"] if isinstance(e, str) and is_valid_email(e)]
                    
                    # 2. Filter primary email
                    if "email" in website_data_dict and website_data_dict["email"]:
                        if not isinstance(website_data_dict["email"], str) or not is_valid_email(website_data_dict["email"]):
                            website_data_dict["email"] = None
                            
                    # 3. Filter personnel (ensure dicts only)
                    if "personnel" in website_data_dict and isinstance(website_data_dict["personnel"], list):
                        website_data_dict["personnel"] = [p for p in website_data_dict["personnel"] if isinstance(p, dict)]

                    website_data = Website(**website_data_dict)
                except yaml.YAMLError:
                    console.print(f"[bold yellow]Warning:[/bold yellow] Could not parse YAML in {website_md_path}")
                    return
                except Exception as e:
                    console.print(f"[bold red]Validation failed for {company_dir.name}:[/bold red] {e}")
                    return
            else:
                return

        updated = False
        
        # Phone
        if website_data.phone and not company.phone_number:
            company.phone_number = website_data.phone
            updated = True

        # Social URLs
        for field in ["facebook_url", "linkedin_url", "instagram_url", "twitter_url", "youtube_url"]:
            website_val = getattr(website_data, field)
            company_val = getattr(company, field)
            if website_val and not company_val:
                setattr(company, field, website_val)
                updated = True

        # Content fields (overwrite if website has data, as website is the current enrichment target)
        if website_data.about_us_url and website_data.about_us_url != company.about_us_url:
            company.about_us_url = website_data.about_us_url
            updated = True

        if website_data.contact_url and website_data.contact_url != company.contact_url:
            company.contact_url = website_data.contact_url
            updated = True

        if website_data.description and website_data.description != company.description:
            company.description = website_data.description
            updated = True

        # List fields: MERGE
        for field in ["services", "products", "categories", "keywords", "tech_stack"]:
            if field == "keywords":
                website_list = website_data.found_keywords or []
            else:
                website_list = getattr(website_data, field) or []
                
            company_list = getattr(company, field) or []
            
            existing_set = set(company_list)
            new_items = [item for item in website_list if item and item not in existing_set]
            
            if new_items:
                company_list.extend(new_items)
                setattr(company, field, company_list)
                updated = True

        # Email
        if website_data.email and not company.email:
            from ..models.email_address import EmailAddress
            try:
                company.email = EmailAddress(str(website_data.email))
                updated = True
            except Exception:
                pass

        if updated:
            create_company_files(company, company_dir)
            company.save()
            return
