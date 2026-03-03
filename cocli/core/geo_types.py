from typing import ClassVar, TypeVar, Any
from pydantic import RootModel, field_validator

T = TypeVar("T", bound="GeoDegrees")

class GeoDegrees(RootModel[float]):
    """
    Base type for geographic coordinates with explicit precision.
    Ensures rounding happens at the moment of instantiation.
    """
    root: float
    DECIMALS: ClassVar[int] = 6

    @field_validator("root", mode="before")
    @classmethod
    def round_value(cls, v: Any) -> float:
        return round(float(v), cls.DECIMALS)

    def __str__(self) -> str:
        return f"{self.root:.{self.DECIMALS}f}"
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.root})"

    def __add__(self, other: float) -> float:
        return self.root + float(other)

    def __sub__(self, other: float) -> float:
        return self.root - float(other)

    def __float__(self) -> float:
        return self.root

class LatScale1(GeoDegrees):
    """1-decimal precision for sharding and Tile IDs (e.g. 25.0)."""
    DECIMALS = 1

class LonScale1(GeoDegrees):
    """1-decimal precision for sharding and Tile IDs (e.g. -79.9)."""
    DECIMALS = 1

class LatScale6(GeoDegrees):
    """6-decimal precision for high-fidelity business locations."""
    DECIMALS = 6

class LonScale6(GeoDegrees):
    """6-decimal precision for high-fidelity business locations."""
    DECIMALS = 6
