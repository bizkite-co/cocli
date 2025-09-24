import requests
from typing import Optional, Dict, Any

def get_coordinates_from_zip(zip_code: str) -> Optional[Dict[str, float]]:
    """
    Retrieves latitude and longitude for a given zip code using Nominatim (OpenStreetMap).
    """
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    params = {
        "postalcode": zip_code,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
    }
    headers = {
        "User-Agent": "CompanyCLI/1.0 (https://github.com/yourusername/company-cli)"
    } # Replace with your project's info

    try:
        response = requests.get(NOMINATIM_URL, params=params, headers=headers)
        response.raise_for_status() # Raise an exception for HTTP errors
        data = response.json()

        if data:
            # Nominatim returns a list of results, take the first one
            result = data[0]
            latitude = float(result["lat"])
            longitude = float(result["lon"])
            return {"latitude": latitude, "longitude": longitude}
        else:
            print(f"No coordinates found for zip code {zip_code} using Nominatim.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error during Nominatim API request for zip code {zip_code}: {e}")
        return None

def get_coordinates_from_city_state(city_state: str) -> Optional[Dict[str, float]]:
    """
    Retrieves latitude and longitude for a given city and state using Nominatim (OpenStreetMap).
    Expected format: "City,State" (e.g., "Brea,CA").
    """
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": city_state,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
    }
    headers = {
        "User-Agent": "CompanyCLI/1.0 (https://github.com/yourusername/company-cli)"
    }

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
            print(f"No coordinates found for city/state {city_state} using Nominatim.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error during Nominatim API request for city/state {city_state}: {e}")
        return None
    except ValueError:
        print(f"Could not parse coordinates for city/state {city_state}.")
        return None
    except ValueError:
        print(f"Could not parse coordinates for zip code {zip_code}.")
        return None