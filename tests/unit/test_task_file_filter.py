"""is_valid_task_data_file: the one rule for "is this a real task/result
record" shared between FilesystemQueueBase.count_state() (local os.walk)
and cocli audit cluster's S3-key-based queue depth counts. Exists because
a raw file/key count over a queue prefix silently overcounts real tasks -
every claimed task adds a lease*.json, every retried one an attempts*.json,
and datapackage.json/mission.usv sidecars sit in most of these prefixes
too - none of those are tasks.
"""

from cocli.core.queue.task_file_filter import is_valid_task_data_file


def test_accepts_usv_and_json_data_files() -> None:
    assert is_valid_task_data_file("commercial-vinyl-flooring-contractor.usv")
    assert is_valid_task_data_file("ChIJaxQdG-hnA4wRDamuMmSaDwI.json")
    assert is_valid_task_data_file("task.json")


def test_rejects_datapackage_sidecar() -> None:
    assert not is_valid_task_data_file("datapackage.json")


def test_rejects_mission_manifest() -> None:
    assert not is_valid_task_data_file("mission.usv")


def test_rejects_schema_ledger() -> None:
    assert not is_valid_task_data_file("schema_ledger.json")


def test_rejects_lease_files() -> None:
    assert not is_valid_task_data_file("lease.json")
    assert not is_valid_task_data_file("lease_abc123.json")


def test_rejects_attempts_files() -> None:
    assert not is_valid_task_data_file("attempts.json")
    assert not is_valid_task_data_file("attempts_abc123.json")


def test_rejects_files_with_no_relevant_extension() -> None:
    assert not is_valid_task_data_file("readme.txt")
    assert not is_valid_task_data_file("notes")
