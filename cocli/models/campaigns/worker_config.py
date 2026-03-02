# POLICY: frictionless-data-policy-enforcement
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

class WorkerDefinition(BaseModel):
    """Configuration for a specific worker instance on a node."""
    name: str = Field(..., description="Unique name for the worker (e.g. gm-list-1)")
    role: str = Field(..., description="Role of the worker: 'scraper', 'processor', or 'full'")
    content_type: str = Field(..., description="Specific content type: 'gm-list', 'gm-details', or 'enrichment'")
    workers: int = Field(1, description="Number of parallel worker threads/processes")
    iot_profile: Optional[str] = Field(None, description="Specific AWS IoT profile for least-privilege auth")

class PiNodeConfig(BaseModel):
    """Configuration for a specific Raspberry Pi node."""
    model_config = ConfigDict(populate_by_name=True)

    hostname: str = Field(..., alias="host", description="Node hostname (e.g. cocli5x1.pi)")
    ip_address: Optional[str] = Field(None, alias="ip")
    label: Optional[str] = None

    enabled: bool = True
    workers: List[WorkerDefinition] = Field(default_factory=list)
    
class CampaignClusterConfig(BaseModel):
    """Global cluster configuration for a campaign."""
    nodes: List[PiNodeConfig] = Field(default_factory=list)
    default_iot_profile: str = "roadmap-iot"
