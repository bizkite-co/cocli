from typing import Optional
from pydantic import BaseModel

# USV Control Characters
US = "\x1f"  # Unit Separator
RS = "\x1e"  # Record Separator

class DatagramRecord(BaseModel):
    timestamp: str
    node_id: str
    target: str  # e.g. companies/apple-inc
    field: str
    value: str
    causality: Optional[str] = None  # Future: Vector Clock / Lamport Timestamp

    def to_usv(self) -> str:
        parts = [self.timestamp, self.node_id, self.target, self.field, self.value, self.causality or ""]
        return US.join(parts) + RS

    @classmethod
    def from_usv(cls, usv_record: str) -> "DatagramRecord":
        parts = usv_record.rstrip(RS).split(US)
        return cls(
            timestamp=parts[0],
            node_id=parts[1],
            target=parts[2],
            field=parts[3],
            value=parts[4],
            causality=parts[5] if len(parts) > 5 else None
        )
