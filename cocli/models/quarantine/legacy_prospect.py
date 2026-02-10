from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from ..google_maps_prospect import GoogleMapsProspect

class LegacyProspectUSV(BaseModel):
    """
    QUARANTINED MODEL: Matches the legacy USV format found on disk.
    Sequence observed: [place_id, company_slug, name, phone_1, created_at, updated_at, version, processed_by, full_address, ...rest]
    """
    # 0-3: The Identity & Phone
    place_id: str
    company_slug: Optional[str] = None
    name: str
    phone_1: Optional[str] = None
    
    # 4-7: Metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    version: Optional[str] = None
    processed_by: Optional[str] = None
    
    # 8: Full Address (This was being shifted in the Gold model)
    full_address: Optional[str] = None
    
    @classmethod
    def from_usv_line(cls, line: str) -> "LegacyProspectUSV":
        from cocli.core.utils import UNIT_SEP
        parts = line.strip("\x1e\n").split(UNIT_SEP)
        
        data = {
            "place_id": parts[0] if len(parts) > 0 else None,
            "company_slug": parts[1] if len(parts) > 1 else None,
            "name": parts[2] if len(parts) > 2 else None,
            "phone_1": parts[3] if len(parts) > 3 else None,
            "created_at": parts[4] if len(parts) > 4 else None,
            "updated_at": parts[5] if len(parts) > 5 else None,
            "version": parts[6] if len(parts) > 6 else None,
            "processed_by": parts[7] if len(parts) > 7 else None,
            "full_address": parts[8] if len(parts) > 8 else None,
        }
        return cls(**{k: v for k, v in data.items() if v is not None})

    def to_ideal(self) -> GoogleMapsProspect:
        """Transforms the known legacy sequence into the Gold Standard model."""
        from cocli.core.text_utils import parse_address_components, calculate_company_hash
        
        # 1. Start with reliable base fields
        data = {
            "place_id": self.place_id,
            "company_slug": self.company_slug,
            "name": self.name,
            "phone": self.phone_1,
            "full_address": self.full_address,
            "processed_by": self.processed_by or "legacy-recovery"
        }
        
        # 2. Attempt to parse out structured address components if missing
        if self.full_address:
            addr_data = parse_address_components(self.full_address)
            for key, val in addr_data.items():
                if val:
                    data[key] = val
        
        # 3. Generate the hash from recovered components
        data["company_hash"] = calculate_company_hash(
            data["name"],
            data.get("street_address"),
            data.get("zip")
        )
        
        return GoogleMapsProspect.model_validate(data)
