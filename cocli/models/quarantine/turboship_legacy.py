from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..google_maps_prospect import GoogleMapsProspect

class TurboshipLegacyProspect(BaseModel):
    """
    QUARANTINED MODEL: Matches the legacy headered USV format found in Turboship.
    Total fields: 53 (0 to 52)
    """
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    version: Optional[str] = None
    keyword: Optional[str] = None
    name: str
    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    municipality: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    phone_1: Optional[str] = None
    phone_standard_format: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    first_category: Optional[str] = None
    second_category: Optional[str] = None
    claimed_google_my_business: Optional[str] = None
    reviews_count: Optional[str] = None
    average_rating: Optional[str] = None
    hours: Optional[str] = None
    saturday: Optional[str] = None
    sunday: Optional[str] = None
    monday: Optional[str] = None
    tuesday: Optional[str] = None
    wednesday: Optional[str] = None
    thursday: Optional[str] = None
    friday: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    coordinates: Optional[str] = None
    plus_code: Optional[str] = None
    place_id: str
    menu_link: Optional[str] = None
    gmb_url: Optional[str] = None
    cid: Optional[str] = None
    google_knowledge_url: Optional[str] = None
    kgmid: Optional[str] = None
    image_url: Optional[str] = None
    favicon: Optional[str] = None
    review_url: Optional[str] = None
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    reviews: Optional[str] = None
    quotes: Optional[str] = None
    uuid: Optional[str] = None
    company_slug: Optional[str] = None
    company_hash: Optional[str] = None
    processed_by: Optional[str] = None

    @classmethod
    def from_usv_line(cls, line: str) -> "TurboshipLegacyProspect":
        from cocli.core.utils import UNIT_SEP
        parts = line.strip("\x1e\n").split(UNIT_SEP)
        
        # Skip header if it's the header row
        if parts[0] == "created_at":
            return None # Type system will handle this in caller
            
        # Mapping based on the verified indices (Place ID at 35, Slug at 51)
        data = {
            "created_at": parts[0] if len(parts) > 0 else None,
            "updated_at": parts[1] if len(parts) > 1 else None,
            "version": parts[2] if len(parts) > 2 else None,
            "keyword": parts[4] if len(parts) > 4 else None,
            "name": parts[5] if len(parts) > 5 else "Unknown",
            "full_address": parts[6] if len(parts) > 6 else None,
            "street_address": parts[7] if len(parts) > 7 else None,
            "city": parts[8] if len(parts) > 8 else None,
            "zip": parts[9] if len(parts) > 9 else None,
            "municipality": parts[10] if len(parts) > 10 else None,
            "state": parts[11] if len(parts) > 11 else None,
            "country": parts[12] if len(parts) > 12 else None,
            "timezone": parts[13] if len(parts) > 13 else None,
            "phone_1": parts[14] if len(parts) > 14 else None,
            "phone_standard_format": parts[15] if len(parts) > 15 else None,
            "website": parts[16] if len(parts) > 16 else None,
            "domain": parts[17] if len(parts) > 17 else None,
            "first_category": parts[18] if len(parts) > 18 else None,
            "second_category": parts[19] if len(parts) > 19 else None,
            "claimed_google_my_business": parts[20] if len(parts) > 20 else None,
            "reviews_count": parts[21] if len(parts) > 21 else None,
            "average_rating": parts[22] if len(parts) > 22 else None,
            "hours": parts[23] if len(parts) > 23 else None,
            "saturday": parts[24] if len(parts) > 24 else None,
            "sunday": parts[25] if len(parts) > 25 else None,
            "monday": parts[26] if len(parts) > 26 else None,
            "tuesday": parts[27] if len(parts) > 27 else None,
            "wednesday": parts[28] if len(parts) > 28 else None,
            "thursday": parts[29] if len(parts) > 29 else None,
            "friday": parts[30] if len(parts) > 30 else None,
            "latitude": parts[31] if len(parts) > 31 else None,
            "longitude": parts[32] if len(parts) > 32 else None,
            "coordinates": parts[33] if len(parts) > 33 else None,
            "plus_code": parts[34] if len(parts) > 34 else None,
            "place_id": parts[35] if len(parts) > 35 else "NONE",
            "menu_link": parts[36] if len(parts) > 36 else None,
            "gmb_url": parts[37] if len(parts) > 37 else None,
            "cid": parts[38] if len(parts) > 38 else None,
            "google_knowledge_url": parts[39] if len(parts) > 39 else None,
            "kgmid": parts[40] if len(parts) > 40 else None,
            "image_url": parts[41] if len(parts) > 41 else None,
            "favicon": parts[42] if len(parts) > 42 else None,
            "review_url": parts[43] if len(parts) > 43 else None,
            "facebook_url": parts[44] if len(parts) > 44 else None,
            "linkedin_url": parts[45] if len(parts) > 45 else None,
            "instagram_url": parts[46] if len(parts) > 46 else None,
            "thumbnail_url": parts[47] if len(parts) > 47 else None,
            "reviews": parts[48] if len(parts) > 48 else None,
            "quotes": parts[49] if len(parts) > 49 else None,
            "uuid": parts[50] if len(parts) > 50 else None,
            "company_slug": parts[51] if len(parts) > 51 else None,
            "processed_by": parts[52] if len(parts) > 52 else None,
        }
        return cls(**{k: v for k, v in data.items() if v is not None})

    def to_ideal(self) -> GoogleMapsProspect:
        """Transforms the Turboship legacy format into the Gold Standard model."""
        from cocli.core.text_utils import parse_address_components, calculate_company_hash, slugify
        
        # 1. Map all fields to the Gold Standard model
        data = {
            "place_id": self.place_id,
            "name": self.name,
            "keyword": self.keyword,
            "full_address": self.full_address,
            "street_address": self.street_address,
            "city": self.city,
            "zip": self.zip,
            "municipality": self.municipality,
            "state": self.state,
            "country": self.country,
            "timezone": self.timezone,
            "phone": self.phone_1,
            "phone_standard_format": self.phone_standard_format,
            "website": self.website,
            "domain": self.domain,
            "first_category": self.first_category,
            "second_category": self.second_category,
            "claimed_google_my_business": self.claimed_google_my_business,
            "hours": self.hours,
            "saturday": self.saturday,
            "sunday": self.sunday,
            "monday": self.monday,
            "tuesday": self.tuesday,
            "wednesday": self.wednesday,
            "thursday": self.thursday,
            "friday": self.friday,
            "coordinates": self.coordinates,
            "plus_code": self.plus_code,
            "menu_link": self.menu_link,
            "gmb_url": self.gmb_url,
            "cid": self.cid,
            "google_knowledge_url": self.google_knowledge_url,
            "kgmid": self.kgmid,
            "image_url": self.image_url,
            "favicon": self.favicon,
            "review_url": self.review_url,
            "facebook_url": self.facebook_url,
            "linkedin_url": self.linkedin_url,
            "instagram_url": self.instagram_url,
            "thumbnail_url": self.thumbnail_url,
            "reviews": self.reviews,
            "quotes": self.quotes,
            "uuid": self.uuid,
            "processed_by": self.processed_by or "turboship-migration"
        }

        # Handle numeric fields
        try:
            if self.reviews_count:
                data["reviews_count"] = int(self.reviews_count)
            if self.average_rating:
                data["average_rating"] = float(self.average_rating)
            if self.latitude:
                data["latitude"] = float(self.latitude)
            if self.longitude:
                data["longitude"] = float(self.longitude)
        except (ValueError, TypeError):
            pass

        # Handle datetimes
        try:
            if self.created_at:
                data["created_at"] = datetime.fromisoformat(self.created_at)
            if self.updated_at:
                data["updated_at"] = datetime.fromisoformat(self.updated_at)
        except (ValueError, TypeError):
            pass

        # 2. Identity Tripod & Slug
        if not self.company_slug and self.name:
            data["company_slug"] = slugify(self.name)
        else:
            data["company_slug"] = self.company_slug

        # 3. Parsing address components if they are missing but full_address exists
        if not data.get("street_address") and self.full_address:
            addr_data = parse_address_components(self.full_address)
            for key, val in addr_data.items():
                if val and not data.get(key):
                    data[key] = val

        # 4. Final Hash
        data["company_hash"] = calculate_company_hash(
            data["name"],
            data.get("street_address"),
            data.get("zip")
        )
        
        return GoogleMapsProspect.model_validate(data)
