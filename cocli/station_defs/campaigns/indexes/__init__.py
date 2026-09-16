"""Index stations under campaigns/{campaign}/indexes/…"""

from __future__ import annotations

from typing import Any, Optional

from stations.segments import ShardByHash, shard_by_hash
from stations.station import StationDecl

# Shared by email + domain indexes (sha256 hex width 2). Managers must
# collect_shard the decl rather than hashlib.sha256(...)[:2] in parallel.
# Annotated explicitly: the sibling modules below import this name while this
# package is still initializing, and mypy cannot infer a type through that.
DOMAIN_HASH_SHARD: ShardByHash = shard_by_hash(2)

# Imported below the shard: the sibling modules import DOMAIN_HASH_SHARD from
# this package, so the name must exist before they are loaded.
from cocli.station_defs.campaigns.indexes.emails import EMAIL_INDEX  # noqa: E402
from cocli.station_defs.campaigns.indexes.google_maps_prospects import (  # noqa: E402
    PROSPECTS_INDEX,
)

# Index family (directory name under indexes/) → root StationDecl.
# domains/ deliberately has no entry: domains.py declares that index global
# rather than campaign-scoped, and the campaign-scoped directories on disk are
# empty husks. Adding a root decl here would assert the opposite.
INDEX_STATIONS: dict[str, StationDecl[Any]] = {
    "emails": EMAIL_INDEX,
    "google_maps_prospects": PROSPECTS_INDEX,
}


def station_for_index(index_name: str) -> Optional[StationDecl[Any]]:
    """Root StationDecl for an index family, or None when undeclared.

    Unlike queues there is no permissive default: only 3 of the 10 index
    families on disk are declared, so guessing a shape would be a worse lie
    than admitting the family is undeclared.
    """
    return INDEX_STATIONS.get(index_name)

