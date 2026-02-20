import csv
from pathlib import Path
from typing import Optional, Dict, Any, Iterable
from datetime import datetime, UTC, timezone
import json
import logging

from cocli.models.domain import Domain
from cocli.models.companies.website import Website
from .config import get_cocli_app_data_dir
from ..utils.usv_utils import USVDictReader, USVDictWriter

logger = logging.getLogger(__name__)

class WebsiteCache:
    def __init__(self, cache_dir: Optional[Path] = None):
        if not cache_dir:
            cache_dir = get_cocli_app_data_dir() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file_usv = cache_dir / "website_data_cache.usv"
        self.cache_file_csv = cache_dir / "website_data_cache.csv"
        self.data: Dict[str, Website] = {}
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
                processed_data: Dict[str, Any] = {}

                # Convert datetime fields
                for field in ['created_at', 'updated_at']:
                    if row.get(field):
                        try:
                            processed_data[field] = datetime.fromisoformat(row[field]).replace(tzinfo=timezone.utc)
                        except (ValueError, TypeError):
                            processed_data[field] = None
                
                # Convert list fields from string representation
                for field in ['personnel', 'services', 'products', 'tags', 'all_emails', 'tech_stack', 'email_contexts']:
                    if row.get(field) and isinstance(row[field], str):
                        try:
                            # Safely evaluate string representation of list or dict
                            evaluated_data = json.loads(row[field])
                            processed_data[field] = evaluated_data
                        except (json.JSONDecodeError, ValueError, SyntaxError):
                            if field == 'email_contexts':
                                processed_data[field] = {}
                            else:
                                processed_data[field] = []
                
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
                        self.data[cleaned_data["url"].url] = Website(**cleaned_data)  # type: ignore
                except Exception as e:
                    logger.warning(f"Error loading Website from cache: {e} for row: {row}")

    def get_by_url(self, url: str) -> Optional[Website]:
        return self.data.get(url)

    def add_or_update(self, item: Website) -> None:
        item.updated_at = datetime.now(UTC)
        self.data[item.url] = item

    def flag_as_email_provider(self, url: str) -> None:
        item = self.get_by_url(url)
        if not item:
            item = Website(url=url)
        item.is_email_provider = True
        self.add_or_update(item)

    def save(self) -> None:
        with open(self.cache_file_usv, "w", encoding="utf-8") as f:
            headers = list(Website.model_fields.keys())
            writer = USVDictWriter(f, fieldnames=headers)
            writer.writeheader()
            for item in self.data.values():
                dump = item.model_dump()
                # Convert lists and dicts to JSON strings for CSV/USV
                for field in ['personnel', 'services', 'products', 'tags', 'all_emails', 'tech_stack', 'email_contexts']:
                    if dump.get(field) is not None:
                        dump[field] = json.dumps(dump[field])
                writer.writerow(dump)
        
        # Cleanup legacy CSV if it exists
        if self.cache_file_csv.exists():
            try:
                self.cache_file_csv.unlink()
            except Exception:
                pass