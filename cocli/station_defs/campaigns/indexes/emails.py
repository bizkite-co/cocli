"""Station defs: campaigns/{campaign}/indexes/emails/ (decision 0010).

Data tree:
  indexes/emails/inbox/     — hot write intake (WAL shape B)
  indexes/emails/shards/    — DuckDB-facing materialization
  indexes/emails/CURRENT    — stations commit pointer

Segments are declared at construction time (combinators), not hard-coded
globals: inbox uses hash sharding width 2 (domain → 00..ff); shards are cold
materialization of the same fold.
"""

from __future__ import annotations

from stations.segments import phases, shard_by_hash
from stations.station import StationDecl

from cocli.models.campaigns.indexes.email import EmailEntry

# path_template is relative to the emails index root (product resolves absolute).
EMAIL_INBOX: StationDecl[EmailEntry] = StationDecl(
    name="email-inbox",
    path_template="inbox",
    model=EmailEntry,
    serialization="usv-or-json-file",
    segments=(
        phases("inbox"),  # hot layer phase name is "inbox" for this station
        shard_by_hash(2),  # domain hash 00-ff (matches EmailIndexManager)
    ),
)

EMAIL_SHARDS: StationDecl[EmailEntry] = StationDecl(
    name="email-shards",
    path_template="shards",
    model=EmailEntry,
    serialization="usv-lines",
    segments=(shard_by_hash(2),),
)

EMAIL_INDEX: StationDecl[EmailEntry] = StationDecl(
    name="email-index",
    path_template="emails",
    model=EmailEntry,
    serialization="json-checkpoint",
    segments=(
        phases("inbox", "shards"),  # materialization layers under the index
        shard_by_hash(2),
    ),
)
