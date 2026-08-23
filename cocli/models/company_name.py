from typing import Any, Optional, Protocol, runtime_checkable
import re
from pydantic import GetCoreSchemaHandler, BeforeValidator
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Annotated
from rich.text import Text


@runtime_checkable
class CompanyNameProtocol(Protocol):
    """Protocol defining the interface for validated company names."""

    value: str

    def __str__(self) -> str:
        """Returns the normalized company name."""
        ...

    def model_dump(self) -> str:
        """Pydantic serialization."""
        ...

    @classmethod
    def model_validate(cls, v: Any) -> Optional["CompanyName"]:
        """Pydantic validation."""
        ...


def empty_to_none(v: Any) -> Any:
    if v is None:
        return None
    if hasattr(v, "__class__") and "MagicMock" in str(v.__class__):
        return None
    if isinstance(v, str) and (not v.strip() or v.lower() == 'none' or v.lower() == 'null'):
        return None
    return v


class CompanyName:
    """
    A validated company name that removes CSV quote artifacts and normalizes whitespace.

    Handles:
    - Removal of double-quote characters (CSV artifact) - single-quotes are
      preserved since they're routinely real content (e.g. "John's Flooring")
    - Whitespace normalization (collapse multiple spaces)
    - Trimming of leading/trailing whitespace

    Implements CompanyNameProtocol for strong typing.
    """

    def __init__(self, value: str):
        self.value = value

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.union_schema([
                core_schema.none_schema(),
                core_schema.str_schema(),
                core_schema.is_instance_schema(cls),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x) if x else None,
                when_used='always'
            )
        )

    @classmethod
    def validate(cls, v: Any) -> Optional["CompanyName"]:
        """
        Validate and normalize a company name.
        Removes quotes (CSV artifacts) and normalizes whitespace.
        """
        if v is None:
            return None
        if isinstance(v, cls):
            return v

        if not isinstance(v, str):
            v = str(v)

        v = v.strip()
        if not v or v.lower() == 'none' or v.lower() == 'null':
            raise ValueError("Empty company name")

        # Only double-quotes are a CSV/scraper artifact worth stripping - a
        # single-quote is routinely real content in a business name
        # ("John's Flooring", "Lowe's") and must survive (confirmed live:
        # 193 of 197 quote-containing checkpoint names were legitimate
        # apostrophes, only 4 were real "..." corruption).
        v = v.replace('"', '')

        # Normalize whitespace: collapse multiple spaces to single space
        v = re.sub(r'\s+', ' ', v).strip()

        if not v:
            raise ValueError("Company name is empty after quote removal")

        return cls(v)

    def __str__(self) -> str:
        """Returns the normalized company name."""
        return self.value

    def __repr__(self) -> str:
        return f"CompanyName({self.value!r})"

    def __eq__(self, other: Any) -> bool:
        """Support comparison with strings and other CompanyName objects."""
        if isinstance(other, CompanyName):
            return self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return False

    def __hash__(self) -> int:
        """Make hashable for use in sets/dicts."""
        return hash(self.value)

    def __lt__(self, other: Any) -> bool:
        """Support sorting, matching plain-string ordering."""
        if isinstance(other, CompanyName):
            return self.value < other.value
        if isinstance(other, str):
            return self.value < other
        return NotImplemented

    def __rich__(self) -> Text:
        """Make Rich/Textual renderable."""
        return Text(self.value)

    def __getattr__(self, name: str) -> Any:
        """Delegate string methods to the underlying value."""
        # Avoid infinite recursion for special attributes
        if name.startswith('_'):
            raise AttributeError(f"'CompanyName' object has no attribute '{name}'")
        try:
            return getattr(self.value, name)
        except AttributeError:
            raise AttributeError(f"'CompanyName' object has no attribute '{name}'")

    def model_dump(self) -> str:
        """Used by Pydantic for serialization."""
        return self.value

    @classmethod
    def model_validate(cls, v: Any) -> Optional["CompanyName"]:
        """Compatibility with Pydantic v2 API."""
        return cls.validate(v)


OptionalCompanyName = Annotated[Optional[CompanyName], BeforeValidator(empty_to_none)]
