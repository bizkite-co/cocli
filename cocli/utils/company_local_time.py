"""Resolve a company's local timezone and format the current time there."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tzlocal import get_localzone


_ABBREV_TO_ZONE = {
    "PT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "MT": "America/Denver",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "CT": "America/Chicago",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "ET": "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "AKT": "America/Anchorage",
    "AKST": "America/Anchorage",
    "AKDT": "America/Anchorage",
    "HT": "Pacific/Honolulu",
    "HST": "Pacific/Honolulu",
    "HAST": "Pacific/Honolulu",
}

_STATE_TO_ZONE = {
    "AL": "America/Chicago",
    "AK": "America/Anchorage",
    "AZ": "America/Phoenix",
    "AR": "America/Chicago",
    "CA": "America/Los_Angeles",
    "CO": "America/Denver",
    "CT": "America/New_York",
    "DE": "America/New_York",
    "DC": "America/New_York",
    "FL": "America/New_York",
    "GA": "America/New_York",
    "HI": "Pacific/Honolulu",
    "ID": "America/Boise",
    "IL": "America/Chicago",
    "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago",
    "KS": "America/Chicago",
    "KY": "America/New_York",
    "LA": "America/Chicago",
    "ME": "America/New_York",
    "MD": "America/New_York",
    "MA": "America/New_York",
    "MI": "America/Detroit",
    "MN": "America/Chicago",
    "MS": "America/Chicago",
    "MO": "America/Chicago",
    "MT": "America/Denver",
    "NE": "America/Chicago",
    "NV": "America/Los_Angeles",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NM": "America/Denver",
    "NY": "America/New_York",
    "NC": "America/New_York",
    "ND": "America/Chicago",
    "OH": "America/New_York",
    "OK": "America/Chicago",
    "OR": "America/Los_Angeles",
    "PA": "America/New_York",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "SD": "America/Chicago",
    "TN": "America/Chicago",
    "TX": "America/Chicago",
    "UT": "America/Denver",
    "VT": "America/New_York",
    "VA": "America/New_York",
    "WA": "America/Los_Angeles",
    "WV": "America/New_York",
    "WI": "America/Chicago",
    "WY": "America/Denver",
}

_STATE_NAMES = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

# Used when city is known but state/zip are not. Split-state cities that
# disagree with the state's majority zone also live here (El Paso).
_CITY_TO_ZONE = {
    "dallas": "America/Chicago",
    "fort worth": "America/Chicago",
    "houston": "America/Chicago",
    "austin": "America/Chicago",
    "san antonio": "America/Chicago",
    "el paso": "America/Denver",
    "chicago": "America/Chicago",
    "new york": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "phoenix": "America/Phoenix",
    "denver": "America/Denver",
    "seattle": "America/Los_Angeles",
    "portland": "America/Los_Angeles",
    "miami": "America/New_York",
    "atlanta": "America/New_York",
    "boston": "America/New_York",
    "philadelphia": "America/New_York",
}

_CITY_STATE_ZIP_RE = re.compile(
    r"(?P<city>[A-Za-z][A-Za-z .'-]{1,40}),\s*"
    r"(?P<state>[A-Z]{2}|[A-Za-z]{4,20})\s+"
    r"(?P<zip>\d{5})(?:-\d{4})?"
)
_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


@dataclass(frozen=True)
class CompanyPlace:
    tz: tzinfo
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None

    def place_label(self) -> str:
        city = (self.city or "").strip()
        state = (self.state or "").strip()
        if city and state:
            return f"{city}, {state}"
        return city or state or "company local"


def normalize_state(state: Optional[str]) -> Optional[str]:
    if not state:
        return None
    raw = state.strip()
    if not raw:
        return None
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()
    return _STATE_NAMES.get(raw.lower())


def extract_us_location(*texts: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Pull (city, state, zip) out of free-text address fragments."""
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    for text in texts:
        if not text:
            continue
        blob = str(text)
        match = _CITY_STATE_ZIP_RE.search(blob)
        if match:
            city = city or match.group("city").strip()
            state = state or normalize_state(match.group("state"))
            zip_code = zip_code or match.group("zip")
        if zip_code is None:
            zip_match = _ZIP_RE.search(blob)
            if zip_match:
                zip_code = zip_match.group(1)
        if state is None:
            for name, abbr in _STATE_NAMES.items():
                if re.search(rf"\b{re.escape(name)}\b", blob, re.IGNORECASE):
                    state = abbr
                    break
        if city is None:
            lowered = blob.lower()
            for name in _CITY_TO_ZONE:
                if re.search(rf"\b{re.escape(name)}\b", lowered):
                    city = name.title()
                    break
    return city, state, zip_code


def _zoneinfo(name: str) -> Optional[ZoneInfo]:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return None


def _zip_to_zone(zip_code: str) -> Optional[str]:
    digits = re.sub(r"\D", "", zip_code)
    if len(digits) < 5:
        return None
    if digits.startswith("799"):
        return "America/Denver"
    if digits.startswith(("967", "968")):
        return "Pacific/Honolulu"
    if digits.startswith(("995", "996", "997", "998", "999")):
        return "America/Anchorage"
    first = int(digits[0])
    if first <= 4:
        return "America/New_York"
    if first <= 7:
        return "America/Chicago"
    if first == 8:
        return "America/Denver"
    return "America/Los_Angeles"


def _lng_to_us_zone(latitude: float, longitude: float) -> Optional[str]:
    if latitude < 24 or latitude > 50 or longitude > -66 or longitude < -170:
        return None
    if longitude < -125:
        return "America/Anchorage" if latitude > 50 else "Pacific/Honolulu"
    if longitude < -115:
        return "America/Los_Angeles"
    if longitude < -104:
        return "America/Denver"
    if longitude < -85.5:
        return "America/Chicago"
    return "America/New_York"


def resolve_company_place(
    timezone_name: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    zip_code: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    address_text: Optional[str] = None,
) -> CompanyPlace:
    """Best-effort place: explicit TZ, then zip/city/state/coords/address, then local."""
    parsed_city, parsed_state, parsed_zip = extract_us_location(address_text)
    city = (city or parsed_city or None)
    state_code = normalize_state(state) or parsed_state
    zip_code = zip_code or parsed_zip

    zone: Optional[ZoneInfo] = None
    if timezone_name:
        raw = timezone_name.strip()
        mapped = _ABBREV_TO_ZONE.get(raw.upper())
        zone = _zoneinfo(mapped or raw)

    if zone is None and zip_code:
        zname = _zip_to_zone(zip_code)
        zone = _zoneinfo(zname) if zname else None

    if zone is None and city:
        zname = _CITY_TO_ZONE.get(city.strip().lower())
        zone = _zoneinfo(zname) if zname else None

    if zone is None and state_code:
        zname = _STATE_TO_ZONE.get(state_code)
        zone = _zoneinfo(zname) if zname else None

    if (
        zone is None
        and latitude is not None
        and longitude is not None
    ):
        zname = _lng_to_us_zone(float(latitude), float(longitude))
        zone = _zoneinfo(zname) if zname else None

    if zone is None:
        zone_tz: tzinfo = get_localzone()
    else:
        zone_tz = zone

    display_city = city.title() if city else None
    return CompanyPlace(tz=zone_tz, city=display_city, state=state_code, zip_code=zip_code)


def resolve_company_tz(
    timezone_name: Optional[str] = None, state: Optional[str] = None
) -> tzinfo:
    """Best-effort tz for a company: explicit IANA/abbrev, then US state, then local."""
    return resolve_company_place(timezone_name=timezone_name, state=state).tz


def format_company_local_now(
    timezone_name: Optional[str] = None,
    state: Optional[str] = None,
    *,
    city: Optional[str] = None,
    zip_code: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    address_text: Optional[str] = None,
    place: Optional[CompanyPlace] = None,
) -> str:
    """Current local time, e.g. 'Fri 2:34:12 PM CDT'."""
    resolved = place or resolve_company_place(
        timezone_name=timezone_name,
        state=state,
        city=city,
        zip_code=zip_code,
        latitude=latitude,
        longitude=longitude,
        address_text=address_text,
    )
    now = datetime.now(resolved.tz)
    hour = now.strftime("%I").lstrip("0") or "12"
    zone = now.strftime("%Z") or (resolved.tz.key if hasattr(resolved.tz, "key") else "")
    stamp = f"{now.strftime('%a')} {hour}:{now.strftime('%M:%S %p')}"
    return f"{stamp} {zone}".strip()
