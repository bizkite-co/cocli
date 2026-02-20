from typing import Any
from pathlib import Path
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader

def test_single_file_isolated(file_path: Path) -> bool:
    print(f"Testing isolated parse of: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        # Detect headers
        first_line = f.readline()
        f.seek(0)
        
        if "created_at" in first_line:
            print("Detected headered USV")
            reader = USVDictReader(f)
        else:
            print("Detected headerless USV")
            # Same ordered fields as manager
            ordered_fields = ["place_id", "company_slug", "name", "phone_1"]
            all_fields = list(GoogleMapsProspect.model_fields.keys())
            remaining = [f for f in all_fields if f not in ordered_fields]
            fieldnames = ordered_fields + remaining
            reader = USVDictReader(f, fieldnames=fieldnames)
        
        for row in reader:
            # The normalization logic we just added to the manager:
            normalized_row: dict[str, Any] = {}
            for k, v in row.items():
                if not k:
                    continue
                key = k.lower().replace(" ", "_")
                if key == "place_id":
                    key = "place_id"
                if key == "id" and not normalized_row.get("place_id"):
                    key = "place_id"
                normalized_row[key] = v
            
            try:
                model_data = {k: v for k, v in normalized_row.items() if k in GoogleMapsProspect.model_fields}
                p = GoogleMapsProspect.model_validate(model_data)
                print(f"SUCCESS: Parsed {p.name} ({p.place_id})")
                return True
            except Exception as e:
                print(f"VALIDATION ERROR: {e}")
                return False
        return False

if __name__ == "__main__":
    target = Path("data/campaigns/roadmap/indexes/google_maps_prospects/wal/5/ChIJj5vRbBl_a4cR3SgY4OXAuWE.usv")
    test_single_file_isolated(target)