import re
from datetime import datetime, UTC
from typing import Annotated
from pydantic import PlainSerializer, AfterValidator

def validate_aware_datetime(v: datetime) -> datetime:
    """
    Validator for timezone-aware datetimes, ensuring they are in UTC.
    If a naive datetime is provided, it is assumed to be in UTC.
    """
    if v.tzinfo is None:
        return v.replace(tzinfo=UTC)
    if v.tzinfo != UTC:
        # Convert to UTC if it's aware but not UTC
        return v.astimezone(UTC)
    return v

def validate_place_id(v: str) -> str:
    """
    Validator for Google Place IDs.
    Place IDs are typically ~27 characters and can include alphanumeric, 
    underscores, hyphens, and colons.
    """
    if not v or not isinstance(v, str):
        raise ValueError("Place ID must be a non-empty string")
    
    # Basic sanity check for common Place ID characters
    if not re.match(r"^[A-Za-z0-9_\-:]+$", v):
        raise ValueError(f"Invalid characters in Place ID: {v}")
    
    return v

# Define a custom Pydantic type for Place IDs
PlaceID = Annotated[
    str,
    AfterValidator(validate_place_id),
]

# Define a custom Pydantic type for UTC-aware datetimes
AwareDatetime = Annotated[
    datetime,
    AfterValidator(validate_aware_datetime),
    PlainSerializer(lambda x: x.isoformat(), return_type=str, when_used='unless-none')
]