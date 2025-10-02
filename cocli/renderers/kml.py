
import os
import yaml
import simplekml
import toml
from pathlib import Path

from ..core.config import get_companies_dir
from ..core.geocoding import get_coordinates_from_zip

def render_kml_for_campaign(campaign_name: str):
    """
    Generates a KML file for a specific campaign.
    """
    
    campaign_dirs = list(Path("campaigns").glob(f"**/{campaign_name}"))
    if not campaign_dirs:
        print(f"Campaign '{campaign_name}' not found.")
        return
    campaign_dir = campaign_dirs[0]
    config_path = campaign_dir / "config.toml"
    
    if not config_path.exists():
        print(f"Configuration file not found for campaign '{campaign_name}'.")
        return
        
    with open(config_path, "r") as f:
        config = toml.load(f)
        
    tag = config.get("campaign", {}).get("tag")
    if not tag:
        print(f"Tag not found in configuration for campaign '{campaign_name}'.")
        return
        
    data_dir = get_companies_dir()
    kml = simplekml.Kml()
    
    
    tagged_companies = []
    for company_dir in data_dir.iterdir():
        if company_dir.is_dir():
            tags_path = company_dir / "tags.lst"
            if tags_path.exists():
                with open(tags_path, "r") as f:
                    if tag in f.read():
                        tagged_companies.append(company_dir)
    
    total_companies = len(tagged_companies)
    progress_interval = total_companies // 10 if total_companies > 9 else 1
    company_count = 0
    processed_count = 0

    for company_dir in tagged_companies:
        processed_count += 1
        if processed_count % 10 == 0:
            print(f"Processed {processed_count}/{total_companies} companies...")

        index_file = company_dir / "_index.md"
        if index_file.exists():
            with open(index_file, "r") as f_index:
                content = f_index.read()
                parts = content.split('---\n')
                if len(parts) > 1:
                    try:
                        frontmatter = yaml.safe_load(parts[1])
                        
                        name = frontmatter.get("name")
                        full_address = frontmatter.get("full_address")
                        city = frontmatter.get("city")
                        state = frontmatter.get("state")
                        zip_code = frontmatter.get("zip_code")
                        country = frontmatter.get("country")
                        
                        if country == "United States":
                                                                        if full_address and city and state and zip_code:
                                                                            placemark = kml.newpoint(name=name)
                                                                            placemark.address = f"{full_address}, {city}, {state} {zip_code}"
                                                                            
                                                                            description = f"""
                            Website: {frontmatter.get("website_url", "N/A")}<br>
                            Address: {full_address}<br>
                            Phone: {frontmatter.get("phone_1", "N/A")}
                            """
                                                                            placemark.description = description
                            
                                                                            coords = get_coordinates_from_zip(zip_code)
                                                                            if coords:
                                                                                placemark.coords = [(coords['longitude'], coords['latitude'])]
                                                                            
                                                                            company_count += 1                                
                    except yaml.YAMLError as e:
                        print(f"Error parsing YAML in {index_file}: {e}")

    kml_file_path = campaign_dir / f"{campaign_name}_customers.kml"
    kml.save(kml_file_path)
    print(f"KML file '{kml_file_path}' created successfully.")
    print(f"Added {company_count} companies to the KML file.")
