from typing import Any
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
        )

    @classmethod
    def validate(cls, v: str) -> "EmailAddress":
        if not isinstance(v, str):
            raise ValueError("Email must be a string")
        
        # Normalize
        normalized = v.strip().lower()
        if normalized.startswith("email:"):
            normalized = normalized[6:].strip()
            
        # Validate
        if not is_valid_email(normalized):
            raise ValueError(f"Invalid email format or anomalous string: {v}")
            
        return cls(normalized)

    def __repr__(self) -> str:
        return f"EmailAddress({super().__repr__()})"
