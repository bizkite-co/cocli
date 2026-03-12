from typing import Optional, ClassVar
from datetime import datetime, UTC
from pathlib import Path
import logging

from .google_maps_place import GoogleMapsPlace
from .google_maps_raw import GoogleMapsRawResult

logger = logging.getLogger(__name__)

class GoogleMapsProspect(GoogleMapsPlace):
    """
    GOLD STANDARD MODEL: Standardized model for Google Maps sales prospects.
    Strictly follows the 56-column canonical USV format.
    """
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    INDEX_NAME: ClassVar[str] = "google_maps_prospects"

    def merge_with_existing(self, existing: "GoogleMapsProspect") -> "GoogleMapsProspect":
        """
        Merges this (newly scraped) prospect with an existing one.
        Mandate: Only overwrite fields if the new value is NOT null/empty.
        """
        new_data = self.model_dump(exclude_unset=True)
        existing_data = existing.model_dump()
        
        merged_data = existing_data.copy()
        for key, val in new_data.items():
            # Only overwrite if new value is non-null and non-empty string
            if val is not None and val != "":
                merged_data[key] = val
        
        # Ensure updated_at is refreshed
        merged_data["updated_at"] = datetime.now(UTC)
        
        return self.__class__(**merged_data)

    @classmethod
    def get_by_place_id(cls, campaign_name: str, place_id: str) -> Optional["GoogleMapsProspect"]:
        """
        Attempts to find an existing prospect in the campaign index by Place ID.
        """
        from cocli.core.prospects_csv_manager import ProspectsIndexManager
        manager = ProspectsIndexManager(campaign_name)
        # Use DuckDB for fast lookup in checkpoint + WAL shards
        import duckdb
        con = duckdb.connect(database=':memory:')
        
        checkpoint = manager.index_dir / "prospects.checkpoint.usv"
        if not checkpoint.exists():
            return None
            
        try:
            # We only need to check the checkpoint for now as a baseline
            q = f"SELECT * FROM read_csv('{checkpoint}', delim='\x1f', header=False, auto_detect=True, all_varchar=True) WHERE column1 = '{place_id}' LIMIT 1"
            res = con.execute(q).df()
            if not res.empty:
                from cocli.utils.usv_utils import USVDictReader
                with open(checkpoint, "r", encoding="utf-8") as f:
                    reader = USVDictReader(f)
                    for r in reader:
                        if r.get("place_id") == place_id:
                            return cls.model_validate(r)
        except Exception:
            pass
        return None

    @classmethod
    def save_datapackage(cls, path: Path, resource_name: str = "google_maps_prospects", resource_path: str = "prospects.checkpoint.usv", force: bool = False, wasi_hash: Optional[str] = None) -> None:
        """Saves the datapackage.json to the specified directory."""
        super().save_datapackage(path, resource_name, resource_path, force=force, wasi_hash=wasi_hash)

    @classmethod
    def from_raw(cls, raw: GoogleMapsRawResult) -> "GoogleMapsProspect":
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
            "details_found_at": raw.updated_at
        }
        
        if data["name"]:
            name_str = str(data["name"])
            data["slug"] = slugify(name_str)
            
        return cls(**data) # type: ignore

    @classmethod
    def append_to_checkpoint(cls, campaign_name: str, prospect: "GoogleMapsProspect") -> None:
        """Appends a prospect to the campaign's main checkpoint USV."""
        from ....core.paths import paths
        checkpoint_path = paths.campaign(campaign_name).index(cls.INDEX_NAME).checkpoint
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(checkpoint_path, "a", encoding="utf-8") as f:
            f.write(prospect.to_usv())
