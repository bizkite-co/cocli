import os
import yaml
import simplekml # type: ignore
import toml
from pathlib import Path
from typing import Optional
import logging

from ..core.config import get_companies_dir, get_people_dir
from ..core.geocoding import get_coordinates_from_zip, get_coordinates_from_city_state, get_coordinates_from_address
from ..models.company import Company
from ..models.person import Person
from ..models.geocode import GeocodeData
from ..core.utils import slugify

logger = logging.getLogger(__name__)

def render_kml_for_campaign(campaign_name: str):
    """
    Generates a KML file for a specific campaign.
    """
    
    campaign_dirs = list(Path("campaigns").glob(f"**/{campaign_name}"))
    if not campaign_dirs:
        logger.error(f"Campaign '{campaign_name}' not found.")
        return
    campaign_dir = campaign_dirs[0]
    config_path = campaign_dir / "config.toml"
    
    if not config_path.exists():
        logger.error(f"Configuration file not found for campaign '{campaign_name}'.")
        return
        
    with open(config_path, "r") as f:
        config = toml.load(f)
        
    tag = config.get("campaign", {}).get("tag")
    if not tag:
        logger.error(f"Tag not found in configuration for campaign '{campaign_name}'.")
        return
        
    people_dir = get_people_dir()
    companies_dir = get_companies_dir()
    kml = simplekml.Kml()
    
    company_count = 0
    
    all_company_dirs = list(companies_dir.iterdir())
    total_companies = len(all_company_dirs)
    processed_count = 0

    for company_dir in all_company_dirs:
        if not company_dir.is_dir():
            continue

        processed_count += 1
        if processed_count % 10 == 0:
            logger.info(f"Processing {processed_count}/{total_companies} companies for KML...")

        company = Company.from_directory(company_dir)
        if not company:
            continue

        if tag not in company.tags or "customer" not in company.tags:
            continue # Only process companies with both tags

        # --- Find Associated Person for Address (for most accurate geocoding) ---
        associated_person: Optional[Person] = None
        for person_file in people_dir.glob("**/*.md"):
            person = Person.from_file(person_file)
            if person and person.company_name and slugify(person.company_name) == slugify(company.name):
                associated_person = person
                break

        # --- Geocoding Logic ---
        geocode_data: Optional[GeocodeData] = None
        company_enrichment_dir = company_dir / "enrichments"
        geocode_md_path = company_enrichment_dir / "geocode.md"

        if geocode_md_path.exists():
            with open(geocode_md_path, "r") as f_md:
                content = f_md.read()
                parts = content.split('---\n')
                if len(parts) > 1:
                    try:
                        frontmatter = yaml.safe_load(parts[1])
                        geocode_data = GeocodeData(**frontmatter)
                    except yaml.YAMLError as e:
                        logger.error(f"Error parsing YAML in {geocode_md_path}: {e}")
                    except Exception as e:
                        logger.error(f"Error loading GeocodeData from {geocode_md_path}: {e}")
        
        if not geocode_data:
            # Determine the best address to use for geocoding
            address_to_geocode = None
            if associated_person and associated_person.full_address:
                address_to_geocode = associated_person.full_address
            elif company.full_address:
                address_to_geocode = company.full_address
            elif associated_person and associated_person.zip_code:
                address_to_geocode = associated_person.zip_code
            elif company.zip_code:
                address_to_geocode = company.zip_code
            elif associated_person and associated_person.city and associated_person.state:
                address_to_geocode = f"{associated_person.city},{associated_person.state}"
            elif company.city and company.state:
                address_to_geocode = f"{company.city},{company.state}"

            if address_to_geocode:
                coordinates = None
                if "address" in address_to_geocode:
                    coordinates = get_coordinates_from_address(address_to_geocode)
                elif len(address_to_geocode) == 5 and address_to_geocode.isdigit(): # Simple check for zip code
                    coordinates = get_coordinates_from_zip(address_to_geocode)
                elif "," in address_to_geocode: # Simple check for city,state
                    coordinates = get_coordinates_from_city_state(address_to_geocode)
                else:
                    coordinates = get_coordinates_from_address(address_to_geocode) # Default to full address search

                if coordinates:
                    geocode_data = GeocodeData(
                        latitude=coordinates["latitude"],
                        longitude=coordinates["longitude"],
                        address=address_to_geocode,
                        zip_code=associated_person.zip_code if associated_person else company.zip_code,
                        city=associated_person.city if associated_person else company.city,
                        state=associated_person.state if associated_person else company.state,
                        country=associated_person.country if associated_person else company.country
                    )
                    # Save geocode data to enrichments
                    company_enrichment_dir.mkdir(parents=True, exist_ok=True)
                    with open(geocode_md_path, "w") as f_md:
                        f_md.write("---\n")
                        yaml.dump(geocode_data.model_dump(exclude_none=True), f_md, sort_keys=False, default_flow_style=False, allow_unicode=True)
                        f_md.write("---\n")
                else:
                    logger.warning(f"Could not geocode address for {company.name} (address: {address_to_geocode}). Skipping KML entry.")
                    continue
            else:
                logger.warning(f"No address information available for {company.name}. Skipping KML entry.")
                continue

        # --- Website Data Access ---
        website_url = None
        if company.domain:
            website_url = company.domain
        
        if not website_url:
            google_maps_md_path = company_enrichment_dir / "google-maps.md"
            if google_maps_md_path.exists():
                with open(google_maps_md_path, "r") as f_md:
                    content = f_md.read()
                    parts = content.split('---\n')
                    if len(parts) > 1:
                        try:
                            frontmatter = yaml.safe_load(parts[1])
                            website_url = frontmatter.get("Website") # Google Maps enrichment uses "Website"
                        except yaml.YAMLError:
                            pass

        # --- KML Placemark Creation ---
        if geocode_data and geocode_data.latitude and geocode_data.longitude:
            placemark = kml.newpoint(name=company.name)
            placemark.coords = [(geocode_data.longitude, geocode_data.latitude)]
            
            description_parts = []
            if website_url:
                description_parts.append(f"Website: <a href=\"http://{website_url}\">{website_url}</a>")
            
            display_address = None
            if associated_person and associated_person.full_address:
                display_address = associated_person.full_address
            elif company.full_address:
                display_address = company.full_address
            elif geocode_data.address:
                display_address = geocode_data.address
            elif geocode_data.city and geocode_data.state:
                display_address = f"{geocode_data.city}, {geocode_data.state}"

            if display_address:
                description_parts.append(f"Address: {display_address}")
            
            # Use phone from company or associated person
            display_phone = None
            if company.phone_1:
                display_phone = company.phone_1
            elif associated_person and associated_person.phone:
                display_phone = associated_person.phone
            
            if display_phone:
                description_parts.append(f"Phone: {display_phone}")
            
            placemark.description = "<br>".join(description_parts)
            company_count += 1

    kml_file_path = campaign_dir / f"{campaign_name}_customers.kml"
    kml.save(kml_file_path)
    logger.info(f"KML file '{kml_file_path}' created successfully.")
    logger.info(f"Added {company_count} companies to the KML file.")
