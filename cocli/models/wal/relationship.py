"""One relationship or observation fact (ADR-014).

Whole typed record in a retained Shape A journal. Fields are separated by
the unit separator, and each record ends with a newline. No record separator.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

US = "\x1f"

# Column order is the on-disk contract. Append only.
_COLUMNS: tuple[str, ...] = (
    "relationship_id",
    "timestamp",
    "node_id",
    "campaign_name",
    "subject_type",
    "subject",
    "predicate",
    "object_type",
    "object_key",
    "started_at",
    "ended_at",
    "is_primary",
    "source",
    "method",
    "observed_at",
)


class RelationshipRecord(BaseModel):
    """Append-only fact. Identity for fold is ``relationship_id`` unless the
    predicate's policy says otherwise (ADR-014)."""

    relationship_id: str
    timestamp: str
    node_id: str
    campaign_name: str
    subject_type: str
    subject: str
    predicate: str
    object_type: str
    object_key: str
    started_at: str = ""
    ended_at: str = ""
    is_primary: bool = False
    source: str = ""
    method: str = ""
    observed_at: str = ""
    environment: str = Field(default="prod", exclude=True)

    def to_usv(self) -> str:
        primary = "1" if self.is_primary else "0"
        parts = [
            self.relationship_id,
            self.timestamp,
            self.node_id,
            self.campaign_name,
            self.subject_type,
            self.subject,
            self.predicate,
            self.object_type,
            self.object_key,
            self.started_at,
            self.ended_at,
            primary,
            self.source,
            self.method,
            self.observed_at,
        ]
        if len(parts) != len(_COLUMNS):
            raise RuntimeError("relationship USV column count drifted")
        return US.join(parts) + "\n"

    @classmethod
    def from_usv(cls, line: str) -> "RelationshipRecord":
        parts = line.rstrip("\n").split(US)
        if len(parts) != len(_COLUMNS):
            raise ValueError(
                f"relationship record has {len(parts)} fields, want {len(_COLUMNS)}"
            )
        raw = dict(zip(_COLUMNS, parts))
        flag = raw.pop("is_primary")
        if flag not in ("0", "1"):
            raise ValueError(f"is_primary must be 0 or 1, got {flag!r}")
        return cls(is_primary=flag == "1", **raw)
