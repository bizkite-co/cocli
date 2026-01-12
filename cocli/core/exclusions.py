import json
from typing import Optional, Dict, List
from datetime import datetime
import logging

from ..models.exclusion import Exclusion
from .paths import paths

logger = logging.getLogger(__name__)

class ExclusionManager:
    def __init__(self, campaign: str):
        self.campaign = campaign
        self.exclude_dir = paths.campaign_indexes(campaign) / "exclude"
        self.exclude_dir.mkdir(parents=True, exist_ok=True)
        # In-memory cache for fast lookup
        self._slug_map: Dict[str, Exclusion] = {}
        self._domain_map: Dict[str, Exclusion] = {}
        self._load_all()

    def _load_all(self) -> None:
        self._slug_map.clear()
        self._domain_map.clear()
        for file in self.exclude_dir.glob("*.json"):
            try:
                with open(file, "r") as f:
                    data = json.load(f)
                    if "created_at" in data and data["created_at"]:
                        data["created_at"] = datetime.fromisoformat(data["created_at"])
                    exc = Exclusion(**data)
                    if exc.company_slug:
                        self._slug_map[exc.company_slug] = exc
                    if exc.domain:
                        self._domain_map[exc.domain] = exc
            except Exception as e:
                logger.error(f"Error loading exclusion file {file}: {e}")

    def is_excluded(self, domain: Optional[str] = None, slug: Optional[str] = None) -> bool:
        if slug and slug in self._slug_map:
            return True
        if domain and domain in self._domain_map:
            return True
        return False

    def add_exclusion(self, domain: Optional[str] = None, slug: Optional[str] = None, reason: Optional[str] = None) -> None:
        if not domain and not slug:
            raise ValueError("Must provide either domain or slug to exclude")
        
        exc = Exclusion(
            domain=domain,
            company_slug=slug,
            campaign=self.campaign,
            reason=reason
        )
        
        # Save to file named after slug (preferred) or domain
        name = slug if slug else (domain.replace(".", "_") if domain else "unknown")
        file_path = self.exclude_dir / f"{name}.json"
        
        with open(file_path, "w") as f:
            data = exc.model_dump()
            data["created_at"] = data["created_at"].isoformat()
            json.dump(data, f, indent=2)
        
        # Update cache
        if slug:
            self._slug_map[slug] = exc
        if domain:
            self._domain_map[domain] = exc

    def remove_exclusion(self, domain: Optional[str] = None, slug: Optional[str] = None) -> None:
        if slug and slug in self._slug_map:
            filename = slug
            del self._slug_map[slug]
        elif domain and domain in self._domain_map:
            filename = domain.replace(".", "_")
            del self._domain_map[domain]
        else:
            return

        file_path = self.exclude_dir / f"{filename}.json"
        if file_path.exists():
            file_path.unlink()

    def list_exclusions(self) -> List[Exclusion]:
        # Return unique exclusions (some might have both slug and domain)
        unique = {}
        for exc in self._slug_map.values():
            unique[id(exc)] = exc
        for exc in self._domain_map.values():
            unique[id(exc)] = exc
        return list(unique.values())