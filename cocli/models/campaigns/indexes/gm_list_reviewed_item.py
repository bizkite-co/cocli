from pydantic import Field
from typing import ClassVar
from datetime import datetime
from ...base import BaseUsvModel, ResourcePathPolicy


class GmListReviewedItem(BaseUsvModel):
    """
    User-reviewed gm-list data entry.
    Stores rating and review counts manually reviewed by the user from Google Maps.
    These entries take precedence over scraped data.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-03-24T00:00:00+00:00"
    RESOURCE_PATH_PATTERN: ClassVar[ResourcePathPolicy] = ResourcePathPolicy.SPECIFIC
    HEADER: ClassVar[bool] = True  # Write header row to USV files

    place_id: str = Field(
        ..., min_length=26, max_length=29, description="Google Place ID"
    )
    average_rating: float = Field(
        ..., ge=0.0, le=5.0, description="Reviewed average rating (0-5)"
    )
    reviews_count: int = Field(..., ge=0, description="Reviewed number of reviews")
    reviewed_at: str = Field(
        ..., description="ISO timestamp when the data was reviewed"
    )

    @classmethod
    def create(
        cls, place_id: str, average_rating: float, reviews_count: int
    ) -> "GmListReviewedItem":
        """Factory method to create a reviewed item with current timestamp."""
        return cls(
            place_id=place_id,
            average_rating=average_rating,
            reviews_count=reviews_count,
            reviewed_at=datetime.utcnow().isoformat() + "Z",
        )
