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
            "queries": "Search Phrases (e.g. 'Flooring Contractor')",
            "locations": "Target Cities/Regions",
            "proximity": "Search Radius (miles)"
        },
        to_property_map={
            "latitude": "WGS84 Latitude",
            "longitude": "WGS84 Longitude",
            "zoom": "Maps Zoom Level",
            "tile_id": "0.1 Degree Grid Tile ID"
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
            "place_id": "Google Place ID (Unique Anchor)",
            "name": "Business Name (Display)",
            "discovery_phrase": "Source Search Query"
        },
        to_property_map={
            "Company.name": "Canonical Business Name",
            "Company.address": "Verified Physical Address",
            "Company.phone": "Primary Business Phone",
            "Company.website": "Official Domain/URL"
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
            "domain": "Target Website Domain",
            "company_slug": "Internal ID Link"
        },
        to_property_map={
            "Company.email": "Found Email Addresses",
            "Company.socials": "FB/IG/LI Profiles",
            "Company.tech_stack": "Detected CMS/Trackers"
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
            "company_slug": "Internal ID Link",
            "has_phone": "Valid Phone Check",
            "has_email": "Valid Email Check"
        },
        to_property_map={
            "Priority": "Urgency Score (1-5)",
            "Reason": "Why they were enqueued",
            "ContactHistory": "Previous outreach logs"
        },
        sharding_strategy="None (Flat List)"
    )
}
