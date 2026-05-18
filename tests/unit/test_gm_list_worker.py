"""Unit tests for gm-list compactor worker validation."""

import json


def test_compute_self_hash():
    """Test that compute_self_hash returns a valid SHA256 hash."""
    from scripts.compact_gm_list_wal import compute_self_hash
    
    result = compute_self_hash()
    
    assert result.startswith("sha256:")
    # SHA256 hex is 64 characters
    assert len(result) == 7 + 64  # "sha256:" + 64 hex chars


def test_find_worker_json_priority(tmp_path):
    """Test that find_worker_json checks paths in priority order."""
    from scripts.compact_gm_list_wal import (
        find_worker_json
    )
    
    # Create test structure
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    campaign_dir = data_dir / "campaigns" / "test" / "queues" / "gm-list" / "completed"
    campaign_dir.mkdir(parents=True)
    
    global_registry = data_dir / ".registry" / "index-workers" / "gm-list-compactor"
    global_registry.mkdir(parents=True)
    global_worker = global_registry / "worker.json"
    global_worker.write_text(json.dumps({"hash": "sha256:global"}))
    
    campaign_registry = campaign_dir / "registry"
    campaign_registry.mkdir()
    campaign_worker = campaign_registry / "gm-list-compactor.json"
    campaign_worker.write_text(json.dumps({"hash": "sha256:campaign"}))
    
    legacy_dir = campaign_dir / "shards"
    legacy_dir.mkdir()
    legacy = legacy_dir / "worker.json"
    legacy.write_text(json.dumps({"hash": "sha256:legacy"}))
    
    # Monkey-patch paths for testing
    import scripts.compact_gm_list_wal as module
    
    original_data = module.DATA_DIR
    original_shards = module.SHARDS_DIR
    original_registry = module.REGISTRY_JSON
    original_campaign = module.CAMPAIGN_REGISTRY_JSON
    original_worker = module.WORKER_JSON
    
    module.DATA_DIR = data_dir
    module.SHARDS_DIR = legacy_dir
    module.REGISTRY_JSON = global_worker
    module.CAMPAIGN_REGISTRY_JSON = campaign_worker
    module.WORKER_JSON = legacy
    
    try:
        # Test campaign registry takes priority
        result = find_worker_json()
        assert result == campaign_worker
        
        # Remove campaign registry, should fall back to global
        campaign_worker.unlink()
        result = find_worker_json()
        assert result == module.REGISTRY_JSON
        
        # Remove global registry, should fall back to legacy
        module.REGISTRY_JSON.unlink()
        result = find_worker_json()
        assert result == legacy
        
        # Remove all - should return None
        legacy.unlink()
        result = find_worker_json()
        assert result is None
        
    finally:
        # Restore original paths
        module.DATA_DIR = original_data
        module.SHARDS_DIR = original_shards
        module.REGISTRY_JSON = original_registry
        module.CAMPAIGN_REGISTRY_JSON = original_campaign
        module.WORKER_JSON = original_worker


def test_validate_worker_success(tmp_path):
    """Test that validation passes with matching hash."""
    from scripts.compact_gm_list_wal import (
        validate_worker
    )
    import scripts.compact_gm_list_wal as module
    
    # Create test registry with correct hash
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    registry_dir = data_dir / ".registry" / "index-workers" / "gm-list-compactor"
    registry_dir.mkdir(parents=True)
    
    # Get actual script path from repo root
    from scripts.compact_gm_list_wal import compute_self_hash
    actual_hash = compute_self_hash()
    
    worker_json = registry_dir / "worker.json"
    worker_json.write_text(json.dumps({"hash": actual_hash}))
    
    # Monkey-patch
    original_registry = module.REGISTRY_JSON
    original_campaign = module.CAMPAIGN_REGISTRY_JSON
    
    module.REGISTRY_JSON = worker_json
    module.CAMPAIGN_REGISTRY_JSON = tmp_path / "nonexistent"
    
    try:
        # Validation should pass
        result = validate_worker()
        assert result is True
    finally:
        module.REGISTRY_JSON = original_registry
        module.CAMPAIGN_REGISTRY_JSON = original_campaign


def test_validate_worker_hash_mismatch(tmp_path):
    """Test that validation fails with mismatched hash."""
    from scripts.compact_gm_list_wal import validate_worker
    import scripts.compact_gm_list_wal as module
    
    # Create test registry with wrong hash
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    registry_dir = data_dir / ".registry" / "index-workers" / "gm-list-compactor"
    registry_dir.mkdir(parents=True)
    
    worker_json = registry_dir / "worker.json"
    worker_json.write_text(json.dumps({"hash": "sha256:wrong_hash"}))
    
    # Monkey-patch
    original_registry = module.REGISTRY_JSON
    original_campaign = module.CAMPAIGN_REGISTRY_JSON
    
    module.REGISTRY_JSON = worker_json
    module.CAMPAIGN_REGISTRY_JSON = tmp_path / "nonexistent"
    
    try:
        # Validation should fail
        result = validate_worker()
        assert result is False
    finally:
        module.REGISTRY_JSON = original_registry
        module.CAMPAIGN_REGISTRY_JSON = original_campaign


def test_validate_worker_missing(tmp_path):
    """Test that validation fails when no worker.json exists."""
    from scripts.compact_gm_list_wal import validate_worker
    import scripts.compact_gm_list_wal as module
    
    # Monkey-patch with non-existent paths
    original_registry = module.REGISTRY_JSON
    original_campaign = module.CAMPAIGN_REGISTRY_JSON
    
    module.REGISTRY_JSON = tmp_path / "nonexistent" / "worker.json"
    module.CAMPAIGN_REGISTRY_JSON = tmp_path / "nonexistent"
    
    try:
        result = validate_worker()
        assert result is False
    finally:
        module.REGISTRY_JSON = original_registry
        module.CAMPAIGN_REGISTRY_JSON = original_campaign