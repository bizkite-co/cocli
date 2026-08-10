import os
import json
from datetime import datetime, timedelta, UTC
from unittest.mock import patch
from cocli.core.queue.filesystem import FilesystemGmListQueue


def test_filesystem_queue(tmp_path):
    """poll()/ack() only ever touch gm-list's own pending/completed (fixed
    2026-08-09 - previously read from discovery-gen/completed, a foreign
    queue's directory). Fixtures below write directly into pending_dir,
    matching the real copy step (cocli data queue enqueue-gm-list)."""
    with patch('cocli.core.paths.paths.root', tmp_path):
        campaign = "test/test_dfq_campaign"

        with patch.dict(os.environ, {"HOSTNAME": "worker-1"}):
            q1 = FilesystemGmListQueue(campaign)

        with patch.dict(os.environ, {"HOSTNAME": "worker-2"}):
            q2 = FilesystemGmListQueue(campaign)

        # Setup: two tasks already sitting in gm-list/pending/, as the copy
        # step would have placed them.
        tile_dir = q1.pending_dir / "2" / "29.5" / "-98.5"
        tile_dir.mkdir(parents=True)
        (tile_dir / "dentist.usv").write_text("29.5_-98.5\x1fdentist\x1f29.500000\x1f-98.500000")
        (tile_dir / "plumber.usv").write_text("29.5_-98.5\x1fplumber\x1f29.500000\x1f-98.500000")

        tasks1 = q1.poll(batch_size=1)
        assert len(tasks1) == 1
        task1 = tasks1[0]

        tasks2 = q2.poll(batch_size=1)
        assert len(tasks2) == 1
        task2 = tasks2[0]
        assert task1.search_phrase != task2.search_phrase

        tasks3 = q1.poll(batch_size=1)
        assert len(tasks3) == 0

        # ack() deletes both the lease dir and the source pending file.
        assert task1.ack_token is not None
        pending_file = q1.pending_dir / task1.ack_token
        assert pending_file.exists()
        q1.ack(task1)
        assert not pending_file.exists()
        assert not q1._get_task_dir(task1.ack_token).exists()

        # Manual stale lease creation for a fake task.
        (tile_dir / "stale_task.usv").write_text("29.5_-98.5\x1fstale_task\x1f29.500000\x1f-98.500000")
        fake_id = "2/29.5/-98.5/stale_task.usv"

        task_dir = q2._get_task_dir(fake_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        lease_path = task_dir / "lease.json"

        stale_time = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
        with open(lease_path, 'w') as f:
            json.dump({
                "worker_id": "dead-worker",
                "created_at": stale_time,
                "heartbeat_at": stale_time,
                "expires_at": stale_time
            }, f)

        # A stale lease gets reclaimed on a subsequent poll.
        tasks4 = q2.poll(batch_size=10)
        found_stale = any(t.search_phrase == "stale_task" for t in tasks4)
        assert found_stale


if __name__ == "__main__":
    # This requires pytest to run properly due to tmp_path fixture
    pass
