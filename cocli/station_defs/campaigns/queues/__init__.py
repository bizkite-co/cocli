"""Queue station definitions under campaigns/{campaign}/queues/…

Phase names are declared per station template — not a single global phase list.
Product queues may use a subset of these names (see QueueIdentity / StateFolder).
"""

from __future__ import annotations

from stations.segments import phases, shard_by_hash
from stations.station import StationDecl

# Shared pending template for CampaignQueueAsQueueEdge (product queue names vary).
QUEUE_PENDING_TEMPLATE: StationDecl[object] = StationDecl(
    name="campaign-queue-pending",
    path_template="campaigns/{campaign}/queues/{queue}/pending",
    model=object,
    serialization="json-file",
    segments=(
        # Declaration-time phase vocabulary for DFQ-style queues.
        # Runtime dirs still chosen by product code (pending/completed/...).
        phases("pending", "completed", "failed", "sideline", "processing"),
        shard_by_hash(1),
    ),
)
