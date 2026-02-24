# POLICY: frictionless-data-policy-enforcement
from datetime import datetime, UTC
from typing import Optional
from pydantic import Field
import uuid

from ...base import BaseUsvModel

class QueueMessage(BaseUsvModel):
    """
    Standard base for all sharded filesystem queue items.
    Inherits authoritative USV serialization from BaseUsvModel.
    """
    # Payload - Essential pointers (Required fields first)
    domain: str
    company_slug: str
    campaign_name: str

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: int = 1
    
    # Optional Metadata
    aws_profile_name: Optional[str] = None
    force_refresh: bool = False
    ttl_days: int = 30
    
    # Lifecycle Metadata
    attempts: int = 0
    http_500_attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
    # Transient field for queue adapters (e.g. SQS ReceiptHandle)
    ack_token: Optional[str] = Field(None, exclude=True)
