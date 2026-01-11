from typing import Optional, Union, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from .email_address import EmailAddress

class EmailEntry(BaseModel):
    """
    Represents an entry in the campaign-specific email index.
    """
    email: Union[EmailAddress, str] # Allow string fallback for legacy junk
    domain: str
    company_slug: Optional[str] = None
    source: str  # e.g., "website_scraper", "shopify_import", "manual"
    found_at: datetime = Field(default_factory=datetime.utcnow)
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    verification_status: str = "unknown"
    tags: list[str] = Field(default_factory=list)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_lenient(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return EmailAddress(v)
            except Exception:
                return v # Return as raw string if it fails validation
        return v
