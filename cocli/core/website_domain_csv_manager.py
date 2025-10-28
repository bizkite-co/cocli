import csv
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import ast

from ..models.website_domain_csv import WebsiteDomainCsv
from .config import get_cocli_base_dir

class WebsiteDomainCsvManager:
    def __init__(self, indexes_dir: Optional[Path] = None):
        if not indexes_dir:
            indexes_dir = get_cocli_base_dir() / "indexes"
        indexes_dir.mkdir(parents=True, exist_ok=True)
        self.csv_file = indexes_dir / "website-domains.csv"
        self.data: Dict[str, WebsiteDomainCsv] = {}
        self._load_data()

    def _load_data(self) -> None:
        if not self.csv_file.exists():
            return

        with open(self.csv_file, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                processed_row = dict(row)
                # Convert datetime fields
                for field in ['created_at', 'updated_at']:
                    if processed_row.get(field):
                        try:
                            processed_row[field] = datetime.fromisoformat(processed_row[field])
                        except (ValueError, TypeError):
                            processed_row[field] = None
                
                # Convert list fields
                for field in ['personnel', 'tags']:
                    if processed_row.get(field):
                        try:
                            processed_row[field] = ast.literal_eval(processed_row[field])
                        except (ValueError, SyntaxError):
                            processed_row[field] = []
                
                # Convert boolean field
                if processed_row.get('is_email_provider'):
                    processed_row['is_email_provider'] = processed_row['is_email_provider'].lower() == 'true'
                
                # Convert int field
                if processed_row.get('scraper_version'):
                    try:
                        processed_row['scraper_version'] = int(processed_row['scraper_version'])
                    except (ValueError, TypeError):
                        processed_row['scraper_version'] = None

                model_data = {k: v for k, v in processed_row.items() if k in WebsiteDomainCsv.model_fields and v is not None}
                if model_data.get("domain"):
                    self.data[str(model_data["domain"])] = WebsiteDomainCsv(**model_data)

    def get_by_domain(self, domain: str) -> Optional[WebsiteDomainCsv]:
        return self.data.get(domain)

    def add_or_update(self, item: WebsiteDomainCsv) -> None:
        item.updated_at = datetime.utcnow()
        self.data[item.domain] = item
        self.save()

    def flag_as_email_provider(self, domain: str) -> None:
        item = self.get_by_domain(domain)
        if not item:
            item = WebsiteDomainCsv(domain=domain)
        item.is_email_provider = True
        self.add_or_update(item)

    def save(self) -> None:
        with open(self.csv_file, "w", newline="", encoding="utf-8") as csvfile:
            headers = list(WebsiteDomainCsv.model_fields.keys())
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            for item in self.data.values():
                dump = item.model_dump()
                # Convert lists to strings for CSV
                for field in ['personnel', 'tags']:
                    if dump.get(field):
                        dump[field] = str(dump[field])
                writer.writerow(dump)
