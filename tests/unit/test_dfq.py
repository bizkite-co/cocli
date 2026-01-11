import os
import json
from datetime import datetime, timedelta, UTC
from unittest.mock import patch
from cocli.core.queue.filesystem import FilesystemGmListQueue

def test_filesystem_queue(tmp_path):
    # Patch paths.root to use tmp_path
    with patch('cocli.core.paths.paths.root', tmp_path):
        campaign = "test_dfq_campaign"
        base_dir = tmp_path
        campaign_dir = base_dir / "campaigns" / campaign
        
        # Setup mock Mission Index
        target_tiles = campaign_dir / "indexes" / "target-tiles"
        tile_path = target_tiles / "29.5" / "-98.5"
        tile_path.mkdir(parents=True)
        (tile_path / "dentist.csv").write_text("latitude,longitude\n29.5,-98.5")
        (tile_path / "plumber.csv").write_text("latitude,longitude\n29.5,-98.5")
        
        # Create Queue
        with patch.dict(os.environ, {"HOSTNAME": "worker-1"}):
            q1 = FilesystemGmListQueue(campaign)
        
        with patch.dict(os.environ, {"HOSTNAME": "worker-2"}):
            q2 = FilesystemGmListQueue(campaign)
        
        print("--- Polling Worker 1 ---")
        tasks1 = q1.poll(batch_size=1)
        assert len(tasks1) == 1
        task1 = tasks1[0]
        print(f"Worker 1 claimed: {task1.search_phrase} (Token: {task1.ack_token})")
        
        print("--- Polling Worker 2 ---")
        tasks2 = q2.poll(batch_size=1)
        assert len(tasks2) == 1
        task2 = tasks2[0]
        print(f"Worker 2 claimed: {task2.search_phrase} (Token: {task2.ack_token})")
        assert task1.search_phrase != task2.search_phrase
        
        print("--- Polling again (should be empty) ---")
        tasks3 = q1.poll(batch_size=1)
        assert len(tasks3) == 0
        print("Queue empty as expected.")
        
        print("--- Testing ACK ---")
        # V2: ACK should remove the task directory in pending
        q1.ack(task1)
        task1_dir = q1._get_task_dir(task1.ack_token)
        assert not task1_dir.exists()
        print("ACK successful.")
        
        print("--- Testing Stale Lease Reclamation ---")
        # Manual lease creation for a fake task
        fake_id = "29.5/-98.5/stale_task.csv"
        (tile_path / "stale_task.csv").write_text("stale")
        
        # V2: Lease is inside task dir in pending
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
        
        print("Polling for stale task...")
        # We need to poll specifically for this task. 
        # GmListQueue.poll will find it because it's in target-tiles and not in witness.
        tasks4 = q2.poll(batch_size=10) 
        found_stale = any(t.search_phrase == "stale_task" for t in tasks4)
        assert found_stale
        print("Stale task reclaimed successfully.")

if __name__ == "__main__":
    # This requires pytest to run properly due to tmp_path fixture
    pass