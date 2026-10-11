"""Station def: relationship and observation journal (ADR-014, decision 0010).

Data: ``wal/relationships/{period}_{writer}.usv`` (Shape A, retained).
Facts fold into present state beside sovereign entities. Segments stay.
"""

from __future__ import annotations

from stations.station import StationDecl

from cocli.models.wal.relationship import RelationshipRecord

RELATIONSHIP_JOURNAL: StationDecl[RelationshipRecord] = StationDecl(
    name="relationship-journal",
    path_template="wal/relationships/{period}_{writer}.usv",
    model=RelationshipRecord,
    serialization="usv-segment",
)
