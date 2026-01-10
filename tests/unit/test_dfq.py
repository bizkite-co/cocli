import os
import shutil
from cocli.core.queue.filesystem import FilesystemGmListQueue
from cocli.core.config import get_cocli_base_dir

def test_filesystem_queue():
    campaign = "test_dfq_campaign"
    base_dir = get_cocli_base_dir()
    campaign_dir = base_dir / "campaigns" / campaign
    
    # Cleanup
    if campaign_dir.exists():
        shutil.rmtree(campaign_dir)
    witness_dir = base_dir / "indexes" / "scraped-tiles"
    if witness_dir.exists():
        shutil.rmtree(witness_dir)
    
    # Setup mock Mission Index
    target_tiles = campaign_dir / "indexes" / "target-tiles"
    tile_path = target_tiles / "29.5" / "-98.5"
    tile_path.mkdir(parents=True)
    (tile_path / "dentist.csv").write_text("latitude,longitude\n29.5,-98.5")
    (tile_path / "plumber.csv").write_text("latitude,longitude\n29.5,-98.5")
    
    # Create Queue
    os.environ["HOSTNAME"] = "worker-1"
    q1 = FilesystemGmListQueue(campaign)
    
    os.environ["HOSTNAME"] = "worker-2"
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
    # Simulate witness for dentist
    witness_dir = base_dir / "indexes" / "scraped-tiles"
    witness_path = witness_dir / task1.ack_token
    witness_path.parent.mkdir(parents=True, exist_ok=True)
    witness_path.write_text("done")
    
    q1.ack(task1)
    assert not (campaign_dir / "active-leases" / "gm-list" / f"{task1.ack_token.replace('/', '_')}.lease").exists()
    print("ACK successful.")
    
    print("--- Testing Stale Lease Reclamation ---")
    # Manual lease creation for a fake task
    fake_id = "29.5/-98.5/stale_task.csv"
    (tile_path / "stale_task.csv").write_text("stale")
    
    lease_path = campaign_dir / "active-leases" / "gm-list" / f"{fake_id.replace('/', '_')}.lease"
    import json
    from datetime import datetime, timedelta
    
    stale_time = (datetime.utcnow() - timedelta(minutes=20)).isoformat()
    with open(lease_path, 'w') as f:
        json.dump({
            "worker_id": "dead-worker",
            "created_at": stale_time,
            "heartbeat_at": stale_time,
            "expires_at": stale_time
        }, f)
    
    print("Polling for stale task...")
    tasks4 = q2.poll(batch_size=10) # Should reclaim plumber lease if it was nacked, but here we just want the stale one
    found_stale = any(t.search_phrase == "stale_task" for t in tasks4)
    assert found_stale
    print("Stale task reclaimed successfully.")

    # Cleanup
    shutil.rmtree(campaign_dir)
    print("Test Passed!")

if __name__ == "__main__":
    test_filesystem_queue()
