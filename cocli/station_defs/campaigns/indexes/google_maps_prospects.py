"""Station defs: campaigns/{campaign}/indexes/google_maps_prospects/ (0010).

Data tree:
  indexes/google_maps_prospects/wal/     — write-ahead USV segments
  indexes/google_maps_prospects/prospects.usv  — product checkpoint (IndexPaths)
  indexes/google_maps_prospects/CURRENT  — stations commit pointer
"""

from __future__ import annotations

from stations.segments import phases, shard_by_hash
from stations.station import StationDecl

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

PROSPECTS_WAL: StationDecl[GoogleMapsProspect] = StationDecl(
    name="prospects-wal",
    path_template="wal",
    model=GoogleMapsProspect,
    serialization="usv-tree",
    segments=(
        phases("wal"),  # log phase under the index root
        shard_by_hash(1),  # place-id style 1-char shards when used
    ),
)

PROSPECTS_INDEX: StationDecl[GoogleMapsProspect] = StationDecl(
    name="prospects-index",
    path_template="google_maps_prospects",
    model=GoogleMapsProspect,
    serialization="usv-checkpoint",
    segments=(
        phases("wal", "processing"),  # FIMC local phases (values still on disk)
        shard_by_hash(1),
    ),
)
