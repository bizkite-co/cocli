import pytest
import hashlib
from pathlib import Path
from cocli.core.infrastructure.wasi import WasiRunner
from cocli.core.store.prospects import ProspectsStore

def test_wasi_runner_hashing(tmp_path: Path):
    """Verifies that WasiRunner correctly hashes a WASM binary."""
    wasm_file = tmp_path / "test.wasm"
    # Minimal WASM header
    content = b"\x00asm\x01\x00\x00\x00"
    wasm_file.write_bytes(content)
    
    expected_hash = hashlib.sha256(content).hexdigest()
    runner = WasiRunner(wasm_file)
    
    assert runner.wasi_hash == expected_hash

def test_prospects_store_integrity_enforcement(tmp_path: Path):
    """Verifies that ProspectsStore enforces WASI hash parity."""
    store_root = tmp_path / "prospects"
    store_root.mkdir()
    
    # 1. Initialize store with a WASI hash
    from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
    fake_hash = "abc123expected"
    GoogleMapsProspect.save_datapackage(
        store_root, 
        "google-maps-prospects", 
        "prospects.checkpoint.usv",
        wasi_hash=fake_hash
    )
    
    store = ProspectsStore("test-campaign")
    # Manually set root for testing
    store._root = store_root
    
    # 2. Verify parity works
    assert store.enforce_integrity(fake_hash) is True
    
    # 3. Verify mismatch raises error
    with pytest.raises(RuntimeError) as excinfo:
        store.enforce_integrity("wronghash")
    
    assert "WASI Integrity Violation" in str(excinfo.value)
    assert fake_hash in str(excinfo.value)

def test_datapackage_generation_includes_wasi_hash(tmp_path: Path):
    """Verifies that cocli:wasi_hash is saved in datapackage.json."""
    from cocli.models.campaigns.indexes.domains import WebsiteDomainCsv
    import json
    
    wasi_hash = "sha256:immutable-code-v1"
    WebsiteDomainCsv.save_datapackage(
        tmp_path, 
        "domains", 
        "*.usv", 
        wasi_hash=wasi_hash
    )
    
    sentinel = tmp_path / "datapackage.json"
    assert sentinel.exists()
    
    with open(sentinel, "r") as f:
        data = json.load(f)
        assert data["cocli:wasi_hash"] == wasi_hash
