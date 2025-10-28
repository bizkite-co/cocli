import csv
from pathlib import Path
from typing import Optional, Dict, Any, cast, List
from datetime import datetime, timezone
import json
import logging

from cocli.models.domain import Domain
from cocli.models.website import Website
from .config import get_cocli_base_dir

logger = logging.getLogger(__name__)

class WebsiteCache:
    def __init__(self, cache_dir: Optional[Path] = None):
        if not cache_dir:
            cache_dir = get_cocli_base_dir() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = cache_dir / "website_data_cache.csv"
        self.data: Dict[str, Website] = {}
        self._load_data()

    def _load_data(self) -> None:
        if not self.cache_file.exists():
            return

        with open(self.cache_file, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                processed_data: Dict[str, Any] = {}

                # Convert datetime fields
                for field in ['created_at', 'updated_at']:
                    if row.get(field):
                        try:
                            processed_data[field] = datetime.fromisoformat(row[field]).replace(tzinfo=timezone.utc)
                        except (ValueError, TypeError):
                            processed_data[field] = None
                
                # Convert list fields from string representation
                for field in ['personnel', 'services', 'products', 'tags']:
                    if row.get(field) and isinstance(row[field], str):
                        field_value = cast(str, row[field])
                        try:
                            # Safely evaluate string representation of list
                            evaluated_data = cast(Any, json.loads(field_value))
                            if isinstance(evaluated_data, list):
                                if field == 'personnel':
                                    processed_data[field] = cast(List[Dict[str, Any]], evaluated_data)
                                else:
                                    processed_data[field] = cast(List[str], evaluated_data)
                            else:
                                processed_data[field] = []
                        except (json.JSONDecodeError, ValueError, SyntaxError):
                            processed_data[field] = []
                    elif row.get(field) is not None:
                        # If it's not a string but exists, keep it as is (e.g., already a list)
                        processed_data[field] = row[field]
                
                # Convert 'url' to Domain object if it exists and is a string
                if row.get("url") and isinstance(row["url"], str):
                    processed_data["url"] = Domain(url=row["url"])

                # Convert 'scraper_version' to int
                if row.get("scraper_version") and isinstance(row["scraper_version"], str):
                    try:
                        processed_data["scraper_version"] = int(row["scraper_version"])
                    except (ValueError, TypeError):
                        processed_data["scraper_version"] = None
                elif row.get("scraper_version") is not None:
                    processed_data["scraper_version"] = row["scraper_version"]
                
                # Convert 'is_email_provider' to bool
                if row.get("is_email_provider") and isinstance(row["is_email_provider"], str):
                    processed_data["is_email_provider"] = row["is_email_provider"].lower() == 'true'
                elif row.get("is_email_provider") is not None:
                    processed_data["is_email_provider"] = row["is_email_provider"]

                # Copy remaining fields directly
                for k, v in row.items():
                    if k not in processed_data and v is not None:
                        processed_data[k] = v

                # Filter out None values before passing to Pydantic model
                cleaned_data = {k: v for k, v in processed_data.items() if v is not None}

                try:
                    if "url" in cleaned_data and isinstance(cleaned_data["url"], Domain):
                        assert isinstance(cleaned_data["url"], Domain)
                        self.data[cleaned_data["url"].url] = Website(**cleaned_data)  # type: ignore  # type: ignore  # type: ignore
                except Exception as e:
                    logger.warning(f"Error loading Website from cache: {e} for row: {row}")

    def get_by_url(self, url: str) -> Optional[Website]:
        return self.data.get(url)

    def add_or_update(self, item: Website) -> None:
        item.updated_at = datetime.utcnow()
        self.data[item.url] = item

    def flag_as_email_provider(self, url: str) -> None:
        item = self.get_by_url(url)
        if not item:
            item = Website(url=url)
        item.is_email_provider = True
        self.add_or_update(item)

    def save(self) -> None:
        with open(self.cache_file, "w", newline="", encoding="utf-8") as csvfile:
            headers = Website.model_fields.keys()
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            for item in self.data.values():
                dump = item.model_dump()
                # Convert lists to strings for CSV
                for field in ['personnel', 'services', 'products', 'tags']:
                    if dump.get(field):
                        dump[field] = str(dump[field])
                writer.writerow(dump)
