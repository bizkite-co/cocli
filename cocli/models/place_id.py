from typing import Annotated
from pydantic import StringConstraints

# PlaceID must be at least 20 chars, no ':' and no '0x' prefix.
PlaceID = Annotated[
    str, 
    StringConstraints(
        min_length=20, 
        pattern=r"^(?!0x)[^:]+$"
    )
]
