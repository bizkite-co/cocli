from typing import Any, Optional
from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from cocli.core.text_utils import is_valid_email

class EmailAddress(str):
    """
    A custom Pydantic type for validated and normalized email addresses.
    """
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x) if x else None,
                when_used='always'
            )
        )

    @classmethod
    def validate(cls, v: str) -> Optional["EmailAddress"]:
        if not isinstance(v, str):
            if v is None:
                return None
            raise ValueError("Email must be a string")
        
        # Normalize
        normalized = v.strip().lower()
        if not normalized:
            return None
        
        # Remove common prefixes
        for prefix in ["email:", "mail:", "mailto:", "e-mail:"]:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):].strip()
                break
            
        # Validate
        if not is_valid_email(normalized):
            raise ValueError(f"Invalid email format or anomalous string: {v}")
            
        return cls(normalized)

    def __repr__(self) -> str:
        return f"EmailAddress({super().__repr__()})"
