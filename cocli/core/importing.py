import yaml
from typing import Optional, Set

from ..models.company import Company
from ..models.google_maps import GoogleMapsData
from ..core.utils import slugify
from ..core.config import get_companies_dir

def import_prospect(
    prospect_data: GoogleMapsData,
    existing_domains: Set[str],
    campaign: Optional[str] = None
) -> Optional[Company]:
    """
    Imports a single prospect from a GoogleMapsData object into the canonical company structure.

    Args:
        prospect_data: The GoogleMapsData object for the prospect.
        existing_domains: A set of domains that already exist in the CRM to prevent duplicates.
        campaign: The name of the campaign to associate with the prospect.

    Returns:
        The newly created Company object, or None if the prospect already exists.
    """
    domain = prospect_data.Domain
    if not domain or domain in existing_domains:
        return None

    # Map GoogleMapsData fields to Company fields
    company_data = {
        "name": prospect_data.Name,
        "domain": domain,
        "full_address": prospect_data.Full_Address,
        "phone_1": prospect_data.Phone_1,
        "website_url": prospect_data.Website,
        "categories": prospect_data.First_category.split(';') if prospect_data.First_category else [],
        "reviews_count": prospect_data.Reviews_count,
        "average_rating": prospect_data.Average_rating,
        "place_id": prospect_data.Place_ID,
    }

    # Create a slug from the domain
    slug = slugify(domain)
    company_dir = get_companies_dir() / slug
    company_dir.mkdir(exist_ok=True)

    # Add prospect and campaign tags
    tags = ["prospect"]
    if campaign:
        tags.append(campaign)
    tags_path = company_dir / "tags.lst"
    with open(tags_path, 'w') as tags_file:
        tags_file.write("\n".join(tags))

    # Create and save the main company file
    index_path = company_dir / "_index.md"
    # Filter out None values before dumping to YAML
    frontmatter = {
        key: value for key, value in company_data.items() if value is not None
    }
    
    with open(index_path, 'w') as index_file:
        index_file.write("---" + "\n")
        yaml.dump(frontmatter, index_file)
        index_file.write("---" + "\n")

    # Create a Company object to return
    # This is slightly redundant but completes the model-to-model transform
    company = Company.model_validate(company_data | {"slug": slug, "tags": tags})
    return company
