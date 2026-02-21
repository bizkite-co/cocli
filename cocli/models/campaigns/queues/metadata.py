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
    properties: List[str]
    sharding_strategy: str

QUEUES_METADATA: Dict[QueueName, QueueMetadata] = {
    "gm-list": QueueMetadata(
        name="gm-list",
        label="Google Maps Search",
        description="Geographic search areas to be scraped for company results.",
        model_class=ScrapeTask,
        from_models=["CampaignConfig"],
        to_models=["ProspectIndex", "gm-details"],
        properties=["latitude", "longitude", "zoom", "search_phrase", "tile_id"],
        sharding_strategy="geo_tile (latitude prefix)"
    ),
    "gm-details": QueueMetadata(
        name="gm-details",
        label="Google Maps Details",
        description="Individual Place IDs to be scraped for full business details.",
        model_class=GmItemTask,
        from_models=["gm-list", "ProspectIndex"],
        to_models=["Company", "enrichment"],
        properties=["place_id", "name", "company_slug", "discovery_phrase"],
        sharding_strategy="place_id (6th char)"
    ),
    "enrichment": QueueMetadata(
        name="enrichment",
        label="Website Enrichment",
        description="Domains to be scraped for emails, social links, and tech stacks.",
        model_class=EnrichmentTask,
        from_models=["Company", "gm-details"],
        to_models=["Company", "EmailIndex", "DomainIndex"],
        properties=["domain", "company_slug", "attempts", "last_enriched"],
        sharding_strategy="domain (sha256 hash)"
    ),
    "to-call": QueueMetadata(
        name="to-call",
        label="To Call",
        description="High-priority leads ready for human outreach.",
        model_class=ToCallTask,
        from_models=["Company", "enrichment"],
        to_models=["CRM", "SalesLog"],
        properties=["company_slug", "priority", "reason"],
        sharding_strategy="None (Flat List)"
    )
}
