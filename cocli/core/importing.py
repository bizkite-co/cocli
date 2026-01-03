import yaml
from typing import Optional
import logging

from ..models.company import Company
from ..models.google_maps_prospect import GoogleMapsProspect
from ..core.config import get_companies_dir

logger = logging.getLogger(__name__)

def import_prospect(
    prospect_data: GoogleMapsProspect,
    campaign: Optional[str] = None
) -> Optional[Company]:
    """
    Imports a single prospect from a GoogleMapsProspect object into the canonical company structure.
    If the company already exists by slug, it updates relevant fields.
    Initializes enrichment tracking fields for new companies.

    Args:
        prospect_data: The GoogleMapsProspect object for the prospect.
        campaign: The name of the campaign to associate with the prospect.

    Returns:
        The newly created or updated Company object, or None if the prospect is a duplicate
        that doesn't require further processing here (e.g., domain already exists and
        company record is already sufficiently complete or up-to-date).
    """
    domain = prospect_data.Domain
    company_slug = prospect_data.company_slug # Use the slug from prospect_data

    # Essential check: must have a domain and a slug to proceed
    if not domain or not company_slug:
        logger.warning(f"Skipping import: Prospect missing domain or company_slug. Data: {prospect_data.model_dump()}")
        return None

    existing_company: Optional[Company] = None
    if company_slug:
        existing_company = Company.get(company_slug)
    
    if existing_company:
        # Company already exists. We should update its fields but not overwrite enrichment status.
        logger.debug(f"Company {company_slug} already exists. Updating its metadata from prospect data.")
        
        # Update fields that might be more accurate or new from Google Maps data
        existing_company.name = prospect_data.Name or existing_company.name
        existing_company.domain = prospect_data.Domain or existing_company.domain
        existing_company.full_address = prospect_data.Full_Address or existing_company.full_address
        existing_company.street_address = prospect_data.Street_Address or existing_company.street_address
        existing_company.city = prospect_data.City or existing_company.city
        existing_company.zip_code = prospect_data.Zip or existing_company.zip_code
        existing_company.state = prospect_data.State or existing_company.state
        existing_company.country = prospect_data.Country or existing_company.country
        existing_company.timezone = prospect_data.Timezone or existing_company.timezone
        existing_company.phone_1 = prospect_data.Phone_1 or existing_company.phone_1
        existing_company.website_url = prospect_data.Website or existing_company.website_url
        existing_company.place_id = prospect_data.Place_ID or existing_company.place_id
        existing_company.reviews_count = prospect_data.Reviews_count if prospect_data.Reviews_count is not None else existing_company.reviews_count
        existing_company.average_rating = prospect_data.Average_rating if prospect_data.Average_rating is not None else existing_company.average_rating
        
        # Merge categories (ensure no duplicates)
        new_categories = prospect_data.First_category.split(';') if prospect_data.First_category else []
        existing_company.categories = list(set(existing_company.categories + [cat.strip() for cat in new_categories if cat.strip()]))
        
        # Add tags
        new_tags = set(existing_company.tags)
        new_tags.add("prospect")
        if campaign:
            new_tags.add(campaign)
        existing_company.tags = list(new_tags)

        # Use new robust save method
        existing_company.save()
        return existing_company
    else:
        # Create new company
        company_data = {
            "name": prospect_data.Name,
            "domain": domain,
            "type": "Prospect",
            "slug": company_slug,
            "full_address": prospect_data.Full_Address,
            "street_address": prospect_data.Street_Address,
            "city": prospect_data.City,
            "zip_code": prospect_data.Zip,
            "state": prospect_data.State,
            "country": prospect_data.Country,
            "timezone": prospect_data.Timezone,
            "phone_1": prospect_data.Phone_1,
            "website_url": prospect_data.Website,
            "categories": prospect_data.First_category.split(';') if prospect_data.First_category else [],
            "reviews_count": prospect_data.Reviews_count,
            "average_rating": prospect_data.Average_rating,
            "place_id": prospect_data.Place_ID,
            "last_enriched": None,
            "enrichment_ttl_days": Company.model_fields["enrichment_ttl_days"].default
        }

        # Add initial tags
        tags = {"prospect"}
        if campaign:
            tags.add(campaign)
        company_data["tags"] = list(tags)

        # Filter out None values and validate
        filtered_company_data = {k: v for k, v in company_data.items() if v is not None}
        new_company = Company.model_validate(filtered_company_data)

        # Use new robust save method
        new_company.save()
        return new_company
