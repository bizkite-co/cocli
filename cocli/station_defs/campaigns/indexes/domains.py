"""Station defs: indexes/domains/ (global, not campaign-scoped).

Live layout (DomainIndexManager):
  inbox/{sha256(domain)[:2]}/{slugdotify(domain)}.usv
  shards/{shard}.usv

Shard key is the domain string, same combinator as EMAIL_INBOX.
"""

from __future__ import annotations

from stations.segments import phases
from stations.station import StationDecl

from cocli.models.campaigns.indexes.domains import WebsiteDomainCsv
from cocli.station_defs.campaigns.indexes import DOMAIN_HASH_SHARD

DOMAIN_INBOX: StationDecl[WebsiteDomainCsv] = StationDecl(
    name="domain-inbox",
    path_template="inbox",
    model=WebsiteDomainCsv,
    serialization="usv-or-json-file",
    segments=(
        phases("inbox"),
        DOMAIN_HASH_SHARD,
    ),
)

DOMAIN_SHARDS: StationDecl[WebsiteDomainCsv] = StationDecl(
    name="domain-shards",
    path_template="shards",
    model=WebsiteDomainCsv,
    serialization="usv-lines",
    segments=(DOMAIN_HASH_SHARD,),
)
