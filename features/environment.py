import shutil
from pathlib import Path

def before_scenario(context, scenario):
    # Clean up test_data directory before each scenario
    test_data_dir = Path("./test_data")
    if test_data_dir.exists():
        shutil.rmtree(test_data_dir)
    test_data_dir.mkdir(parents=True, exist_ok=True)
    (test_data_dir / "companies").mkdir(exist_ok=True)
    (test_data_dir / "people").mkdir(exist_ok=True)