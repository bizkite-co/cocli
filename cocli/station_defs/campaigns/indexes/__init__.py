"""Index stations under campaigns/{campaign}/indexes/…"""

from stations.segments import shard_by_hash

# Shared by email + domain indexes (sha256 hex width 2). Managers must
# collect_shard the decl rather than hashlib.sha256(...)[:2] in parallel.
DOMAIN_HASH_SHARD = shard_by_hash(2)

