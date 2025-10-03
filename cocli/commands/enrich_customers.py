import typer
import toml
import yaml
from pathlib import Path

from ..core.config import get_companies_dir, get_people_dir
from ..scrapers.google_maps_finder import find_business_on_google_maps
from ..models.person import Person
from ..core.utils import slugify

app = typer.Typer()

@app.command()
def enrich_customers(
    campaign_name: str = typer.Argument(..., help="Name of the campaign to enrich customers for.")
):
    """
    Enrich existing customers for a campaign with Google Maps data.
    """
    
    campaign_dirs = list(Path("campaigns").glob(f"**/{campaign_name}"))
    if not campaign_dirs:
        print(f"Campaign '{campaign_name}' not found.")
        raise typer.Exit(code=1)
    campaign_dir = campaign_dirs[0]
    config_path = campaign_dir / "config.toml"
    
    if not config_path.exists():
        print(f"Configuration file not found for campaign '{campaign_name}'.")
        raise typer.Exit(code=1)
        
    with open(config_path, "r") as f:
        config = toml.load(f)
        
    tag = config.get("campaign", {}).get("tag")
    if not tag:
        print(f"Tag not found in configuration for campaign '{campaign_name}'.")
        raise typer.Exit(code=1)
        
    people_dir = get_people_dir()
    for person_file in people_dir.glob("**/*.md"):
        if person_file.is_file():
            person = Person.from_file(person_file)
            if not person:
                continue

            if tag in person.tags and "customer" in person.tags:
                if not person.company_name:
                    print(f"Skipping {person.name} as they are not associated with a company.")
                    continue

                company_dir = get_companies_dir() / slugify(person.company_name)
                enrichment_dir = company_dir / "enrichments"
                google_maps_md_path = enrichment_dir / "google-maps.md"
                
                if google_maps_md_path.exists():
                    print(f"Skipping {person.company_name} as it is already enriched.")
                    continue
                    
                print(f"Enriching {person.company_name} (from person {person.name})...")
                
                location_param = {}
                if person.full_address:
                    location_param["address"] = person.full_address
                elif person.zip_code:
                    location_param["zip_code"] = person.zip_code
                elif person.city and person.state:
                    location_param["city"] = f"{person.city},{person.state}"
                else:
                    print(f"Skipping {person.name} as it has no address information.")
                    continue

                business_data = find_business_on_google_maps(person.company_name, location_param)
                
                if business_data:
                    enrichment_dir.mkdir(parents=True, exist_ok=True)
                    with open(google_maps_md_path, "w") as f_md:
                        f_md.write("---\n")
                        yaml.dump(business_data, f_md, sort_keys=False, default_flow_style=False, allow_unicode=True)
                        f_md.write("---\n")
                    print(f"Enriched data for {person.company_name} and saved to {google_maps_md_path}")
                else:
                    print(f"Could not find {person.company_name} on Google Maps.")
