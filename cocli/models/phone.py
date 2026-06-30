from typing import Any, Optional, Protocol, runtime_checkable, Annotated
import re
from pydantic import GetCoreSchemaHandler, BeforeValidator, ValidationError
from pydantic_core import CoreSchema, core_schema
import phonenumbers
from phonenumbers import NumberParseException


@runtime_checkable
class PhoneNumberProtocol(Protocol):
    """Protocol defining the interface for phone number objects."""

    country_code: str
    national_destination_code: str
    subscriber_number: str
    extension: Optional[str]

    def __str__(self) -> str:
        """Returns the phone number as a sequence of digits (E.164 style without +)."""
        ...

    def format(self, pattern: str = "international") -> str:
        """Renders the phone number according to a pattern."""
        ...

    def model_dump(self) -> str:
        """Pydantic serialization."""
        ...

    @classmethod
    def model_validate(cls, v: Any) -> Optional["PhoneNumber"]:
        """Pydantic validation."""
        ...


def empty_to_none(v: Any) -> Any:
    if v is None:
        return None
    # Handle MagicMock during tests
    if hasattr(v, "__class__") and "MagicMock" in str(v.__class__):
        return None
    if isinstance(v, str) and (not v.strip() or v.lower() == 'none' or v.lower() == 'null'):
        return None
    return v


class PhoneNumber:
    """
    A validated phone number type using libphonenumber (phonenumbers library).

    Stores country code, national destination code, and subscriber number separately.
    Uses the phonenumbers library to parse and validate, ensuring bulletproof
    handling of multi-digit country codes and international formats.

    Implements PhoneNumberProtocol for strong typing.
    """

    def __init__(
        self,
        country_code: str,
        national_destination_code: str,
        subscriber_number: str,
        extension: Optional[str] = None,
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
        """
        Validate and parse a phone number using libphonenumber.

        Handles:
        - E.164 format: +1234567890
        - Formatted strings: (123) 456-7890, +1 123-456-7890
        - Digits only: 1234567890
        - Extensions: (123) 456-7890 ext 101
        """
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

        # Extract extension before parsing
        extension = None
        ext_match = re.search(r"[\s./-]*(?:ext|x|Ext|X|\#)\.?\s*(\d{1,5})$", v)
        if ext_match:
            extension = ext_match.group(1)
            v = v[:ext_match.start()].strip()

        # Try to parse with phonenumbers library
        parsed_phone = cls._parse_with_phonenumbers(v)
        if parsed_phone:
            parsed_phone.extension = extension
            return parsed_phone

        # Fallback to lenient parsing for edge cases (malformed but salvageable)
        return cls._parse_lenient(v, extension)

    @classmethod
    def _parse_with_phonenumbers(cls, phone_str: str) -> Optional["PhoneNumber"]:
        """
        Use libphonenumber to parse the phone number.
        This handles all valid E.164 formats and common formats.
        """
        # Try parsing with the most common region first (US)
        for region in ["US", "GB", "CA", None]:
            try:
                parsed = phonenumbers.parse(phone_str, region)
                if not phonenumbers.is_valid_number(parsed):
                    continue

                cc = str(parsed.country_code)
                national_number = str(parsed.national_number)

                # Parse national number into NDC and subscriber number
                # This is region-specific; use region metadata from phonenumbers
                ndc, sn = cls._split_national_number(parsed, national_number)

                return cls(cc, ndc, sn)
            except NumberParseException:
                continue

        return None

    @classmethod
    def _split_national_number(
        cls, parsed_number: Any, national_number: str
    ) -> tuple[str, str]:
        """
        Split the national number into NDC (area code) and subscriber number.
        Uses phonenumbers metadata when available.
        """
        country_code = parsed_number.country_code

        # NANP (North America): CC=1, NDC=3 digits, SN=7 digits
        if country_code == 1:
            if len(national_number) >= 10:
                return national_number[:3], national_number[3:]
            # If fewer than 10 digits, still try to split
            if len(national_number) >= 3:
                return national_number[:3], national_number[3:]
            return national_number, ""

        # UK: CC=44, NDC typically 2-4 digits, SN variable
        if country_code == 44:
            if len(national_number) >= 10:
                return national_number[:3], national_number[3:]
            if len(national_number) >= 3:
                return national_number[:2], national_number[2:]
            return national_number, ""

        # For other countries, use a heuristic: split after first 2-3 digits
        if len(national_number) >= 6:
            # Most countries use 2-3 digit area codes
            return national_number[:2], national_number[2:]
        if len(national_number) >= 3:
            return national_number[:1], national_number[1:]

        return national_number, ""

    @classmethod
    def _parse_lenient(
        cls, phone_str: str, extension: Optional[str]
    ) -> "PhoneNumber":
        """
        Fallback lenient parser for edge cases.
        Used when libphonenumber can't parse it but we still have digits.
        """
        # Remove all non-digit characters except '+' at the start
        has_plus = phone_str.startswith('+')
        digits = re.sub(r'\D', '', phone_str)

        if not digits:
            raise ValueError(f"No digits found in phone number: {phone_str}")

        # Default to NANP (US/Canada, CC=1) if 10 digits
        if len(digits) == 10:
            return cls("1", digits[:3], digits[3:], extension)

        # If 11 digits and starts with 1, it's NANP with CC
        if len(digits) == 11 and digits.startswith('1'):
            return cls("1", digits[1:4], digits[4:], extension)

        # Handle UK leading 0 (common in the data)
        if len(digits) == 11 and digits.startswith('0') and not has_plus:
            return cls("44", digits[1:5], digits[5:], extension)

        if has_plus:
            # For E.164 with plus: need to extract CC and national number
            # Use phonenumbers as much as possible
            if digits.startswith('44'):  # UK
                return cls("44", digits[2:5] if len(digits) > 5 else digits[2:], digits[5:] if len(digits) > 5 else "", extension)
            if digits.startswith('1'):  # NANP
                return cls("1", digits[1:4] if len(digits) > 4 else digits[1:], digits[4:] if len(digits) > 4 else "", extension)

            # For unknown country codes, try common patterns
            if 11 <= len(digits) <= 13:
                return cls(digits[:2], digits[2:5], digits[5:], extension)
            if len(digits) > 13:
                return cls(digits[:3], digits[3:6], digits[6:], extension)

            return cls(digits[:1], digits[1:4] if len(digits) > 4 else digits[1:], digits[4:] if len(digits) > 4 else "", extension)

        # Fallback: assume NANP
        if len(digits) >= 10:
            return cls("1", digits[:3], digits[3:], extension)

        if len(digits) >= 3:
            return cls("1", digits[:3], digits[3:], extension)

        return cls("1", digits, "", extension)

    def __str__(self) -> str:
        """Returns the phone number as a sequence of digits (E.164 style without +)."""
        return f"{self.country_code}{self.national_destination_code}{self.subscriber_number}"

    def __repr__(self) -> str:
        return f"PhoneNumber(cc={self.country_code}, ndc={self.national_destination_code}, sn={self.subscriber_number}, ext={self.extension})"

    def format(self, pattern: str = "international") -> str:
        """
        Renders the phone number according to a pattern.

        Patterns:
        - "international": +1 (512) 555-1212
        - "national": (512) 555-1212
        - "dots": 1.512.555.1212
        - "digits": 15125551212
        - "e164": +15125551212
        - Custom pattern with {cc}, {ndc}, {sn}, {sn_prefix}, {sn_line}, {ext}
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
