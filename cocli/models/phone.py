from typing import Any, Optional, Annotated
import re
from pydantic import GetCoreSchemaHandler, BeforeValidator
from pydantic_core import CoreSchema, core_schema

def empty_to_none(v: Any) -> Any:
    if isinstance(v, str) and (not v.strip() or v.lower() == 'none' or v.lower() == 'null'):
        return None
    return v

class PhoneNumber:
    """
    A custom type for representing and validating phone numbers.
    Internally stores segments using international terminology.
    Serializes to a string of digits.
    """
    def __init__(
        self, 
        country_code: str, 
        national_destination_code: str, 
        subscriber_number: str, 
        extension: Optional[str] = None
    ):
        self.country_code = country_code
        self.national_destination_code = national_destination_code
        self.subscriber_number = subscriber_number
        self.extension = extension

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.union_schema([
                core_schema.none_schema(),
                core_schema.str_schema(),
                core_schema.dict_schema(),
                core_schema.is_instance_schema(cls),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x) if x else None,
                when_used='always'
            )
        )

    @classmethod
    def validate(cls, v: Any) -> Optional["PhoneNumber"]:
        if v is None:
            return None
        if isinstance(v, cls):
            return v
        
        if isinstance(v, dict):
            return cls(
                country_code=v["country_code"],
                national_destination_code=v["national_destination_code"],
                subscriber_number=v["subscriber_number"],
                extension=v.get("extension")
            )

        if not isinstance(v, str):
            v = str(v)

        v = v.strip()
        if not v or v.lower() == 'none' or v.lower() == 'null':
            raise ValueError("Empty phone number")

        # Handle extensions
        extension = None
        ext_match = re.search(r"[\s./-]*(?:ext|x|Ext|X|\#)\.?\s*(\d{1,5})$", v)
        if ext_match:
            extension = ext_match.group(1)
            v = v[:ext_match.start()]

        # Remove all non-digit characters except '+' at the start
        has_plus = v.startswith('+')
        digits = re.sub(r'\D', '', v)
        
        if not digits:
            raise ValueError(f"No digits found in phone number: {v}")

        # Default to NANP (US/Canada) if 10 digits and doesn't start with 0/1
        if len(digits) == 10 and not has_plus and digits[0] not in '01':
            return cls("1", digits[:3], digits[3:], extension)
        
        # If 11 digits and starts with 1, it's NANP with CC
        if len(digits) == 11 and digits.startswith('1'):
            return cls("1", digits[1:4], digits[4:], extension)

        # Handle UK leading 0 (common in the data)
        if len(digits) == 11 and digits.startswith('0') and not has_plus:
            # Convert 0XXXXXXXXXX to 44XXXXXXXXXX
            return cls("44", digits[1:5], digits[5:], extension)

        if has_plus:
            # Heuristic for common CCs
            if digits.startswith('44'): # UK
                # UK NDC can be 2, 3, or 4 digits. Let's guess 4 for mobile/common.
                return cls("44", digits[2:6], digits[6:], extension)
            if digits.startswith('1'): # NANP
                return cls("1", digits[1:4], digits[4:], extension)
            
            # For others, if we have 11-13 digits, guess 2-digit CC
            if 11 <= len(digits) <= 13:
                return cls(digits[:2], digits[2:5], digits[5:], extension)
            # Guess 3-digit CC
            if len(digits) > 13:
                return cls(digits[:3], digits[3:6], digits[6:], extension)
            
            return cls(digits[:1], digits[1:4], digits[4:], extension)

        # Final fallback: assume NANP if 10 digits even if it starts with 0/1 (risky but common)
        if len(digits) == 10:
            return cls("1", digits[:3], digits[3:], extension)
            
        return cls("1", digits[:3] if len(digits) > 3 else digits, digits[3:] if len(digits) > 3 else "", extension)

    def __str__(self) -> str:
        """Returns the phone number as a sequence of digits (E.164 style without +)."""
        return f"{self.country_code}{self.national_destination_code}{self.subscriber_number}"

    def __repr__(self) -> str:
        return f"PhoneNumber(cc={self.country_code}, ndc={self.national_destination_code}, sn={self.subscriber_number}, ext={self.extension})"

    def format(self, pattern: str = "international") -> str:
        """
        Renders the phone number according to a pattern.
        """
        cc = self.country_code
        ndc = self.national_destination_code
        sn = self.subscriber_number
        
        # Split SN for NANP style if it's 7 digits
        sn_prefix = sn[:3] if len(sn) >= 3 else sn
        sn_line = sn[3:] if len(sn) >= 3 else ""

        if pattern == "international":
            base = f"+{cc} ({ndc}) {sn_prefix}-{sn_line}"
            return f"{base} ext {self.extension}" if self.extension else base
        elif pattern == "national":
            base = f"({ndc}) {sn_prefix}-{sn_line}"
            return f"{base} ext {self.extension}" if self.extension else base
        elif pattern == "dots":
            return f"{cc}.{ndc}.{sn_prefix}.{sn_line}"
        elif pattern == "digits":
            return str(self)
        elif pattern == "e164":
            return f"+{str(self)}"
        
        # Custom pattern replacement
        res = pattern.replace("{cc}", cc).replace("{ndc}", ndc).replace("{sn}", sn)
        res = res.replace("{sn_prefix}", sn_prefix).replace("{sn_line}", sn_line)
        if self.extension:
            res = res.replace("{ext}", self.extension)
        else:
            res = res.replace("{ext}", "")
        return res

    def model_dump(self) -> str:
        """Used by Pydantic for serialization."""
        return str(self)
    
    @classmethod
    def model_validate(cls, v: Any) -> Optional["PhoneNumber"]:
        """Compatibility with Pydantic v2 API."""
        return cls.validate(v)

OptionalPhone = Annotated[Optional[PhoneNumber], BeforeValidator(empty_to_none)]
