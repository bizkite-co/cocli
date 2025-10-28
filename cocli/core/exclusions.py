import csv
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

from ..models.exclusion import Exclusion
from .config import get_cocli_base_dir

class ExclusionManager:
    def __init__(self, campaign: str, cache_dir: Optional[Path] = None):
        if not cache_dir:
            cache_dir = get_cocli_base_dir() / "exclusions"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.campaign = campaign
        self.cache_file = cache_dir / f"{campaign}-exclusions.csv"
        self.data: Dict[str, Exclusion] = {}
        self._load_data()

    def _load_data(self) -> None:
        if not self.cache_file.exists():
            return

        with open(self.cache_file, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row.get("domain"):
                    if row.get("created_at"):
                        try:
                            row["created_at"] = datetime.fromisoformat(row["created_at"])
                        except (ValueError, TypeError):
                            row["created_at"] = None
                    exclusion_data = dict(row)
                    if exclusion_data.get("created_at") is None:
                        del exclusion_data["created_at"]
                    self.data[row["domain"]] = Exclusion(**exclusion_data)

    def is_excluded(self, domain: str) -> bool:
        return domain in self.data

    def add_exclusion(self, domain: str, reason: Optional[str] = None) -> None:
        exclusion = Exclusion(domain=domain, campaign=self.campaign, reason=reason)
        self.data[domain] = exclusion
        self.save()

    def save(self) -> None:
        with open(self.cache_file, "w", newline="", encoding="utf-8") as csvfile:
            headers = Exclusion.model_fields.keys()
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            for item in self.data.values():
                writer.writerow(item.model_dump())
