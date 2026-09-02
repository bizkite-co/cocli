"""Queue station definitions under campaigns/{campaign}/queues/…

Phase names are declared per station — not a single global phase list.

## Shard strategy → combinator map (algorithm-preserving)

| Queue family | Production algorithm | Combinator |
| :--- | :--- | :--- |
| gm-details (default DFQ) | place_id 6th char, raw alphabet (``-``/``_`` distinct) | ``shard_by_char_index(5)`` |
| gm-list | same for bare ids; pre-sharded task ids (``2/25.0/…``) keep first segment | ``shard_by_char_index(5)`` + FSQ pre-shard rule |
| enrichment | ``sha256(domain)[:2]`` hex | ``shard_by_hash(2)`` |
| map-tile | no DFQ item shard; payload bag under pending | phases only; layout ``tiles`` under pending |
| unknown queue_name | place_id char (safe DFQ default) | ``shard_by_char_index(5)`` |

**Not** ``shard_by_hash(1)`` for place ids — that would re-shard production data.
discovery-gen is still PR7.
"""

from __future__ import annotations

from stations.segments import phases, shard_by_char_index, shard_by_hash
from stations.station import StationDecl

# Shared DFQ phase set (value-level names on disk; not a global enum type).
_DFQ_PHASES = phases("pending", "completed", "failed", "sideline", "processing")
_PLACE_ID_SHARD = shard_by_char_index(5)
_DOMAIN_HASH_SHARD = shard_by_hash(2)

# DFQ-style queues: pending work lives under pending/{shard}/{id}/
DFQ_QUEUE_STATION: StationDecl[object] = StationDecl(
    name="dfq-queue",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    serialization="json-file",
    segments=(_DFQ_PHASES, _PLACE_ID_SHARD),
)

# Named product queues (0010 PR3)
GM_DETAILS_QUEUE_STATION: StationDecl[object] = StationDecl(
    name="gm-details-queue",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    serialization="json-file",
    segments=(_DFQ_PHASES, _PLACE_ID_SHARD),
)

GM_LIST_QUEUE_STATION: StationDecl[object] = StationDecl(
    name="gm-list-queue",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    serialization="json-file",
    segments=(_DFQ_PHASES, _PLACE_ID_SHARD),
)

ENRICHMENT_QUEUE_STATION: StationDecl[object] = StationDecl(
    name="enrichment-queue",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    serialization="json-file",
    segments=(_DFQ_PHASES, _DOMAIN_HASH_SHARD),
)

# map-tile: pure tile registry (file-per-tile, phrase rows inside each file).
# No processing phase - map-tile has no staging/throttling job to do; that
# job belongs to whatever consumes map-tile/pending (batched via --max).
# ``tiles`` is layout under pending/ — not a peer phase of pending/completed.
_MAP_TILE_PHASES = phases("pending", "completed")
MAP_TILE_QUEUE_STATION: StationDecl[object] = StationDecl(
    name="map-tile-queue",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    # Payload files under pending/tiles are USV; schema written by TileRecord.
    # StationDecl uses json-file so datapackage_path is not required at decl time.
    serialization="json-file",
    segments=(_MAP_TILE_PHASES,),
)
# Fixed layout segment name under pending (not a PhaseRef).
MAP_TILE_PENDING_LAYOUT = "tiles"

# to-call / to-call-invalid: one USV file per slug under pending/, no DFQ shard.
_TO_CALL_PHASES = phases("pending", "completed")
TO_CALL_QUEUE_STATION: StationDecl[object] = StationDecl(
    name="to-call-queue",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    serialization="json-file",
    segments=(_TO_CALL_PHASES,),
)
TO_CALL_INVALID_QUEUE_STATION: StationDecl[object] = StationDecl(
    name="to-call-invalid-queue",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    serialization="json-file",
    segments=(_TO_CALL_PHASES,),
)
TO_CALL_HIGH_VALUE_QUEUE_STATION: StationDecl[object] = StationDecl(
    name="to-call-high-value-queue",
    path_template="campaigns/{campaign}/queues/{queue}",
    model=object,
    serialization="json-file",
    segments=(_TO_CALL_PHASES,),
)

# Backward-compatible name used by path_helpers pilot
QUEUE_PENDING_TEMPLATE: StationDecl[object] = StationDecl(
    name="campaign-queue-pending",
    path_template="campaigns/{campaign}/queues/{queue}/pending",
    model=object,
    serialization="json-file",
    segments=(_DFQ_PHASES, _PLACE_ID_SHARD),
)

# Explicit alias kept for callers that already import the domain-hash template
DFQ_DOMAIN_SHARD_STATION: StationDecl[object] = ENRICHMENT_QUEUE_STATION

# queue_name → StationDecl (FilesystemQueue / QueueLayout resolution)
QUEUE_STATIONS: dict[str, StationDecl[object]] = {
    "gm-details": GM_DETAILS_QUEUE_STATION,
    "gm-list": GM_LIST_QUEUE_STATION,
    "enrichment": ENRICHMENT_QUEUE_STATION,
    "map-tile": MAP_TILE_QUEUE_STATION,
    "to-call": TO_CALL_QUEUE_STATION,
    "to-call-invalid": TO_CALL_INVALID_QUEUE_STATION,
    "to-call-high-value": TO_CALL_HIGH_VALUE_QUEUE_STATION,
}


def station_for_queue(queue_name: str) -> StationDecl[object]:
    """Resolve StationDecl for a queue_name (algorithm-preserving DFQ default)."""
    return QUEUE_STATIONS.get(queue_name, DFQ_QUEUE_STATION)
