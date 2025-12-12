import simplekml # type: ignore
import typer
import logging
from typing import Dict, List, Optional

from ..core.config import get_people_dir, get_campaign_dir
from ..models.company import Company
from ..models.person import Person

logger = logging.getLogger(__name__)

def render_prospects_kml(
    campaign_name: str = typer.Argument(..., help="The name of the campaign to render the KML for.")
) -> None:
    """
    Generates a KML file for prospects from a CSV file for a specific campaign,
    including enriched data like emails, phones, and associated people.
    """
    # Find campaign directory
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign '{campaign_name}' not found.")
        raise typer.Exit(code=1)

    from ..core.prospects_csv_manager import ProspectsIndexManager
    manager = ProspectsIndexManager(campaign_name)

    output_kml_path = campaign_dir / f"{campaign_name}_prospects.kml"

    if not manager.index_dir.exists():
        logger.error(f"Error: Prospects index not found at {manager.index_dir}")
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

    prospects = manager.read_all_prospects()
    for prospect in prospects:
        name = prospect.Name
        lat = prospect.Latitude
        lon = prospect.Longitude
        place_id = prospect.Place_ID

        if not all([name, lat, lon, place_id]):
            logger.warning(f"Skipping prospect due to missing data: {name or 'N/A'}")
            continue

        # Get enriched Company data
        company: Optional[Company] = companies_by_place_id.get(str(place_id))
        if not company and name:
            # Fallback to name lookup if place_id not found in canonical companies
            company = companies_by_name.get(str(name))

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
        thumbnail_url = prospect.Thumbnail_URL
        if thumbnail_url:
            description_parts.append(f'<img src="{thumbnail_url}" width="150"><br>')

        # Basic Info
        description_parts.append(f'<b>Name:</b> {name}<br>')
        if company.domain:
            description_parts.append(f'<b>Domain:</b> <a href="https://{company.domain}">{company.domain}</a><br>')
        elif prospect.Website:
            website = prospect.Website
            description_parts.append(f'<b>Website:</b> <a href="{website}">{website}</a><br>')
        
        # Email
        email_address = None
        if company.email:
            email_address = company.email
        # Note: GoogleMapsProspect does not have an Email field by default, so we removed the fallback from CSV.
        
        if email_address:
            description_parts.append(f'<b>Email:</b> <a href="mailto:{email_address}">{email_address}</a><br>')

        # Phone
        phone_number = None
        if company.phone_number or company.phone_1:
            phone_number = company.phone_number or company.phone_1
        elif prospect.Phone_1:
            phone_number = prospect.Phone_1
        if phone_number:
            description_parts.append(f'<b>Phone:</b> {phone_number}<br>')

        full_address = company.full_address or prospect.Full_Address
        if full_address:
            description_parts.append(f'<b>Address:</b> {full_address}<br>')
        
        # Associated People
        if associated_people:
            description_parts.append('<hr><b>Associated People:</b><br>')
            for person in associated_people:
                person_info = f'{person.name}'
                if person.role:
                    person_info += f' ({person.role})'
                if person.email:
                    person_info += f' - <a href="mailto:{person.email}">{person.email}</a>'
                if person.phone:
                    person_info += f' - {person.phone}'
                description_parts.append(f'{person_info}<br>')

        description_parts.append("]]>") # End CDATA block
        placemark.description = "".join(description_parts)

    kml.save(output_kml_path)
    logger.info(f"KML file generated at: {output_kml_path}")