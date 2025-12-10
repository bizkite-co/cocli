import yaml
from typing import Optional
import logging

from ..models.company import Company
from ..models.google_maps import GoogleMapsData
from ..core.config import get_companies_dir

logger = logging.getLogger(__name__)

def import_prospect(
    prospect_data: GoogleMapsData,
    campaign: Optional[str] = None
) -> Optional[Company]:
    """
    Imports a single prospect from a GoogleMapsData object into the canonical company structure.
    If the company already exists by slug, it updates relevant fields.
    Initializes enrichment tracking fields for new companies.

    Args:
        prospect_data: The GoogleMapsData object for the prospect.
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
        # This is where we define what fields are updated from new prospect data.
        logger.debug(f"Company {company_slug} already exists. Updating its metadata from prospect data.")
        
        # Update fields that might be more accurate or new from Google Maps data
        existing_company.name = prospect_data.Name or existing_company.name
        existing_company.domain = prospect_data.Domain or existing_company.domain # Should be same as original but for safety
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
        
        # Save updated company
        company_dir = get_companies_dir() / company_slug
        company_dir.mkdir(exist_ok=True) # Ensure directory exists
        index_path = company_dir / "_index.md"

        with open(index_path, 'w') as index_file:
            index_file.write("---" + "\n")
            yaml.dump(existing_company.model_dump(exclude_none=True), index_file, sort_keys=False) # Dump model directly
            index_file.write("---" + "\n")
        
        # Also ensure tags are merged/updated if necessary.
        tags_path = company_dir / "tags.lst"
        current_tags = set()
        if tags_path.exists():
            current_tags.update(tags_path.read_text().strip().split('\n'))
        
        new_tags_to_add = ["prospect"]
        if campaign:
            new_tags_to_add.append(campaign)
        current_tags.update(new_tags_to_add)

        with open(tags_path, 'w') as tags_file:
            tags_file.write("\n".join(sorted(list(current_tags)))) # Write sorted unique tags
        
        return existing_company
    else:
        # Create new company
        company_data = {
            "name": prospect_data.Name,
            "domain": domain,
            "type": "Prospect", # Default type for new prospects
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
            "last_enriched": None, # New company, not yet enriched
            "enrichment_ttl_days": Company.model_fields["enrichment_ttl_days"].default # Use model default
        }

        # Filter out None values from company_data before passing to model_validate
        # This ensures pydantic doesn't complain about Optional fields if their values are explicitly None
        filtered_company_data = {k: v for k, v in company_data.items() if v is not None}

        # Create Company object
        new_company = Company.model_validate(filtered_company_data)

        # Ensure directory exists and save
        company_dir = get_companies_dir() / new_company.slug
        company_dir.mkdir(exist_ok=True)
        index_path = company_dir / "_index.md"

        with open(index_path, 'w') as index_file:
            index_file.write("---" + "\n")
            yaml.dump(new_company.model_dump(exclude_none=True), index_file, sort_keys=False) # Dump model directly
            index_file.write("---" + "\n")

        # Add prospect and campaign tags
        tags = ["prospect"]
        if campaign:
            tags.append(campaign)
        tags_path = company_dir / "tags.lst"
        with open(tags_path, 'w') as tags_file:
            tags_file.write("\n".join(tags))
        
        return new_company
