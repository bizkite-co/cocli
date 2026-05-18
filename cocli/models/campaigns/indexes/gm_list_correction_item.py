from pydantic import Field
from typing import ClassVar
from datetime import datetime
from ...base import BaseUsvModel, ResourcePathPolicy


class GmListCorrectionItem(BaseUsvModel):
    """
    Field-level correction record for gm-list scraping audit.

    Stores every manual correction of a scraped field, recording
    what the original value was and what it was changed to.
    """

    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-03-27T00:00:00+00:00"
    RESOURCE_PATH_PATTERN: ClassVar[ResourcePathPolicy] = ResourcePathPolicy.SPECIFIC

    place_id: str = Field(
        ..., min_length=26, max_length=29, description="Google Place ID"
    )
    field_name: str = Field(..., description="Name of the field being corrected")
    original_value: str = Field("", description="Original scraped value")
    corrected_value: str = Field(..., description="Corrected value")
    corrected_by: str = Field("audit-validate", description="Operator who made the correction")
    corrected_at: str = Field(
        ..., description="ISO timestamp when the correction was made"
    )

    @classmethod
    def create(
        cls,
        place_id: str,
        field_name: str,
        original_value: str = "",
        corrected_value: str = "",
        corrected_by: str = "audit-validate",
    ) -> "GmListCorrectionItem":
        """Factory method with current timestamp."""
        return cls(
            place_id=place_id,
            field_name=field_name,
            original_value=original_value,
            corrected_value=corrected_value,
            corrected_by=corrected_by,
            corrected_at=datetime.utcnow().isoformat() + "Z",
        )
