"""LocatedPlace / PostalAddress protocols.

A postal-code-free interface for anything that has a place on Earth: a
Company, a GoogleMapsPlace row, a prospect. The shared shape lets pipeline
code copy one location value between models without caring which model it
came from (task-agent: international-location-data-from-google-maps-detail-
scrapes; see cocli/models/company_address.py for the style this follows).

Do not make Company implement GoogleMapsPlaceProtocol: a company is not a
Maps row. Both models do implement LocatedPlace.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from .company_address import OptionalCompanyAddress


@runtime_checkable
class PostalAddress(Protocol):
    """The text part of a place, plus one postal-code spelling."""

    city: Optional[str]
    state: Optional[str]

    @property
    def postal_code(self) -> Optional[str]: ...


@runtime_checkable
class LocatedPlace(PostalAddress, Protocol):
    """Anything that stores one shared location value, copied via transform."""

    full_address: OptionalCompanyAddress
    street_address: OptionalCompanyAddress
    # ISO 3166-1 alpha-2 (e.g. "DK", never "Denmark")
    country: Optional[str]
    # IANA zone name (e.g. "Europe/Copenhagen")
    timezone: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
