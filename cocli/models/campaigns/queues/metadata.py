from typing import Dict, List, Type
from pydantic import BaseModel
from .gm_list import ScrapeTask
from .gm_details import GmItemTask
from .enrichment import EnrichmentTask
from .to_call import ToCallTask
from ....core.ordinant import QueueName

class QueueMetadata(BaseModel):
    name: QueueName
    label: str
    description: str
    model_class: Type[BaseModel]
    from_models: List[str]
    to_models: List[str]
    from_property_map: Dict[str, str]  # Tech Name -> Descriptive Name
    to_property_map: Dict[str, str]    # Tech Name -> Descriptive Name
    sharding_strategy: str

QUEUES_METADATA: Dict[QueueName, QueueMetadata] = {
    "gm-list": QueueMetadata(
        name="gm-list",
        label="Google Maps Search",
        description="Geographic search areas to be scraped for company results. Acts as the entry point for geo-prospecting.",
        model_class=ScrapeTask,
        from_models=["CampaignConfig"],
        to_models=["ProspectIndex", "gm-details"],
        from_property_map={
            "queries": "List of search phrases (e.g. 'Flooring Contractor') to iterate over.",
            "locations": "Target cities, zip codes, or custom regions defined in the campaign.",
            "proximity": "The search radius in miles around each location center."
        },
        to_property_map={
            "latitude": "WGS84 Latitude coordinate for the center of the scrape tile.",
            "longitude": "WGS84 Longitude coordinate for the center of the scrape tile.",
            "zoom": "The Google Maps zoom level (usually 14-16) for appropriate density.",
            "tile_id": "Deterministic 0.1 degree grid identifier (e.g. '30.1_-97.5')."
        },
        sharding_strategy="geo_tile (latitude prefix)"
    ),
    "gm-details": QueueMetadata(
        name="gm-details",
        label="Google Maps Details",
        description="Individual Place IDs to be scraped for full business details. Bridges raw results to canonical company files.",
        model_class=GmItemTask,
        from_models=["gm-list", "ProspectIndex"],
        to_models=["Company", "enrichment"],
        from_property_map={
            "place_id": "The unique Google Maps identifier used to fetch place details API/web data.",
            "name": "The business name found during the initial list scrape.",
            "discovery_phrase": "The query that originally discovered this lead (for attribution)."
        },
        to_property_map={
            "Company.name": "The verified business name from the Place Detail result.",
            "Company.address": "Formatted physical address including street, city, state, and zip.",
            "Company.phone": "The primary business telephone number.",
            "Company.website": "The official business domain or landing page URL."
        },
        sharding_strategy="place_id (6th char)"
    ),
    "enrichment": QueueMetadata(
        name="enrichment",
        label="Website Enrichment",
        description="Domains to be scraped for emails, social links, and tech stacks. Deep-dives into digital footprint.",
        model_class=EnrichmentTask,
        from_models=["Company", "gm-details"],
        to_models=["Company", "EmailIndex", "DomainIndex"],
        from_property_map={
            "domain": "The target website domain to crawl.",
            "company_slug": "Internal identifier used to link enrichment data back to the company file."
        },
        to_property_map={
            "Company.email": "Primary and secondary email addresses found on the site.",
            "Company.socials": "Links to Facebook, Instagram, LinkedIn, and Twitter profiles.",
            "Company.tech_stack": "List of detected technologies (e.g. WordPress, Shopify, Google Analytics)."
        },
        sharding_strategy="domain (sha256 hash)"
    ),
    "to-call": QueueMetadata(
        name="to-call",
        label="To Call",
        description="High-priority leads ready for human outreach. Final stage of the enrichment pipeline.",
        model_class=ToCallTask,
        from_models=["Company", "enrichment"],
        to_models=["CRM", "SalesLog"],
        from_property_map={
            "company_slug": "Internal identifier for the target company.",
            "has_phone": "Boolean flag indicating if a valid phone number is available for calling.",
            "has_email": "Boolean flag indicating if a valid email is available for follow-up."
        },
        to_property_map={
            "Priority": "Numerical urgency score (1-5) based on lead quality.",
            "Reason": "Explains why this lead was enqueued (e.g. 'Highly Enriched').",
            "ContactHistory": "Previous outreach attempts and disposition logs."
        },
        sharding_strategy="None (Flat List)"
    )
}
