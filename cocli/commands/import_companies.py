import csv
from pathlib import Path
import typer
import yaml
from typing import List
from cocli.core.utils import slugify, create_company_files
from cocli.models.company import Company
from cocli.models.website import Website
from cocli.core.website_cache import WebsiteCache
from fuzzywuzzy import process

def import_companies(
    prospects_csv_path: Path = typer.Argument(..., help="Path to the prospects CSV file.", exists=True, file_okay=True, dir_okay=False, readable=True),
    tags: List[str] = typer.Option(..., "--tag", help="Tags to add to the companies."),
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
    website_cache = WebsiteCache()

    if not companies_dir.exists():
        print(f"Error: Companies directory not found at {companies_dir}")
        raise typer.Exit(code=1)

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
                print(f"Updating existing company: {company_dir.name}")
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
                print(f"Creating new company: {company_name}")
                company_slug = slugify(company_name)
                company_dir = companies_dir / company_slug
                company_data_from_csv["tags"] = tags
                company = Company(**company_data_from_csv)
                create_company_files(company, company_dir)

            # Add to website cache
            if company.domain:
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
            print(f"Created/Updated google-maps.md for {company_name}")

    website_cache.save()

if __name__ == "__main__":
    import_prospects()