import typer
import csv
import logging
from typing_extensions import Annotated
from typing import Optional, Iterator, List

from pydantic import ValidationError

from cocli.models.company import Company
from cocli.models.hubspot import HubspotContactCsv
from cocli.core.config import get_campaign, get_campaigns_dir

app = typer.Typer()

logger = logging.getLogger(__name__)

def get_prospects(campaign: str, with_email: bool, city: Optional[str], state: Optional[str]) -> Iterator[Company]:
    """Yields companies that match the filter criteria."""
    for company in Company.get_all():
        if campaign in company.tags:
            if with_email and not company.email:
                continue
            if city and company.city != city:
                continue
            if state and company.state != state:
                continue
            yield company

@app.command("to-hubspot-csv")
def to_hubspot_csv(
    with_email: Annotated[bool, typer.Option("--with-email", help="Only include prospects with email addresses.")] = True,
    city: Annotated[Optional[str], typer.Option(help="Filter by city.")] = None,
    state: Annotated[Optional[str], typer.Option(help="Filter by state.")] = None,
):
    """
    Exports campaign prospects to a HubSpot CSV file.
    """
    campaign = get_campaign()
    if not campaign:
        print("No campaign set. Please set a campaign using `cocli campaign set <campaign_name>`.")
        raise typer.Exit(1)

    prospects = get_prospects(campaign, with_email, city, state)

    campaigns_dir = get_campaigns_dir()
    output_dir = campaigns_dir / campaign / "prospects" / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"hubspot_export_{campaign}.csv"
    exported_count = 0

    with open(output_file, "w", newline="") as csvfile:
        fieldnames = HubspotContactCsv.model_fields.keys()
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for prospect in prospects:
            try:
                contact = HubspotContactCsv(
                    company=prospect.name,
                    phone=prospect.phone_1,
                    website=prospect.website_url,
                    city=prospect.city,
                    state=prospect.state,
                    email=prospect.email,
                )
                writer.writerow(contact.model_dump())
                exported_count += 1
            except ValidationError as e:
                logger.warning(f"Skipping prospect {prospect.name} due to invalid data: {e}")

    print(f"Exported {exported_count} prospects to {output_file}")
