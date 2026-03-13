from typing import Optional
from pydantic import BaseModel

# USV Control Characters
US = "\x1f"  # Unit Separator
RS = "\x1e"  # Record Separator

class DatagramRecord(BaseModel):
    timestamp: str
    node_id: str
    campaign_name: str
    target: str  # e.g. companies/apple-inc
    field: str
    value: str
    causality: Optional[str] = None  # Future: Vector Clock / Lamport Timestamp

    def to_usv(self) -> str:
        parts = [self.timestamp, self.node_id, self.campaign_name, self.target, self.field, self.value, self.causality or ""]
        return US.join(parts) + RS

    @classmethod
    def from_usv(cls, usv_record: str) -> "DatagramRecord":
        parts = usv_record.rstrip(RS).split(US)
        if len(parts) == 6:
            # Backward compatible: timestamp, node_id, target, field, value, causality
            # We must infer campaign from target (e.g. campaigns/roadmap/...)
            target = parts[2]
            campaign = "unknown"
            if target.startswith("campaigns/"):
                campaign = target.split("/")[1]
            return cls(
                timestamp=parts[0],
                node_id=parts[1],
                campaign_name=campaign,
                target=target,
                field=parts[3],
                value=parts[4],
                causality=parts[5] if len(parts) > 5 else None
            )
        return cls(
            timestamp=parts[0],
            node_id=parts[1],
            campaign_name=parts[2],
            target=parts[3],
            field=parts[4],
            value=parts[5],
            causality=parts[6] if len(parts) > 6 else None
        )

class QueueDatagram(BaseModel):
    campaign_name: str
    queue_name: str
    task_id: str
    status: str
    timestamp: str
    node_id: str

    def to_usv(self) -> str:
        parts = ["Q", self.campaign_name, self.queue_name, self.task_id, self.status, self.timestamp, self.node_id]
        return US.join(parts) + RS

    @classmethod
    def from_usv(cls, usv_record: str) -> Optional["QueueDatagram"]:
        parts = usv_record.rstrip(RS).split(US)
        if not parts or parts[0] != "Q":
            return None
        try:
            if len(parts) == 6:
                # Legacy: Q, queue_name, task_id, status, timestamp, node_id
                return cls(
                    campaign_name="unknown",
                    queue_name=parts[1],
                    task_id=parts[2],
                    status=parts[3],
                    timestamp=parts[4],
                    node_id=parts[5]
                )
            return cls(
                campaign_name=parts[1],
                queue_name=parts[2],
                task_id=parts[3],
                status=parts[4],
                timestamp=parts[5],
                node_id=parts[6]
            )
        except (IndexError, ValueError):
            return None

class HeartbeatDatagram(BaseModel):
    campaign_name: str
    node_id: str
    timestamp: str
    load_avg: float
    memory_percent: float
    worker_count: int
    active_tasks: int

    def to_usv(self) -> str:
        parts = ["H", self.campaign_name, self.node_id, self.timestamp, str(self.load_avg), str(self.memory_percent), str(self.worker_count), str(self.active_tasks)]
        return US.join(parts) + RS

    @classmethod
    def from_usv(cls, usv_record: str) -> Optional["HeartbeatDatagram"]:
        parts = usv_record.rstrip(RS).split(US)
        if not parts or parts[0] != "H":
            return None
        try:
            if len(parts) == 7:
                # Legacy: H, node_id, timestamp, load_avg, ...
                return cls(
                    campaign_name="unknown",
                    node_id=parts[1],
                    timestamp=parts[2],
                    load_avg=float(parts[3]),
                    memory_percent=float(parts[4]),
                    worker_count=int(parts[5]),
                    active_tasks=int(parts[6])
                )
            return cls(
                campaign_name=parts[1],
                node_id=parts[2],
                timestamp=parts[3],
                load_avg=float(parts[4]),
                memory_percent=float(parts[5]),
                worker_count=int(parts[6]),
                active_tasks=int(parts[7])
            )
        except (IndexError, ValueError):
            return None

class ConfigDatagram(BaseModel):
    campaign_name: str
    node_id: str  # Target node (or '*' for all)
    timestamp: str
    config_json: str # Serialized worker configuration

    def to_usv(self) -> str:
        parts = ["C", self.campaign_name, self.node_id, self.timestamp, self.config_json]
        return US.join(parts) + RS

    @classmethod
    def from_usv(cls, usv_record: str) -> Optional["ConfigDatagram"]:
        parts = usv_record.rstrip(RS).split(US)
        if not parts or parts[0] != "C":
            return None
        try:
            if len(parts) == 4:
                # Legacy
                return cls(
                    campaign_name="unknown",
                    node_id=parts[1],
                    timestamp=parts[2],
                    config_json=parts[3]
                )
            return cls(
                campaign_name=parts[1],
                node_id=parts[2],
                timestamp=parts[3],
                config_json=parts[4]
            )
        except (IndexError, ValueError):
            return None
