"""Station defs: campaigns/{campaign}/indexes/emails/ (decision 0010).

Data tree:
  indexes/emails/inbox/     — hot write intake (WAL shape B)
  indexes/emails/shards/    — DuckDB-facing materialization
  indexes/emails/CURRENT    — stations commit pointer

Segments are declared at construction time (combinators), not hard-coded
globals: inbox uses DOMAIN_HASH_SHARD (domain → 00..ff); the email address is
the filename, not the shard key. Shards are cold materialization of the same
fold.
"""

from __future__ import annotations

from stations.segments import phases
from stations.station import StationDecl

from cocli.models.campaigns.indexes.email import EmailEntry
from cocli.station_defs.campaigns.indexes import DOMAIN_HASH_SHARD

# path_template is relative to the emails index root (product resolves absolute).
EMAIL_INBOX: StationDecl[EmailEntry] = StationDecl(
    name="email-inbox",
    path_template="inbox",
    model=EmailEntry,
    serialization="usv-or-json-file",
    segments=(
        phases("inbox"),  # hot layer phase name is "inbox" for this station
        DOMAIN_HASH_SHARD,  # domain → 00-ff; filename is the email, not the shard key
    ),
)

EMAIL_SHARDS: StationDecl[EmailEntry] = StationDecl(
    name="email-shards",
    path_template="shards",
    model=EmailEntry,
    serialization="usv-lines",
    segments=(DOMAIN_HASH_SHARD,),
)

EMAIL_INDEX: StationDecl[EmailEntry] = StationDecl(
    name="email-index",
    path_template="emails",
    model=EmailEntry,
    serialization="json-checkpoint",
    segments=(
        phases("inbox", "shards"),  # materialization layers under the index
        DOMAIN_HASH_SHARD,
    ),
)
