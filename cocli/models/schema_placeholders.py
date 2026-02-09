import re
from pydantic import BaseModel, Field, field_validator

class SchemaPlaceholders(BaseModel):
    CAMPAIGN_NAME: str = Field(..., min_length=2, pattern=r"^[a-z0-9-]+$")
    SHARD_CHAR: str = Field(..., min_length=1, max_length=1, pattern=r"^[A-Za-z0-9]$")
    PLACE_ID: str = Field(..., min_length=10, pattern=r"^ChIJ[A-Za-z0-9_-]+$")
    LAT_SHARD: str = Field(..., pattern=r"^-?\d$")
    LAT_TENTH_DEGREE: str = Field(..., pattern=r"^-?\d+(\.\d)?$")
    LON_TENTH_DEGREE: str = Field(..., pattern=r"^-?\d+(\.\d)?$")
    SEARCH_SLUG: str = Field(..., pattern=r"^[a-z0-9-]+$")

    @classmethod
    def validate_placeholder(cls, placeholder_name: str, value: str) -> bool:
        if placeholder_name not in cls.model_fields:
            return False
        try:
            # Create a dynamic instance for validation
            data = {placeholder_name: value}
            # We bypass full model validation to check just one field
            field = cls.model_fields[placeholder_name]
            # Since Pydantic doesn't have a simple 'validate_field' without an instance,
            # we'll use a temporary partial model or just raw regex for the check.
            
            pattern = None
            for metadata in field.metadata:
                if hasattr(metadata, 'pattern'):
                    pattern = metadata.pattern
            
            if pattern:
                return bool(re.match(pattern, value))
            return True
        except Exception:
            return False
