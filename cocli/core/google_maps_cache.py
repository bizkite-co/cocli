
import csv
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, UTC

from ..models.google_maps import GoogleMapsData
from .config import get_cocli_base_dir

class GoogleMapsCache:
    def __init__(self, cache_dir: Optional[Path] = None):
        if not cache_dir:
            cache_dir = get_cocli_base_dir() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = cache_dir / "google_maps_cache.csv"
        self.data: Dict[str, GoogleMapsData] = {}
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
                            if dt_obj.tzinfo is None:
                                processed_row[k] = dt_obj.replace(tzinfo=UTC)
                            else:
                                processed_row[k] = dt_obj
                        except (ValueError, TypeError):
                            processed_row[k] = None
                    else:
                        processed_row[k] = v

                if processed_row.get("Place_ID"):
                    try:
                        self.data[str(processed_row["Place_ID"])] = GoogleMapsData(**processed_row)
                    except Exception as e:
                        print(f"Error loading GoogleMapsData from cache: {e} for row: {row}")

    def get_by_place_id(self, place_id: str) -> Optional[GoogleMapsData]:
        return self.data.get(place_id)

    def add_or_update(self, item: GoogleMapsData) -> None:
        if item.Place_ID:
            item.updated_at = datetime.now(UTC)
            self.data[item.Place_ID] = item

    def save(self) -> None:
        with open(self.cache_file, "w", newline="", encoding="utf-8") as csvfile:
            headers = GoogleMapsData.model_fields.keys()
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            for item in self.data.values():
                writer.writerow(item.model_dump())
