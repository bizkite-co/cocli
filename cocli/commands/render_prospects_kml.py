import csv
import simplekml # type: ignore
from pathlib import Path
import typer
import logging
from typing import Dict, List, Optional, cast

from ..core.config import get_scraped_data_dir, get_companies_dir, get_people_dir
from ..models.company import Company
from ..models.person import Person

logger = logging.getLogger(__name__)

def render_prospects_kml(
    campaign_name: str = typer.Argument(..., help="The name of the campaign to render the KML for.")
):
    """
    Generates a KML file for prospects from a CSV file for a specific campaign,
    including enriched data like emails, phones, and associated people.
    """
    # Find campaign directory
    campaign_dirs = list(Path("campaigns").glob(f"**/{campaign_name}"))
    if not campaign_dirs:
        logger.error(f"Campaign '{campaign_name}' not found.")
        raise typer.Exit(code=1)
    campaign_dir = campaign_dirs[0]

    prospects_csv_path = get_scraped_data_dir() / campaign_name / "prospects" / "prospects.csv"
    output_kml_path = campaign_dir / f"{campaign_name}_prospects.kml"

    if not prospects_csv_path.exists():
        logger.error(f"Error: Prospects CSV file not found at {prospects_csv_path}")
        raise typer.Exit(code=1)

    kml = simplekml.Kml()

    # --- Load all Companies for lookup ---
    companies_by_place_id: Dict[str, Company] = {}
    companies_by_name: Dict[str, Company] = {}
    for company_obj in Company.get_all(): # Renamed to company_obj to avoid redefinition
        if company_obj.place_id:
            companies_by_place_id[company_obj.place_id] = company_obj
        companies_by_name[company_obj.name] = company_obj # Also store by name for people lookup

    # --- Load all People for lookup ---
    people_by_company_name: Dict[str, List[Person]] = {}
    people_root_dir = get_people_dir()
    for person_dir in people_root_dir.iterdir():
        if person_dir.is_dir():
            person = Person.from_directory(person_dir)
            if person and person.company_name:
                people_by_company_name.setdefault(person.company_name, []).append(person)

    with open(prospects_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('Name')
            lat = row.get('Latitude')
            lon = row.get('Longitude')
            place_id = row.get('Place_ID')

            if not all([name, lat, lon, place_id]):
                logger.warning(f"Skipping prospect due to missing data: {row.get('Name', 'N/A')}")
                continue

            # Get enriched Company data
            company: Optional[Company] = companies_by_place_id.get(cast(str, place_id)) # Cast place_id to str
            if not company:
                # Fallback to name lookup if place_id not found in canonical companies
                company = companies_by_name.get(cast(str, name)) # Cast name to str

            if not company:
                logger.warning(f"Skipping prospect '{name}' (Place ID: {place_id}) as no matching Company record was found.")
                continue

            # At this point, 'company' is guaranteed to be a Company object

            # Get associated People
            associated_people: List[Person] = people_by_company_name.get(company.name, [])

            placemark = kml.newpoint(name=name)
            placemark.coords = [(lon, lat)]

            # --- Construct rich HTML description ---
            description_parts = []
            description_parts.append("<![CDATA[") # Start CDATA block

            # Thumbnail
            thumbnail_url = row.get('Thumbnail_URL')
            if thumbnail_url:
                description_parts.append(f'<img src="{thumbnail_url}" width="150"><br>')

            # Basic Info
            description_parts.append(f'<b>Name:</b> {name}<br>')
            if company.domain:
                description_parts.append(f'<b>Domain:</b> <a href="https://{company.domain}">{company.domain}</a><br>')
            elif row.get('Website'):
                website = row.get('Website')
                description_parts.append(f'<b>Website:</b> <a href="{website}">{website}</a><br>')
            
            # Email
            email_address = None
            if company.email:
                email_address = company.email
            elif row.get('Email'):
                email_address = row.get('Email')
            if email_address:
                description_parts.append(f'<b>Email:</b> <a href="mailto:{email_address}">{email_address}</a><br>')

            # Phone
            phone_number = None
            if company.phone_number or company.phone_1:
                phone_number = company.phone_number or company.phone_1
            elif row.get('Phone_1'):
                phone_number = row.get('Phone_1')
            if phone_number:
                description_parts.append(f'<b>Phone:</b> {phone_number}<br>')

            full_address = company.full_address or row.get('Full_Address')
            if full_address:
                description_parts.append(f'<b>Address:</b> {full_address}<br>')
            
            # Associated People
            if associated_people:
                description_parts.append('<hr><b>Associated People:</b><br>')
                for person in associated_people:
                    person_info = f'{person.name}'
                    if person.role: person_info += f' ({person.role})'
                    if person.email: person_info += f' - <a href="mailto:{person.email}">{person.email}</a>'
                    if person.phone: person_info += f' - {person.phone}'
                    description_parts.append(f'{person_info}<br>')

            description_parts.append("]]>") # End CDATA block
            placemark.description = "".join(description_parts)

    kml.save(output_kml_path)
    logger.info(f"KML file generated at: {output_kml_path}")