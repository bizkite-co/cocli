from typing import List
from pydantic import Field
from enum import Enum
from .base import BaseUsvModel

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"

class MissionTask(BaseUsvModel):
    """
    Represents a single development task in the mission index.
    Priority is determined by the ordinal position in the USV file.
    """
    slug: str = Field(..., description="Unique URL-friendly name")
    title: str = Field(..., description="Human-readable title")
    status: TaskStatus = Field(TaskStatus.PENDING, description="Current state")
    dependencies: List[str] = Field(default_factory=list, description="List of required task slugs")
    file_path: str = Field(..., description="Relative path to the markdown requirement")

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
        return "\x1f".join(cls.model_fields.keys())
