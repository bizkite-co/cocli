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

# Define a custom Pydantic type for UTC-aware datetimes
AwareDatetime = Annotated[
    datetime,
    AfterValidator(validate_aware_datetime),
    PlainSerializer(lambda x: x.isoformat(), return_type=str, when_used='unless-none')
]