from typing import List
from pydantic import Field, PrivateAttr
from enum import Enum
from .base import BaseUsvModel

class TaskStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"

class MissionTask(BaseUsvModel):
    """
    Represents a single development task in the mission index.
    Priority is determined by the ordinal position in the USV file.
    File paths are resolved dynamically by slug.
    """
    # ORDER MUST MATCH datapackage.json (Positional)
    slug: str = Field(..., description="Unique URL-friendly name")
    dependencies: List[str] = Field(default_factory=list, description="List of required task slugs")

    # Runtime-only fields (not stored in USV)
    _title: str = PrivateAttr("")
    _status: TaskStatus = PrivateAttr(TaskStatus.PENDING)

    model_config = {
        "use_enum_values": True
    }

    @property
    def title(self) -> str:
        return self._title or self.slug.replace("-", " ").title()

    @title.setter
    def title(self, value: str) -> None:
        self._title = value

    @property
    def status(self) -> TaskStatus:
        return self._status

    @status.setter
    def status(self, value: TaskStatus) -> None:
        self._status = value

    @classmethod
    def from_usv(cls, usv_str: str) -> "MissionTask":
        return super().from_usv(usv_str)

class MigrationTask(BaseUsvModel):
    """
    Orchestrates a distributed data migration across the cluster.
    Pairs an immutable reader with an immutable writer/transformer.
    """
    slug: str = Field(..., description="Unique migration identifier")
    target_store: str = Field(..., description="The StoreIdentity to migrate")
    old_wasi_hash: str = Field(..., description="The SHA-256 hash of the current reader")
    new_wasi_hash: str = Field(..., description="The SHA-256 hash of the new writer")
    transformer_wasm: str = Field(..., description="Path to the WASM transformer binary")
    status: TaskStatus = Field(TaskStatus.PENDING)

    @classmethod
    def get_header(cls) -> str:
        from ..core.constants import UNIT_SEP
        return UNIT_SEP.join(cls.model_fields.keys())
