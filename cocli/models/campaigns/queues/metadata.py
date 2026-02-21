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
    from_model_name: str
    to_model_name: str
    from_models: List[str] # Restored
    to_models: List[str]   # Restored
    from_property_map: Dict[str, str]  # Tech Name -> Descriptive Name
    to_property_map: Dict[str, str]    # Tech Name -> Descriptive Name
    sharding_strategy: str

QUEUES_METADATA: Dict[QueueName, QueueMetadata] = {
    "gm-list": QueueMetadata(
        name="gm-list",
        label="Google Maps Search",
        description="Geographic search areas to be scraped for company results. Acts as the entry point for geo-prospecting.",
        model_class=ScrapeTask,
        from_model_name="cocli.models.campaigns.config.CampaignConfig",
        to_model_name="cocli.models.campaigns.queues.gm_list.ScrapeTask",
        from_models=["CampaignConfig"],
        to_models=["ProspectIndex", "gm-details"],
        from_property_map={
            "queries": "List of search phrases (e.g. 'Flooring Contractor') to iterate over.",
            "locations": "Target cities, zip codes, or custom regions defined in the campaign.",
            "proximity": "The search radius in miles around each location center.",
            "grid_size": "Step size for geographic tiling (default 0.1 deg)."
        },
        to_property_map={
            "latitude": "WGS84 Latitude coordinate for the center of the scrape tile.",
            "longitude": "WGS84 Longitude coordinate for the center of the scrape tile.",
            "zoom": "The Google Maps zoom level (usually 14-16) for appropriate density.",
            "search_phrase": "The specific query phrase used for this tile.",
            "tile_id": "Deterministic 0.1 degree grid identifier (e.g. '30.1_-97.5').",
            "radius_miles": "Approximate radius covered by this specific task.",
            "force_refresh": "If true, bypasses local witness index.",
            "ttl_days": "Time-to-live for the cached result."
        },
        sharding_strategy="geo_tile (latitude prefix)"
    ),
    "gm-details": QueueMetadata(
        name="gm-details",
        label="Google Maps Details",
        description="Individual Place IDs to be scraped for full business details. Bridges raw results to canonical company files.",
        model_class=GmItemTask,
        from_model_name="cocli.models.campaigns.queues.gm_list.ScrapeTask",
        to_model_name="cocli.models.campaigns.queues.gm_details.GmItemTask",
        from_models=["gm-list", "ProspectIndex"],
        to_models=["Company", "enrichment"],
        from_property_map={
            "place_id": "The unique Google Maps identifier found in the list results.",
            "name": "The business name found during the initial list scrape.",
            "discovery_phrase": "The query that originally discovered this lead.",
            "discovery_tile_id": "The geographic tile where this lead was found."
        },
        to_property_map={
            "place_id": "Unique anchor for Place Detail API/Web scraping.",
            "name": "The verified business name from the Detail result.",
            "company_slug": "Generated URL-safe slug for the company directory.",
            "force_refresh": "If true, forces a re-scrape of an existing Place ID.",
            "attempts": "Number of times this task has been tried."
        },
        sharding_strategy="place_id (6th char)"
    ),
    "enrichment": QueueMetadata(
        name="enrichment",
        label="Website Enrichment",
        description="Domains to be scraped for emails, social links, and tech stacks. Deep-dives into digital footprint.",
        model_class=EnrichmentTask,
        from_model_name="cocli.models.campaigns.queues.gm_details.GmItemTask",
        to_model_name="cocli.models.campaigns.queues.enrichment.EnrichmentTask",
        from_models=["gm-details"],
        to_models=["Company", "EmailIndex", "DomainIndex"],
        from_property_map={
            "domain": "The target website domain to crawl.",
            "company_slug": "Internal identifier used to link data back to the company file."
        },
        to_property_map={
            "id": "Unique UUID for the enrichment message.",
            "domain": "The primary domain being enriched.",
            "company_slug": "Pointer to data/companies/{slug}/.",
            "aws_profile_name": "Optional IAM profile for cloud workers.",
            "force_refresh": "Bypasses the 30-day enrichment cache.",
            "attempts": "Total retry count for this domain.",
            "http_500_attempts": "Specific tracking for server-side failures.",
            "created_at": "Initial enqueue timestamp.",
            "updated_at": "Last status update timestamp."
        },
        sharding_strategy="domain (sha256 hash)"
    ),
    "to-call": QueueMetadata(
        name="to-call",
        label="To Call",
        description="High-priority leads ready for human outreach. Final stage of the enrichment pipeline.",
        model_class=ToCallTask,
        from_model_name="cocli.models.companies.company.Company",
        to_model_name="cocli.models.campaigns.queues.to_call.ToCallTask",
        from_models=["Company", "enrichment"],
        to_models=["CRM", "SalesLog"],
        from_property_map={
            "company_slug": "Internal identifier for the target company.",
            "has_phone": "Boolean flag indicating if a valid phone number is available.",
            "has_email": "Boolean flag indicating if a valid email is available.",
            "tags": "List of tags (e.g. 'high-value') used for prioritization."
        },
        to_property_map={
            "company_slug": "Internal identifier for the target company.",
            "priority": "Numerical urgency score (1-5) based on lead quality.",
            "reason": "Explains why this lead was enqueued (e.g. 'Highly Enriched').",
            "created_at": "Timestamp when lead entered the outreach queue.",
            "enqueued_at": "Last move to 'pending' state."
        },
        sharding_strategy="None (Flat List)"
    )
}
