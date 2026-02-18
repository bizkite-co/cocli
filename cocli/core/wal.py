import socket
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional, List
from pydantic import BaseModel

from .paths import paths

logger = logging.getLogger(__name__)

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

def get_node_id() -> str:
    return socket.gethostname()

def append_update(target_dir: Path, field: str, value: Any) -> None:
    """
    Appends a field update to the centralized WAL journal via the paths authority.
    """
    node_id = get_node_id()
    wal_file = paths.wal_journal(node_id)
    target_id = paths.wal_target_id(target_dir)

    # Convert value to string representation (JSON if complex)
    if isinstance(value, (list, dict)):
        import json
        value_str = json.dumps(value)
    else:
        value_str = str(value)
    
    record = DatagramRecord(
        timestamp=datetime.now(UTC).isoformat(),
        node_id=node_id,
        target=target_id,
        field=field,
        value=value_str
    )
    
    # Ensure WAL directory exists
    wal_file.parent.mkdir(parents=True, exist_ok=True)

    with open(wal_file, "a") as f:
        f.write(record.to_usv())
    
    logger.info(f"WAL append: {field}={value_str} in {wal_file}")

def read_updates(target_dir: Path) -> List[DatagramRecord]:
    """
    Reads all datagram records for a specific entity from the centralized WAL.
    """
    wal_dir = paths.wal
    records: List[DatagramRecord] = []
    if not wal_dir.exists():
        return records
    
    target_id = paths.wal_target_id(target_dir)

    for wal_file in sorted(wal_dir.glob("*.usv")):
        try:
            content = wal_file.read_text()
            for raw_record in content.split(RS):
                if raw_record.strip():
                    record = DatagramRecord.from_usv(raw_record)
                    if record.target == target_id:
                        records.append(record)
        except Exception as e:
            logger.error(f"Error reading WAL file {wal_file}: {e}")

            
    # Sort by timestamp (naive 'latest wins' for now)
    records.sort(key=lambda x: x.timestamp)
    return records
