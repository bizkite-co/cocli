import pytest
from frictionless import validate
from pathlib import Path


def test_data_compliance():
    """Verify that compacted.usv conforms to the datapackage schema."""
    # Paths based on project structure
    base = Path(
        "/home/mstouffer/.local/share/cocli_data_dev/campaigns/roadmap/queues/gm-list/completed/results"
    )
    data_file = base / "compacted.usv"
    schema_file = base / "datapackage.json"

    assert data_file.exists(), f"Data file {data_file} not found."
    assert schema_file.exists(), f"Schema file {schema_file} not found."

    # Frictionless validation
    report = validate(str(data_file), schema=str(schema_file))

    # Assert report is valid
    assert report.valid, f"Data compliance failed: {report.flatten()}"
