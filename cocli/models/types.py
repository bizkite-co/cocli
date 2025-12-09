from datetime import datetime, UTC
from typing import Annotated

from pydantic import PlainSerializer, BeforeValidator
from pydantic_core import PydanticCustomError

def validate_aware_datetime(v: datetime) -> datetime:
    """
    Validator for timezone-aware datetimes, ensuring they are in UTC.
    """
    if v.tzinfo is None:
        raise PydanticCustomError(
            'datetime_timezone_naive', 'timezone-naive datetimes are not allowed'
        )
    if v.tzinfo != UTC:
        # Convert to UTC if it's aware but not UTC
        return v.astimezone(UTC)
    return v

# Define a custom Pydantic type for UTC-aware datetimes
AwareDatetime = Annotated[
    datetime,
    BeforeValidator(validate_aware_datetime),
    PlainSerializer(lambda x: x.isoformat(), return_type=str, when_used='unless-none')
]
