
import csv
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

from ..models.website import Website
from .config import get_cocli_base_dir

class WebsiteCache:
    def __init__(self, cache_dir: Optional[Path] = None):
        if not cache_dir:
            cache_dir = get_cocli_base_dir() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = cache_dir / "website_data_cache.csv"
        self.data: Dict[str, Website] = {}
        self._load_data()

    def _load_data(self):
        if not self.cache_file.exists():
            return

        with open(self.cache_file, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Convert datetime fields
                for field in ['created_at', 'updated_at']:
                    if row.get(field):
                        try:
                            row[field] = datetime.fromisoformat(row[field])
                        except (ValueError, TypeError):
                            row[field] = None
                # Convert boolean field
                for field in ['personnel', 'services', 'products', 'tags']:
                    if row.get(field):
                        # The string from the CSV looks like "['item1', 'item2']"
                        # We need to evaluate it back into a list.
                        try:
                            row[field] = eval(row[field])
                        except Exception:
                            row[field] = []
                
                model_data = {k: v for k, v in row.items() if k in Website.model_fields}
                if model_data.get("url"):
                    self.data[model_data["url"]] = Website(**model_data)

    def get_by_url(self, url: str) -> Optional[Website]:
        return self.data.get(url)

    def add_or_update(self, item: Website):
        item.updated_at = datetime.utcnow()
        self.data[item.url] = item

    def flag_as_email_provider(self, url: str):
        item = self.get_by_url(url)
        if not item:
            item = Website(url=url)
        item.is_email_provider = True
        self.add_or_update(item)

    def save(self):
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
