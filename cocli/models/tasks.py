from typing import List, Any
from pydantic import Field, model_validator
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
    # ORDER MATTERS FOR USV (Positional)
    slug: str = Field(..., description="Unique URL-friendly name")
    dependencies: List[str] = Field(default_factory=list, description="List of required task slugs")
    title: str = Field("", description="Human-readable title")
    status: TaskStatus = Field(TaskStatus.PENDING, description="Current state")

    model_config = {
        "use_enum_values": True
    }

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_usv(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # If title or status are missing, they will use defaults
            if "title" not in data or not data["title"]:
                data["title"] = data.get("slug", "").replace("-", " ").title()
            if "status" not in data:
                data["status"] = TaskStatus.PENDING
        return data

    @classmethod
    def from_usv(cls, usv_str: str) -> "MissionTask":
        """Overridden to ensure status string is correctly mapped to Enum."""
        # BaseUsvModel.from_usv uses positional parsing
        return super().from_usv(usv_str)

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
