from datetime import datetime, UTC
from typing import Optional
from pydantic import BaseModel, Field
import uuid

class QueueMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: int = 1
    
    # Payload - Essential pointers
    domain: str
    company_slug: str
    campaign_name: str
    
    # Optional Metadata
    aws_profile_name: Optional[str] = None
    force_refresh: bool = False
    ttl_days: int = 30
    
    # Lifecycle Metadata
    attempts: int = 0
    http_500_attempts: int = 0 # New field to track 500 errors specifically
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
    # Transient field for queue adapters (e.g. SQS ReceiptHandle)
    ack_token: Optional[str] = Field(None, exclude=True)
