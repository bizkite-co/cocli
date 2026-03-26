from pydantic import Field
from typing import ClassVar
from datetime import datetime
from ...base import BaseUsvModel, ResourcePathPolicy


class GmListVerifiedItem(BaseUsvModel):
    """
    User-verified gm-list data entry.
    Stores rating and review counts manually verified by the user from Google Maps.
    These entries take precedence over scraped data.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-03-24T00:00:00+00:00"
    RESOURCE_PATH_PATTERN: ClassVar[ResourcePathPolicy] = ResourcePathPolicy.SPECIFIC

    place_id: str = Field(
        ..., min_length=26, max_length=29, description="Google Place ID"
    )
    average_rating: float = Field(
        ..., ge=0.0, le=5.0, description="Verified average rating (0-5)"
    )
    reviews_count: int = Field(..., ge=0, description="Verified number of reviews")
    verified_at: str = Field(
        ..., description="ISO timestamp when the data was verified"
    )

    @classmethod
    def create(
        cls, place_id: str, average_rating: float, reviews_count: int
    ) -> "GmListVerifiedItem":
        """Factory method to create a verified item with current timestamp."""
        return cls(
            place_id=place_id,
            average_rating=average_rating,
            reviews_count=reviews_count,
            verified_at=datetime.utcnow().isoformat() + "Z",
        )
