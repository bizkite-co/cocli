import csv
from pathlib import Path
import typer
import yaml
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

from cocli.core.utils import slugify, create_company_files
from cocli.models.company import Company
from cocli.models.website import Website
from cocli.core.website_cache import WebsiteCache
from fuzzywuzzy import process # type: ignore
from cocli.core.config import get_campaign, get_scraped_data_dir

app = typer.Typer()

@app.command(name="google-maps-cache-to-company-files")
def google_maps_cache_to_company_files(
    prospects_csv_path: Optional[Path] = typer.Argument(None, help="Path to the prospects CSV file. If not provided, infers from current campaign context.", exists=False, file_okay=True, dir_okay=False, readable=True),
    tags: Optional[List[str]] = typer.Option(None, "--tag", help="Tags to add to the companies. If not provided, infers from current campaign context."),
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Specify a campaign name to infer the CSV path and tags from. Overrides current campaign context if set."),
    companies_dir: Path = typer.Option(
        "/home/mstouffer/.local/share/cocli_data/companies",
        help="Path to the companies directory."
    ),
    match_threshold: int = typer.Option(
        80,
        help="Threshold for fuzzy matching company names."
    )
):
    """
    Imports prospects from a CSV file, creating or updating companies and their enrichments.
    """
    effective_campaign_name = campaign_name
    if effective_campaign_name is None:
        effective_campaign_name = get_campaign()

    if prospects_csv_path is None:
        if effective_campaign_name is None:
            logger.error("Error: No prospects CSV path provided and no campaign context is set. Please provide a CSV path, a campaign name with --campaign, or set a campaign context using 'cocli campaign set <campaign_name>'.")
            raise typer.Exit(code=1)
        
        inferred_csv_path = get_scraped_data_dir() / effective_campaign_name / "prospects" / "prospects.csv"
        if not inferred_csv_path.exists():
            logger.error(f"Error: Inferred prospects CSV path does not exist: {inferred_csv_path}")
            raise typer.Exit(code=1)
        prospects_csv_path = inferred_csv_path

    if tags is None:
        if effective_campaign_name:
            tags = ["prospect", effective_campaign_name]
        else:
            tags = ["prospect"] # Default tag if no campaign context

    website_cache = WebsiteCache()

    company_dirs = {d.name: d for d in companies_dir.iterdir() if d.is_dir()}

    with open(prospects_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            company_name = row.get('Name')
            if not company_name:
                continue

            place_id = row.get('Place_ID')

            # Try to find existing company
            company_dir = None
            # 1. By Place_ID
            if place_id:
                for d in company_dirs.values():
                    enrichment_file = d / "enrichments" / "google-maps.md"
                    if enrichment_file.exists():
                        with open(enrichment_file, 'r', encoding='utf-8') as ef:
                            try:
                                content = ef.read()
                                if content.startswith("---"):
                                    frontmatter = yaml.safe_load(content.split("---")[1])
                                    if frontmatter.get('Place_ID') == place_id:
                                        company_dir = d
                                        break
                            except (yaml.YAMLError, IndexError):
                                continue
            
            # 2. By fuzzy name matching
            if not company_dir:
                company_slug = slugify(company_name)
                if company_slug in company_dirs:
                    company_dir = company_dirs[company_slug]
                else:
                    best_match, score = process.extractOne(company_slug, list(company_dirs.keys()))
                    if score >= match_threshold:
                        company_dir = company_dirs[best_match]

            # Prepare company data from CSV
            company_data_from_csv = {
                "name": company_name,
                "full_address": row.get('Full_Address'),
                "street_address": row.get('Street_Address'),
                "city": row.get('City'),
                "zip_code": row.get('Zip'),
                "state": row.get('State'),
                "country": row.get('Country'),
                "phone_1": row.get('Phone_1'),
                "website_url": row.get('Website'),
                "domain": row.get('Domain'),
            }

            # Convert numeric fields
            reviews_count_str = row.get('Reviews_count')
            if reviews_count_str:
                try:
                    company_data_from_csv['reviews_count'] = int(reviews_count_str)
                except (ValueError, TypeError):
                    pass # Ignore conversion errors

            average_rating_str = row.get('Average_rating')
            if average_rating_str:
                try:
                    company_data_from_csv['average_rating'] = float(average_rating_str)
                except (ValueError, TypeError):
                    pass # Ignore conversion errors

            company_data_from_csv = {k: v for k, v in company_data_from_csv.items() if v is not None}

            if company_dir:
                # Update existing company
                logger.info(f"Updating existing company: {company_dir.name}")
                company = Company.from_directory(company_dir)
                if company:
                    # Update fields
                    for key, value in company_data_from_csv.items():
                        setattr(company, key, value)
                    # Add new tags
                    for tag in tags:
                        if tag not in company.tags:
                            company.tags.append(tag)
                    create_company_files(company, company_dir)
            else:
                # Create new company
                logger.info(f"Creating new company: {company_name}")
                company_slug = slugify(company_name)
                company_dir = companies_dir / company_slug
                company_data_from_csv["tags"] = tags
                company = Company(**company_data_from_csv)
                create_company_files(company, company_dir)

            # Add to website cache
            if company and company.domain:
                website = website_cache.get_by_url(company.domain)
                if not website:
                    website = Website(url=company.domain)
                for tag in tags:
                    if tag not in website.tags:
                        website.tags.append(tag)
                website_cache.add_or_update(website)

            # Create or update enrichment file
            enrichment_dir = company_dir / "enrichments"
            enrichment_dir.mkdir(parents=True, exist_ok=True)
            google_maps_md_path = enrichment_dir / "google-maps.md"

            enrichment_data = {k: v for k, v in row.items() if v}
            enrichment_data['version'] = 1

            with open(google_maps_md_path, "w") as f_md:
                f_md.write("---\\n")
                yaml.dump(enrichment_data, f_md, sort_keys=False, default_flow_style=False, allow_unicode=True)
                f_md.write("---\\n")
            logger.info(f"Created/Updated google-maps.md for {company_name}")

    website_cache.save()

if __name__ == "__main__":
    typer.run(google_maps_cache_to_company_files)