import pytest
import json
from pathlib import Path
from cocli.models.base import BaseUsvModel, SchemaConflictError

class MockModelV1(BaseUsvModel):
    id: str
    name: str

class MockModelV2_Good(BaseUsvModel):
    id: str
    name: str
    description: str  # Appended (Good)

class MockModelV2_Bad_Order(BaseUsvModel):
    name: str  # Reordered (Bad)
    id: str

class MockModelV2_Bad_Missing(BaseUsvModel):
    id: str  # 'name' missing (Bad)

def test_usv_schema_append_only(tmp_path: Path):
    """Verifies that appending a field is allowed."""
    # 1. Save V1
    MockModelV1.save_datapackage(tmp_path, "test", "*.usv")
    assert (tmp_path / "datapackage.json").exists()
    
    # 2. Save V2 (Good)
    MockModelV1.save_datapackage(tmp_path, "test", "*.usv") # Re-save same should be fine
    MockModelV2_Good.save_datapackage(tmp_path, "test", "*.usv") # Append should be fine
    
    with open(tmp_path / "datapackage.json", "r") as f:
        data = json.load(f)
        fields = data["resources"][0]["schema"]["fields"]
        assert len(fields) == 3
        assert fields[2]["name"] == "description"

def test_usv_schema_blocks_reorder(tmp_path: Path):
    """Verifies that reordering fields is blocked."""
    MockModelV1.save_datapackage(tmp_path, "test", "*.usv")
    
    with pytest.raises(SchemaConflictError) as excinfo:
        MockModelV2_Bad_Order.save_datapackage(tmp_path, "test", "*.usv")
    
    assert "Schema change detected in existing columns" in str(excinfo.value)
    assert "Position 0: Expected 'id', found 'name'" in excinfo.value.diff[0]

def test_usv_schema_blocks_removal(tmp_path: Path):
    """Verifies that removing fields is blocked."""
    MockModelV1.save_datapackage(tmp_path, "test", "*.usv")
    
    with pytest.raises(SchemaConflictError) as excinfo:
        MockModelV2_Bad_Missing.save_datapackage(tmp_path, "test", "*.usv")
    
    assert "Field count decreased" in str(excinfo.value)

def test_usv_schema_force_override(tmp_path: Path):
    """Verifies that force=True bypasses the check."""
    MockModelV1.save_datapackage(tmp_path, "test", "*.usv")
    
    # This would normally fail, but force=True allows it
    MockModelV2_Bad_Order.save_datapackage(tmp_path, "test", "*.usv", force=True)
    
    with open(tmp_path / "datapackage.json", "r") as f:
        data = json.load(f)
        fields = data["resources"][0]["schema"]["fields"]
        assert fields[0]["name"] == "name"
