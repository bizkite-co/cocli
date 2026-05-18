from pydantic import Field
from typing import ClassVar
from datetime import datetime
from ...base import BaseUsvModel, ResourcePathPolicy


class GmListAuditLogItem(BaseUsvModel):
    """
    Audit log entry for gm-list human-in-the-loop validation.
    Records each validation session metadata.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-03-27T00:00:00+00:00"
    RESOURCE_PATH_PATTERN: ClassVar[ResourcePathPolicy] = ResourcePathPolicy.SPECIFIC

    tile: str = Field(..., description="Grid tile coordinates")
    search_phrase: str = Field(..., description="Search phrase used")
    total_companies: int = Field(0, ge=0, description="Total companies in scrape")
    records_file: str = Field("", description="Source USV records file")
    usv_count: int = Field(0, ge=0, description="Number of records in USV")
    scraper_version: str = Field("unknown", description="Scraper version")
    logged_at: str = Field(
        ..., description="ISO timestamp when the entry was logged"
    )

    @classmethod
    def create(
        cls,
        tile: str,
        search_phrase: str,
        total_companies: int = 0,
        records_file: str = "",
        usv_count: int = 0,
        scraper_version: str = "unknown",
    ) -> "GmListAuditLogItem":
        """Factory method with current timestamp."""
        return cls(
            tile=tile,
            search_phrase=search_phrase,
            total_companies=total_companies,
            records_file=records_file,
            usv_count=usv_count,
            scraper_version=scraper_version,
            logged_at=datetime.utcnow().isoformat() + "Z",
        )
