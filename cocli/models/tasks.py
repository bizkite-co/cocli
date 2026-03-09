from typing import List
from pydantic import Field
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
    slug: str = Field(..., description="Unique URL-friendly name")
    title: str = Field(..., description="Human-readable title")
    status: TaskStatus = Field(TaskStatus.PENDING, description="Current state")
    dependencies: List[str] = Field(default_factory=list, description="List of required task slugs")

    model_config = {
        "use_enum_values": True
    }

    @classmethod
    def from_usv(cls, usv_str: str) -> "MissionTask":
        """Overridden to ensure status string is correctly mapped to Enum."""
        instance = super().from_usv(usv_str)
        return instance

    @classmethod
    def get_header(cls) -> str:
        from ..core.constants import UNIT_SEP
        return UNIT_SEP.join(cls.model_fields.keys())

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
