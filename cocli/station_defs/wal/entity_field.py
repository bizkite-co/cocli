"""Station def: entity field-update journal (decision 0009 + 0010).

Data: ``wal/{period}_{node_id}.usv`` (Shape A segments). Field-update facts
fold into entity present state (e.g. companies/{slug}/_index.md).
"""

from __future__ import annotations

from stations.station import StationDecl

from cocli.models.wal.record import DatagramRecord

ENTITY_FIELD_JOURNAL: StationDecl[DatagramRecord] = StationDecl(
    name="entity-field-journal",
    path_template="wal/{period}_{writer}.usv",
    model=DatagramRecord,
    serialization="usv-segment",
)
