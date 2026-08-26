from typing import Any, Optional, Protocol, runtime_checkable
import re
from pydantic import GetCoreSchemaHandler, BeforeValidator
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Annotated
from rich.text import Text


@runtime_checkable
class CompanyAddressProtocol(Protocol):
    """Protocol defining the interface for validated company addresses."""

    value: str

    def __str__(self) -> str:
        """Returns the normalized company address."""
        ...

    def model_dump(self) -> str:
        """Pydantic serialization."""
        ...

    @classmethod
    def model_validate(cls, v: Any) -> Optional["CompanyAddress"]:
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


def normalize_company_address(value: Any) -> str:
    """Strip CSV/scraper double-quotes and collapse whitespace.

    Shared by ``__init__`` and ``validate`` so DuckDB hydration cannot skip it.
    """
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value or value.lower() in ("none", "null"):
        raise ValueError("Empty company address")
    value = value.replace('"', "")
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        raise ValueError("Address is empty after quote removal")
    return value


class CompanyAddress:
    """
    A validated company address that removes CSV quote artifacts and normalizes whitespace.

    Handles:
    - Removal of double-quote characters (CSV artifact) - single-quotes are
      preserved since they're routinely real content in an address
    - Whitespace normalization (collapse multiple spaces)
    - Trimming of leading/trailing whitespace

    Implements CompanyAddressProtocol for strong typing.
    """

    def __init__(self, value: str):
        self.value = normalize_company_address(value)

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
    def validate(cls, v: Any) -> Optional["CompanyAddress"]:
        """
        Validate and normalize a company address.
        Removes quotes (CSV artifacts) and normalizes whitespace.
        """
        if v is None:
            return None
        if isinstance(v, cls):
            return v

        return cls(v)

    def __str__(self) -> str:
        """Returns the normalized company address."""
        return self.value

    def __repr__(self) -> str:
        return f"CompanyAddress({self.value!r})"

    def __eq__(self, other: Any) -> bool:
        """Support comparison with strings and other CompanyAddress objects."""
        if isinstance(other, CompanyAddress):
            return self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return False

    def __hash__(self) -> int:
        """Make hashable for use in sets/dicts."""
        return hash(self.value)

    def __rich__(self) -> Text:
        """Make Rich/Textual renderable."""
        return Text(self.value)

    def __getattr__(self, name: str) -> Any:
        """Delegate string methods to the underlying value."""
        # Avoid infinite recursion for special attributes
        if name.startswith('_'):
            raise AttributeError(f"'CompanyAddress' object has no attribute '{name}'")
        try:
            return getattr(self.value, name)
        except AttributeError:
            raise AttributeError(f"'CompanyAddress' object has no attribute '{name}'")

    def model_dump(self) -> str:
        """Used by Pydantic for serialization."""
        return self.value

    @classmethod
    def model_validate(cls, v: Any) -> Optional["CompanyAddress"]:
        """Compatibility with Pydantic v2 API."""
        return cls.validate(v)


OptionalCompanyAddress = Annotated[Optional[CompanyAddress], BeforeValidator(empty_to_none)]
