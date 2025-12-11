
import csv
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, UTC

from ..models.google_maps_prospect import GoogleMapsProspect
from .config import get_cocli_base_dir

class GoogleMapsCache:
    def __init__(self, cache_dir: Optional[Path] = None):
        if not cache_dir:
            cache_dir = get_cocli_base_dir() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = cache_dir / "google_maps_cache.csv"
        self.data: Dict[str, GoogleMapsProspect] = {}
        self._load_data()

    def _load_data(self) -> None:
        if not self.cache_file.exists():
            return

        with open(self.cache_file, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                processed_row: Dict[str, Any] = {}
                for k, v in row.items():
                    if v is None or v == '':
                        processed_row[k] = None
                    elif k in ['Reviews_count']:
                        try:
                            processed_row[k] = int(v)
                        except (ValueError, TypeError):
                            processed_row[k] = None
                    elif k in ['Average_rating', 'Latitude', 'Longitude']:
                        try:
                            processed_row[k] = float(v)
                        except (ValueError, TypeError):
                            processed_row[k] = None
                    elif k in ['created_at', 'updated_at']:
                        try:
                            dt_obj = datetime.fromisoformat(v)
                            # Ensure the datetime object is UTC-aware
                            if dt_obj.tzinfo is None:
                                # If naive, assume it's UTC and make it aware
                                processed_row[k] = dt_obj.replace(tzinfo=UTC)
                            else:
                                # If already aware, convert it to UTC timezone
                                processed_row[k] = dt_obj.astimezone(UTC)
                        except (ValueError, TypeError):
                            processed_row[k] = None
                    else:
                        processed_row[k] = v

                if processed_row.get("Place_ID"):
                    try:
                        self.data[str(processed_row["Place_ID"])] = GoogleMapsProspect(**processed_row)
                    except Exception as e:
                        print(f"Error loading GoogleMapsProspect from cache: {e} for row: {row}")

    def get_by_place_id(self, place_id: str) -> Optional[GoogleMapsProspect]:
        return self.data.get(place_id)

    def add_or_update(self, item: GoogleMapsProspect) -> None:
        if item.Place_ID:
            item.updated_at = datetime.now(UTC)
            self.data[item.Place_ID] = item

    def save(self) -> None:
        with open(self.cache_file, "w", newline="", encoding="utf-8") as csvfile:
            headers = GoogleMapsProspect.model_fields.keys()
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            for item in self.data.values():
                writer.writerow(item.model_dump())
