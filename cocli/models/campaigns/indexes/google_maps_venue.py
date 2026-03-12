from typing import Optional, Literal, ClassVar
import logging

from .google_maps_place import GoogleMapsPlace
from .google_maps_raw import GoogleMapsRawResult

logger = logging.getLogger(__name__)

class GoogleMapsVenue(GoogleMapsPlace):
    """
    EXTENDED MODEL: Specialized model for Google Maps venues (community resources).
    Contains 60 columns: 56 base + 4 venue-specific.
    """
    SCHEMA_VERSION: ClassVar[str] = "1.1.0"
    INDEX_NAME: ClassVar[str] = "google_maps_venues"

    # --- Resource Discovery Extension ---
    is_value_resource: Optional[bool] = None
    fee_category: Optional[str] = None
    rationale: Optional[str] = None
    prospect_type: Literal["prospect", "venue"] = "venue"

    @classmethod
    def from_raw(cls, raw: GoogleMapsRawResult) -> "GoogleMapsVenue":
        from cocli.core.text_utils import slugify
        data = {
            "place_id": raw.Place_ID,
            "name": raw.Name,
            "keyword": raw.Keyword,
            "full_address": raw.Full_Address,
            "street_address": raw.Street_Address,
            "city": raw.City,
            "zip": raw.Zip,
            "municipality": raw.Municipality,
            "state": raw.State,
            "country": raw.Country,
            "timezone": raw.Timezone,
            "phone": raw.Phone_1,
            "phone_standard_format": raw.Phone_Standard_format,
            "website": raw.Website,
            "domain": raw.Domain,
            "first_category": raw.First_category,
            "second_category": raw.Second_category,
            "claimed_google_my_business": raw.Claimed_google_my_business,
            "reviews_count": raw.Reviews_count,
            "average_rating": raw.Average_rating,
            "hours": raw.Hours,
            "saturday": raw.Saturday,
            "sunday": raw.Sunday,
            "monday": raw.Monday,
            "tuesday": raw.Tuesday,
            "wednesday": raw.Wednesday,
            "thursday": raw.Thursday,
            "friday": raw.Friday,
            "latitude": raw.Latitude,
            "longitude": raw.Longitude,
            "coordinates": raw.Coordinates,
            "plus_code": raw.Plus_Code,
            "gmb_url": raw.GMB_URL,
            "cid": raw.CID,
            "image_url": raw.Image_URL,
            "favicon": raw.Favicon,
            "review_url": raw.Review_URL,
            "facebook_url": raw.Facebook_URL,
            "linkedin_url": raw.Linkedin_URL,
            "instagram_url": raw.Instagram_URL,
            "thumbnail_url": raw.Thumbnail_URL,
            "reviews": raw.Reviews,
            "quotes": raw.Quotes,
            "processed_by": raw.processed_by or "local-worker",
            "list_found_at": raw.created_at,
            "details_found_at": raw.updated_at,
            "is_value_resource": raw.is_value_resource,
            "fee_category": raw.fee_category,
            "rationale": raw.rationale
        }
        
        if data["name"]:
            name_str = str(data["name"])
            data["slug"] = slugify(name_str)
            
        return cls(**data) # type: ignore

    @classmethod
    def append_to_checkpoint(cls, campaign_name: str, venue: "GoogleMapsVenue") -> None:
        """Appends a venue to the campaign's specialized checkpoint USV."""
        from ....core.paths import paths
        # Venues live in their own checkpoint file to maintain schema purity
        checkpoint_path = paths.campaign(campaign_name).index(cls.INDEX_NAME).path / "venues.checkpoint.usv"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(checkpoint_path, "a", encoding="utf-8") as f:
            f.write(venue.to_usv())
