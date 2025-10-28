from pathlib import Path
import yaml
from rich.console import Console

from .base import BaseCompiler
from ..models.company import Company
from ..models.website import Website
from ..core.utils import create_company_files

console = Console()

class WebsiteCompiler(BaseCompiler):
    def compile(self, company_dir: Path) -> None:
        website_md_path = company_dir / "enrichments" / "website.md"
        if not website_md_path.exists():
            return

        company = Company.from_directory(company_dir)
        if not company:
            console.print(f"[bold yellow]Warning:[/bold yellow] Could not load company data for {company_dir.name}")
            return

        with open(website_md_path, "r") as f:
            content = f.read()
            if content.startswith("---") and "---" in content[3:]:
                frontmatter_str, _ = content.split("---", 2)[1:]
                try:
                    website_data_dict = yaml.safe_load(frontmatter_str) or {}
                    website_data = Website(**website_data_dict)
                except yaml.YAMLError:
                    console.print(f"[bold yellow]Warning:[/bold yellow] Could not parse YAML in {website_md_path}")
                    return
            else:
                return

        updated = False
        if website_data.phone and not company.phone_number:
            company.phone_number = website_data.phone
            updated = True

        if website_data.facebook_url and not company.facebook_url:
            company.facebook_url = website_data.facebook_url
            updated = True

        if website_data.linkedin_url and not company.linkedin_url:
            company.linkedin_url = website_data.linkedin_url
            updated = True

        if website_data.instagram_url and not company.instagram_url:
            company.instagram_url = website_data.instagram_url
            updated = True

        if website_data.twitter_url and not company.twitter_url:
            company.twitter_url = website_data.twitter_url
            updated = True

        if website_data.youtube_url and not company.youtube_url:
            company.youtube_url = website_data.youtube_url
            updated = True

        if website_data.about_us_url and not company.about_us_url:
            company.about_us_url = website_data.about_us_url
            updated = True

        if website_data.contact_url and not company.contact_url:
            company.contact_url = website_data.contact_url
            updated = True

        if website_data.email and not company.email:
            # Clean the email by removing all spaces
            cleaned_email = website_data.email.replace(' ', '')
            company.email = cleaned_email
            updated = True

        if updated:
            create_company_files(company, company_dir)
            console.print(f"Updated -> {company.name}")
