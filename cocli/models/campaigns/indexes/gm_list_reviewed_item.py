from pydantic import Field
from typing import ClassVar
from ...base import BaseUsvModel, ResourcePathPolicy


class GmListReviewedItem(BaseUsvModel):
    """
    Field-level correction record for gm-list audit review.

    Stores each corrected field as a separate row with place_id,
    the field name, and the expected (corrected) value.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-03-28T00:00:00+00:00"
    RESOURCE_PATH_PATTERN: ClassVar[ResourcePathPolicy] = ResourcePathPolicy.SPECIFIC
    HEADER: ClassVar[bool] = True

    place_id: str = Field(
        ..., min_length=26, max_length=29, description="Google Place ID"
    )
    field_name: str = Field(
        ..., description="Name of the field being corrected"
    )
    expected: str = Field(
        ..., description="Expected (corrected) value for this field"
    )
