"""Shared rule for "does this filename represent one real queue task record."

Every queue directory mixes real task/result data (.usv, .json) with
bookkeeping overhead that must NOT be counted as a task: a shared
datapackage.json schema sidecar, and per-task lease/attempts files that
only exist while a task is claimed or has been retried. A raw file/key
count over a queue prefix silently double- (or triple-) counts every
claimed or retried task, which is exactly why cocli audit cluster's queue
depths used to overcount relative to the true number of distinct tasks -
see task-agent ticket audit-cluster-queue-depths-overcounted-raw-file-keys.

Used by both FilesystemQueueBase.count_state() (local os.walk) and
cocli/commands/audit.py's S3-key-based queue depth counts - one rule,
two iteration mechanisms, so they can't drift apart.
"""


_SIDECAR_FILENAMES = {"datapackage.json", "mission.usv", "schema_ledger.json"}


def is_valid_task_data_file(filename: str) -> bool:
    """True if `filename` (basename only, no path) is a real task/result
    record - not a schema sidecar, master mission manifest, lease, or
    retry-attempts bookkeeping file."""
    if filename in _SIDECAR_FILENAMES:
        return False
    if filename.startswith("lease") or filename.startswith("attempts"):
        return False
    return filename.endswith(".usv") or filename.endswith(".json")
