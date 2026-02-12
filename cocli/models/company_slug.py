import re
from typing import Annotated, Any
from pydantic import StringConstraints, BeforeValidator

def normalize_company_slug(v: Any) -> str:
    """
    Strictly normalizes a string to match the CompanySlug pattern: ^[a-z0-9-]+$
    """
    if not v or not isinstance(v, str):
        return ""
    
    # 1. Lowercase and strip
    s = v.lower().strip()
    
    # 2. Replace common non-alphanumeric separators with dashes
    s = s.replace("/", "-").replace("_", "-").replace(".", "-")
    
    # 3. Remove all other characters that are not a-z, 0-9, or -
    s = re.sub(r"[^a-z0-9-]+", "", s)
    
    # 4. Collapse multiple dashes and strip from ends
    s = re.sub(r"-+", "-", s).strip("-")
    
    return s

# CompanySlug must be at least 3 chars, alphanumeric with dashes.
# We allow up to 255 chars to support legacy long paths.
# It uses a BeforeValidator to self-heal/normalize input data.
CompanySlug = Annotated[
    str,
    BeforeValidator(normalize_company_slug),
    StringConstraints(
        min_length=3,
        max_length=255,
        pattern=r"^[a-z0-9-]+$",
        strip_whitespace=True
    )
]

def to_company_slug(name: str, max_length: int = 64) -> str:
    """
    Utility to create a truncated, valid CompanySlug from a string.
    """
    from ..core.text_utils import slugify
    # Use slugify for initial pass (handles many edge cases)
    s = slugify(name)
    # Apply strict normalization
    s = normalize_company_slug(s)
    
    if max_length:
        s = s[:max_length].strip("-")
        
    return s
