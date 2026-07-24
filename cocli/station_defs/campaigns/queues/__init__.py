"""Queue station definitions under campaigns/{campaign}/queues/…"""

from __future__ import annotations

from stations.station import StationDecl

# Shared pending template for CampaignQueueAsQueueEdge (product queue names vary).
QUEUE_PENDING_TEMPLATE: StationDecl[object] = StationDecl(
    name="campaign-queue-pending",
    path_template="campaigns/{campaign}/queues/{queue}/pending",
    model=object,
    serialization="json-file",
)
