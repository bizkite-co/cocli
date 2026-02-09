import pytest
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.core.utils import UNIT_SEP

@pytest.fixture
def temp_campaign_dir(tmp_path):
    campaign_name = "test_campaign"
    campaign_dir = tmp_path / "campaigns" / campaign_name
    campaign_dir.mkdir(parents=True)
    
    # Create index dir
    index_dir = campaign_dir / "indexes" / "google_maps_prospects"
    index_dir.mkdir(parents=True)
    
    return campaign_dir

def test_append_prospect(temp_campaign_dir, monkeypatch):
    # Mock get_campaign_dir to return our temp dir
    monkeypatch.setattr("cocli.core.prospects_csv_manager.get_campaign_dir", lambda c: temp_campaign_dir)
    
    manager = ProspectsIndexManager("test_campaign")
    prospect = GoogleMapsProspect(
        place_id="ChIJtest123",
        company_slug="test-company",
        name="Test Company",
        campaign_name="test_campaign"
    )
    
    success = manager.append_prospect(prospect)
    assert success
    
    # Check if file exists in sharded path inside wal/
    # ChIJtest123 -> shard is 'e' (index 5)
    expected_path = temp_campaign_dir / "indexes" / "google_maps_prospects" / "wal" / "e" / "ChIJtest123.usv"
    assert expected_path.exists()
    assert prospect.place_id in expected_path.read_text()

def test_has_place_id_wal(temp_campaign_dir, monkeypatch):
    monkeypatch.setattr("cocli.core.prospects_csv_manager.get_campaign_dir", lambda c: temp_campaign_dir)
    manager = ProspectsIndexManager("test_campaign")
    
    place_id = "ChIJwal123"
    # Manual write to WAL (new sharded structure)
    shard = "a" 
    shard_dir = manager.index_dir / "wal" / shard
    shard_dir.mkdir(parents=True)
    (shard_dir / f"{place_id}.usv").write_text("dummy data")
    
    assert manager.has_place_id(place_id)
    assert not manager.has_place_id("nonexistent")

def test_has_place_id_checkpoint(temp_campaign_dir, monkeypatch):
    monkeypatch.setattr("cocli.core.prospects_csv_manager.get_campaign_dir", lambda c: temp_campaign_dir)
    manager = ProspectsIndexManager("test_campaign")
    
    place_id = "ChIJcheckpoint123"
    checkpoint_file = manager._get_checkpoint_path()
    checkpoint_file.write_text(f"{place_id}{UNIT_SEP}some-slug{UNIT_SEP}Some Name\n")
    
    assert manager.has_place_id(place_id)

def test_read_all_prospects_merged(temp_campaign_dir, monkeypatch):
    monkeypatch.setattr("cocli.core.prospects_csv_manager.get_campaign_dir", lambda c: temp_campaign_dir)
    manager = ProspectsIndexManager("test_campaign")
    
    # 1. Add to Checkpoint
    p1 = GoogleMapsProspect(place_id="PID1", company_slug="slug1", name="Name 1", campaign_name="test_campaign")
    p2 = GoogleMapsProspect(place_id="PID2", company_slug="slug2", name="Name 2", campaign_name="test_campaign")
    checkpoint_file = manager._get_checkpoint_path()
    checkpoint_file.write_text(p1.to_usv() + p2.to_usv())
    
    # 2. Add to WAL (Overwrite p2, add p3)
    p2_new = GoogleMapsProspect(place_id="PID2", company_slug="slug2", name="Updated Name 2", campaign_name="test_campaign")
    p3 = GoogleMapsProspect(place_id="PID3", company_slug="slug3", name="Name 3", campaign_name="test_campaign")
    manager.append_prospect(p2_new)
    manager.append_prospect(p3)
    
    prospects = list(manager.read_all_prospects())
    assert len(prospects) == 3
    
    # Check if p2 is the updated one
    pid_to_name = {p.place_id: p.name for p in prospects}
    assert pid_to_name["PID1"] == "Name 1"
    assert pid_to_name["PID2"] == "Updated Name 2"
    assert pid_to_name["PID3"] == "Name 3"