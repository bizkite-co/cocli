import requests
import time
from typing import Optional, Dict, Any
import logging
import json
from pathlib import Path

from ..core.config import get_cocli_base_dir
from ..core.utils import slugify

logger = logging.getLogger(__name__)

def get_coordinates_from_zip(zip_code: str) -> Optional[Dict[str, float]]:
    """
    Retrieves latitude and longitude for a given zip code using Nominatim (OpenStreetMap).
    """
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    params: Dict[str, Any] = {
        "postalcode": zip_code,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
    }
    headers = {
        "User-Agent": "CompanyCLI/1.0 (https://github.com/yourusername/company-cli)"
    }

    for i in range(3):
        try:
            response = requests.get(NOMINATIM_URL, params=params, headers=headers)
            response.raise_for_status() # Raise an exception for HTTP errors
            data = response.json()

            if data:
                result = data[0]
                latitude = float(result["lat"])
                longitude = float(result["lon"])
                return {"latitude": latitude, "longitude": longitude}
            else:
                logger.warning(f"No coordinates found for zip code {zip_code} using Nominatim.")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error during Nominatim API request for zip code {zip_code}: {e}")
            if i < 2:
                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                return None
        except ValueError:
            logger.error(f"Could not parse coordinates for zip code {zip_code}.")
            return None
    return None

def get_coordinates_from_city_state(city_state: str) -> Optional[Dict[str, float]]:
    """
    Retrieves latitude and longitude for a given city and state using Nominatim (OpenStreetMap).
    Expected format: "City,State" (e.g., "Brea,CA").
    Results are cached locally.
    """
    cache_dir = get_cocli_base_dir() / "indexes" / "cities" / "proximity_to"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{slugify(city_state)}.json"

    # Check cache first
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                logger.info(f"Loading coordinates for '{city_state}' from cache.")
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not read cache file {cache_file}: {e}. Fetching from API.")

    # If not in cache or cache is invalid, fetch from API
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    params: Dict[str, Any] = {
        "q": city_state,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
    }
    headers = {
        "User-Agent": "CompanyCLI/1.0 (https://github.com/yourusername/company-cli)"
    }

    logger.info(f"Fetching coordinates for '{city_state}' from Nominatim API.")
    for i in range(3):
        try:
            response = requests.get(NOMINATIM_URL, params=params, headers=headers)
            response.raise_for_status() # Raise an exception for HTTP errors
            data = response.json()

            if data:
                result = data[0]
                latitude = float(result["lat"])
                longitude = float(result["lon"])
                coordinates = {"latitude": latitude, "longitude": longitude}
                
                # Save to cache
                try:
                    with open(cache_file, 'w') as f:
                        json.dump(coordinates, f)
                except IOError as e:
                    logger.error(f"Could not write to cache file {cache_file}: {e}")

                return coordinates
            else:
                logger.warning(f"No coordinates found for city/state {city_state} using Nominatim.")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error during Nominatim API request for city/state {city_state}: {e}")
            if i < 2:
                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                return None
        except ValueError:
            logger.error(f"Could not parse coordinates for city/state {city_state}.")
            return None
    return None

def get_coordinates_from_address(address: str) -> Optional[Dict[str, float]]:
    """
    Retrieves latitude and longitude for a given address using Nominatim (OpenStreetMap).
    """
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    params: Dict[str, Any] = {
        "q": address,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
    }
    headers = {
        "User-Agent": "CompanyCLI/1.0 (https://github.com/yourusername/company-cli)"
    }

    for i in range(3):
        try:
            response = requests.get(NOMINATIM_URL, params=params, headers=headers)
            response.raise_for_status() # Raise an exception for HTTP errors
            data = response.json()

            if data:
                result = data[0]
                latitude = float(result["lat"])
                longitude = float(result["lon"])
                return {"latitude": latitude, "longitude": longitude}
            else:
                logger.warning(f"No coordinates found for address {address} using Nominatim.")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error during Nominatim API request for address {address}: {e}")
            if i < 2:
                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                return None
        except ValueError:
            logger.error(f"Could not parse coordinates for address {address}.")
            return None
    return None