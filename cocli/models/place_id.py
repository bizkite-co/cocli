from typing import Annotated
from pydantic import StringConstraints, AfterValidator

def validate_place_id(v: str) -> str:
    """
    Validates that the PlaceID does not start with 0x and does not contain colons.
    """
    if v.startswith("0x"):
        raise ValueError("PlaceID cannot start with '0x' (legacy format)")
    if ":" in v:
        raise ValueError("PlaceID cannot contain colons ':' (legacy format)")
    return v

# PlaceID must be at least 20 chars, no ':' and no '0x' prefix.
PlaceID = Annotated[
    str, 
    StringConstraints(min_length=20),
    AfterValidator(validate_place_id)
]
