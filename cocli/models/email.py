from typing import Optional, Union, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, UTC
from .email_address import EmailAddress

class EmailEntry(BaseModel):
    """
    Represents an entry in the campaign-specific email index.
    """
    email: Union[EmailAddress, str] # Allow string fallback for legacy junk
    domain: str
    company_slug: Optional[str] = None
    source: str  # e.g., "website_scraper", "shopify_import", "manual"
    found_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
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

    def to_usv(self) -> str:
        """Serializes the entry to a USV line."""
        parts = [
            str(self.email),
            self.domain,
            self.company_slug or "",
            self.source,
            self.found_at.isoformat(),
            self.first_seen.isoformat(),
            self.last_seen.isoformat(),
            self.verification_status,
            ";".join(self.tags)
        ]
        from ..core.wal import US
        return US.join(parts) + "\n"

    @classmethod
    def from_usv(cls, usv_line: str) -> "EmailEntry":
        """Deserializes a USV line into an EmailEntry."""
        from ..core.wal import US
        parts = usv_line.strip().split(US)
        
        # Helper to parse dates safely
        def parse_dt(dt_str: str) -> datetime:
            try:
                return datetime.fromisoformat(dt_str)
            except Exception:
                return datetime.now(UTC)

        return cls(
            email=parts[0],
            domain=parts[1],
            company_slug=parts[2] if len(parts) > 2 and parts[2] else None,
            source=parts[3] if len(parts) > 3 else "unknown",
            found_at=parse_dt(parts[4]) if len(parts) > 4 else datetime.now(UTC),
            first_seen=parse_dt(parts[5]) if len(parts) > 5 else datetime.now(UTC),
            last_seen=parse_dt(parts[6]) if len(parts) > 6 else datetime.now(UTC),
            verification_status=parts[7] if len(parts) > 7 else "unknown",
            tags=parts[8].split(";") if len(parts) > 8 and parts[8] else []
        )
