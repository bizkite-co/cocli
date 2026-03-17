from pathlib import Path
from cocli.utils.usv_utils import USVReader
import json

# Setup
usv_path = Path(
    "data/campaigns/roadmap/indexes/google_maps_prospects/prospects.checkpoint.usv"
)
dp_path = Path("data/campaigns/roadmap/indexes/google_maps_prospects/datapackage.json")

# Read schema
with open(dp_path, "r") as f:
    pkg = json.load(f)
    fields = pkg["resources"][0]["schema"]["fields"]

# Read specific line (21505) - note: sed is 1-indexed, Python reader loop is 0-indexed
# Line 21505 is index 21504
target_idx = 21504

with open(usv_path, "r", encoding="utf-8") as f:
    reader = USVReader(f)
    for idx, row in enumerate(reader):
        if idx == target_idx:
            print(f"Inspecting Row {idx} (Line {idx + 1}):")
            for i, (field, value) in enumerate(zip(fields, row)):
                print(f"{i:02}: {field['name']:<25} | {value}")

            # Print remaining USV row elements if they exist
            if len(row) > len(fields):
                print("--- Extra elements found ---")
                for i in range(len(fields), len(row)):
                    print(f"{i:02}: EXTRA                 | {row[i]}")
            break
