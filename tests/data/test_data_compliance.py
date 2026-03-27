import pytest
from frictionless import validate
from pathlib import Path

# Path based on project structure
DATA_BASE = Path(
    "/home/mstouffer/.local/share/cocli_data_dev/campaigns/roadmap/queues/gm-list/completed/results"
)


@pytest.mark.skipif(
    not (DATA_BASE / "compacted.usv").exists(), reason="Data file not found"
)
def test_data_compliance():
    """Verify that compacted.usv conforms to the datapackage schema."""
    data_file = DATA_BASE / "compacted.usv"
    schema_file = DATA_BASE / "datapackage.json"

    # Frictionless validation
    report = validate(str(data_file), schema=str(schema_file))

    # Assert report is valid
    assert report.valid, f"Data compliance failed: {report.flatten()}"
