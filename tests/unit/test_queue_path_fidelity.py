# POLICY: frictionless-data-policy-enforcement
from unittest.mock import patch
from cocli.core.queue.filesystem import FilesystemGmListQueue

def test_gmlist_queue_path_fidelity(tmp_path):
    """
    REPRODUCTION TEST: Detects double-sharding in FilesystemGmListQueue.
    If task_id is '2/25.0/-80.0/phrase.usv', the final path must NOT 
    be 'pending/2/2/25.0/...'.
    """
    campaign = "test_campaign"
    # Mock the paths authority to use tmp_path
    with patch('cocli.core.paths.paths.root', tmp_path):
        queue = FilesystemGmListQueue(campaign)
        
        # This simulates a task_id picked up from the discovery-gen pool
        # which is already sharded.
        task_id = "2/25.0/-80.0/dentist.usv"
        
        # Get the internal task directory used for leases
        # Note: _get_task_dir is internal but we use it to verify the bug
        task_dir = queue._get_task_dir(task_id)
        path_str = str(task_dir)
        pass # Removed diagnostic print
        
        # FAILURE CONDITION: If the shard '2' appears twice consecutively
        assert "/2/2/" not in path_str, f"Double-sharding detected in queue path: {path_str}"
        
        # CORRECT CONDITION: Should be queues/gm-list/pending/2/25.0/-80.0/dentist.usv
        assert path_str.endswith("pending/2/25.0/-80.0/dentist.usv")

def test_generic_queue_sharding_fidelity(tmp_path):
    """
    Ensures that standard PlaceID-based tasks (gm-details) are still
    sharded correctly (exactly once) using the new subpath logic.
    """
    from cocli.core.queue.filesystem import FilesystemQueue
    campaign = "test_campaign"
    with patch('cocli.core.paths.paths.root', tmp_path):
        # Base FilesystemQueue uses PlaceID sharding (6th char)
        queue = FilesystemQueue(campaign, "gm-details")
        
        # PlaceID: 6th char is '5'
        task_id = "ChIJ-5-rest"
        
        task_dir = queue._get_task_dir(task_id)
        path_str = str(task_dir)
        
        # CORRECT: .../pending/5/ChIJ-5-rest
        assert "/pending/5/ChIJ-5-rest" in path_str
        # ERROR: .../pending/5/5/ChIJ-5-rest
        assert "/pending/5/5/" not in path_str
