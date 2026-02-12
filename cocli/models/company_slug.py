import re
from typing import Annotated
from pydantic import StringConstraints

# CompanySlug must be at least 3 chars, alphanumeric with dashes.
# We allow up to 255 chars to support legacy long paths.
# New slugs should be truncated at the point of creation (e.g. using slugify(name, max_length=64))
CompanySlug = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=255,
        pattern=r"^[a-z0-9-]+$",
        strip_whitespace=True
    )
]

def to_company_slug(name: str, max_length: int = 64) -> str:
    """
    Utility to create a truncated CompanySlug from a string.
    """
    from ..core.text_utils import slugify
    return slugify(name, max_length=max_length)
