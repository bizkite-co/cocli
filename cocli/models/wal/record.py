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

class QueueDatagram(BaseModel):
    queue_name: str
    task_id: str
    status: str
    timestamp: str
    node_id: str

    def to_usv(self) -> str:
        parts = ["Q", self.queue_name, self.task_id, self.status, self.timestamp, self.node_id]
        return US.join(parts) + RS

    @classmethod
    def from_usv(cls, usv_record: str) -> Optional["QueueDatagram"]:
        parts = usv_record.rstrip(RS).split(US)
        if not parts or parts[0] != "Q":
            return None
        try:
            return cls(
                queue_name=parts[1],
                task_id=parts[2],
                status=parts[3],
                timestamp=parts[4],
                node_id=parts[5]
            )
        except (IndexError, ValueError):
            return None
