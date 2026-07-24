"""Station definitions (decision 0010): type-level mirror of the data tree.

Package layout mirrors station paths; modules hold model reference + path
template + edge roles — not the model class bodies (models live in
``cocli.models``). Segment *values* (shard ids, dates, pending/) stay on disk.

Named ``station_defs`` rather than ``stations`` so this package never shadows
the ``stations`` library dependency. Decision 0010's example ``cocli/stations/``
maps to this package.

See ``IDENTIFIER_AUDIT.md`` and stations decision 0010.
"""

from cocli.station_defs.campaigns.indexes.emails import (
    EMAIL_INBOX,
    EMAIL_INDEX,
    EMAIL_SHARDS,
)
from cocli.station_defs.campaigns.indexes.google_maps_prospects import (
    PROSPECTS_INDEX,
    PROSPECTS_WAL,
)
from cocli.station_defs.campaigns.queues import QUEUE_PENDING_TEMPLATE
from cocli.station_defs.wal.entity_field import ENTITY_FIELD_JOURNAL

__all__ = [
    "EMAIL_INBOX",
    "EMAIL_INDEX",
    "EMAIL_SHARDS",
    "PROSPECTS_INDEX",
    "PROSPECTS_WAL",
    "QUEUE_PENDING_TEMPLATE",
    "ENTITY_FIELD_JOURNAL",
]
