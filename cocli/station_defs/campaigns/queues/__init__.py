"""Queue station definitions under campaigns/{campaign}/queues/…

Phase names are declared per station — not a single global phase list.
Default DFQ uses place_id 6th-character sharding (``shard_by_char_index(5)``),
matching historical ``get_place_id_shard`` / ``get_shard_id`` — not hash(1).
"""

from __future__ import annotations

from stations.segments import phases, shard_by_char_index, shard_by_hash
from stations.station import StationDecl

# DFQ-style queues: pending work lives under pending/{shard}/{id}/
DFQ_QUEUE_STATION: StationDecl[object] = StationDecl(
    name="dfq-queue",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    serialization="json-file",
    segments=(
        phases("pending", "completed", "failed", "sideline", "processing"),
        # Place ID char at index 5, raw alphabet (incl. '-' and '_') — not slugified
        shard_by_char_index(5),
    ),
)

# Backward-compatible name used by path_helpers pilot
QUEUE_PENDING_TEMPLATE: StationDecl[object] = StationDecl(
    name="campaign-queue-pending",
    path_template="campaigns/{campaign}/queues/{queue}/pending",
    model=object,
    serialization="json-file",
    segments=(
        phases("pending", "completed", "failed", "sideline", "processing"),
        shard_by_char_index(5),
    ),
)

# Domain-hash queues (enrichment-style) — opt-in per PR3 wiring
DFQ_DOMAIN_SHARD_STATION: StationDecl[object] = StationDecl(
    name="dfq-queue-domain-shard",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    serialization="json-file",
    segments=(
        phases("pending", "completed", "failed", "sideline", "processing"),
        shard_by_hash(2),
    ),
)
