"""Station defs: campaigns/{campaign}/indexes/emails/ (decision 0010).

Data tree:
  indexes/emails/inbox/     — hot write intake (WAL shape B)
  indexes/emails/shards/    — DuckDB-facing materialization
  indexes/emails/CURRENT    — stations commit pointer
"""

from __future__ import annotations

from stations.station import StationDecl

from cocli.models.campaigns.indexes.email import EmailEntry

# path_template is relative to the emails index root (product resolves absolute).
EMAIL_INBOX: StationDecl[EmailEntry] = StationDecl(
    name="email-inbox",
    path_template="inbox",
    model=EmailEntry,
    serialization="usv-or-json-file",
)

EMAIL_SHARDS: StationDecl[EmailEntry] = StationDecl(
    name="email-shards",
    path_template="shards",
    model=EmailEntry,
    serialization="usv-lines",
)

EMAIL_INDEX: StationDecl[EmailEntry] = StationDecl(
    name="email-index",
    path_template="emails",
    model=EmailEntry,
    serialization="json-checkpoint",
)
