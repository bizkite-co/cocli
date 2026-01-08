from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
from .email_address import EmailAddress

class EmailEntry(BaseModel):
    """
    Represents an entry in the campaign-specific email index.
    """
    email: EmailAddress
    domain: str
    company_slug: Optional[str] = None
    source: str  # e.g., "website_scraper", "shopify_import", "manual"
    found_at: datetime = Field(default_factory=datetime.utcnow)
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    verification_status: str = "unknown"
    tags: list[str] = Field(default_factory=list)
