import json
import logging
from typing import Dict, List, Optional

from ..models.do_not_call import DoNotCallEntry
from ..models.phone import PhoneNumber
from .paths import paths

logger = logging.getLogger(__name__)


def normalize_phone(raw: str) -> Optional[str]:
    """Canonical DNC key: digits-only via the same PhoneNumber parser used
    everywhere else in cocli, so a person's number matches regardless of
    how it was originally formatted (dashes, parens, country code, etc.)."""
    parsed = PhoneNumber.validate(raw)
    return str(parsed) if parsed else None


class DoNotCallManager:
    """Shared, campaign-independent do-not-call registry, keyed by
    normalized phone number (Mark, 2026-09-01: DNC obligations are
    per-person and typically company-wide, unlike company-level exclusions
    - ExclusionManager - which stay per-campaign with an optional
    shared/global scope)."""

    def __init__(self) -> None:
        self.dir = paths.do_not_call / "people"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._phones: Dict[str, DoNotCallEntry] = {}
        self._load_all()

    def _load_all(self) -> None:
        self._phones.clear()
        for file in self.dir.glob("*.json"):
            try:
                with open(file, "r") as f:
                    data = json.load(f)
                entry = DoNotCallEntry(**data)
                self._phones[entry.phone] = entry
            except Exception as e:
                logger.error(f"Error loading do-not-call entry {file}: {e}")

    def is_do_not_call(self, phone: Optional[str]) -> bool:
        if not phone:
            return False
        normalized = normalize_phone(phone)
        return bool(normalized and normalized in self._phones)

    def add(self, phone: str, reason: Optional[str] = None) -> DoNotCallEntry:
        normalized = normalize_phone(phone)
        if not normalized:
            raise ValueError(f"Could not parse phone number: {phone}")
        entry = DoNotCallEntry(phone=normalized, reason=reason)
        file_path = self.dir / f"{normalized}.json"
        with open(file_path, "w") as f:
            data = entry.model_dump()
            data["added_at"] = data["added_at"].isoformat()
            json.dump(data, f, indent=2)
        self._phones[normalized] = entry
        return entry

    def remove(self, phone: str) -> bool:
        normalized = normalize_phone(phone)
        if not normalized or normalized not in self._phones:
            return False
        del self._phones[normalized]
        file_path = self.dir / f"{normalized}.json"
        if file_path.exists():
            file_path.unlink()
        return True

    def list_entries(self) -> List[DoNotCallEntry]:
        return list(self._phones.values())
