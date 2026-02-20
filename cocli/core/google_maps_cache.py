
import csv
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Iterable
from datetime import datetime, UTC

from ..models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from .config import get_cocli_base_dir
from ..utils.usv_utils import USVDictReader, USVDictWriter

logger = logging.getLogger(__name__)

class GoogleMapsCache:
    def __init__(self, cache_dir: Optional[Path] = None):
        if not cache_dir:
            cache_dir = get_cocli_base_dir() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file_usv = cache_dir / "google_maps_cache.usv"
        self.cache_file_csv = cache_dir / "google_maps_cache.csv"
        self.data: Dict[str, GoogleMapsProspect] = {}
        self._load_data()

    def _load_data(self) -> None:
        # Prefer USV
        if self.cache_file_usv.exists():
            active_file = self.cache_file_usv
            is_usv = True
        elif self.cache_file_csv.exists():
            active_file = self.cache_file_csv
            is_usv = False
        else:
            return

        with open(active_file, "r", encoding="utf-8") as f:
            reader: Iterable[Dict[str, Any]]
            if is_usv:
                reader = USVDictReader(f)
            else:
                reader = csv.DictReader(f)

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

                if processed_row.get("place_id"):
                    try:
                        self.data[str(processed_row["place_id"])] = GoogleMapsProspect(**processed_row)
                    except Exception as e:
                        logger.error(f"Error loading GoogleMapsProspect from cache: {e} for row: {row}")

    def get_by_place_id(self, place_id: str) -> Optional[GoogleMapsProspect]:
        return self.data.get(place_id)

    def add_or_update(self, item: GoogleMapsProspect) -> None:
        if item.place_id:
            item.updated_at = datetime.now(UTC)
            self.data[item.place_id] = item

    def save(self) -> None:
        with open(self.cache_file_usv, "w", encoding="utf-8") as f:
            headers = list(GoogleMapsProspect.model_fields.keys())
            writer = USVDictWriter(f, fieldnames=headers)
            writer.writeheader()
            for item in self.data.values():
                writer.writerow(item.model_dump())
        
        # If we successfully saved USV, and a legacy CSV exists, we can remove it
        if self.cache_file_csv.exists():
            try:
                self.cache_file_csv.unlink()
            except Exception:
                pass
