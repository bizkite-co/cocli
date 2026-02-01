from typing import Optional
import logging

from ..models.company import Company
from ..models.google_maps_prospect import GoogleMapsProspect

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
    domain = prospect_data.domain
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
        existing_company.name = prospect_data.name or existing_company.name
        existing_company.domain = prospect_data.domain or existing_company.domain
        existing_company.full_address = prospect_data.full_address or existing_company.full_address
        existing_company.street_address = prospect_data.street_address or existing_company.street_address
        existing_company.city = prospect_data.city or existing_company.city
        existing_company.zip_code = prospect_data.zip or existing_company.zip_code
        existing_company.state = prospect_data.state or existing_company.state
        existing_company.country = prospect_data.country or existing_company.country
        existing_company.timezone = prospect_data.timezone or existing_company.timezone
        existing_company.phone_1 = prospect_data.phone_1 or existing_company.phone_1
        existing_company.website_url = prospect_data.website or existing_company.website_url
        existing_company.place_id = prospect_data.place_id or existing_company.place_id
        existing_company.reviews_count = prospect_data.reviews_count if prospect_data.reviews_count is not None else existing_company.reviews_count
        existing_company.average_rating = prospect_data.average_rating if prospect_data.average_rating is not None else existing_company.average_rating
        
        # Merge categories (ensure no duplicates)
        new_categories = prospect_data.first_category.split(';') if prospect_data.first_category else []
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
            "name": prospect_data.name,
            "domain": domain,
            "type": "Prospect",
            "slug": company_slug,
            "full_address": prospect_data.full_address,
            "street_address": prospect_data.street_address,
            "city": prospect_data.city,
            "zip_code": prospect_data.zip,
            "state": prospect_data.state,
            "country": prospect_data.country,
            "timezone": prospect_data.timezone,
            "phone_1": prospect_data.phone_1,
            "website_url": prospect_data.website,
            "categories": prospect_data.first_category.split(';') if prospect_data.first_category else [],
            "reviews_count": prospect_data.reviews_count,
            "average_rating": prospect_data.average_rating,
            "place_id": prospect_data.place_id,
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
