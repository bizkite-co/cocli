import sys
from pathlib import Path
from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem

def check_fidelity(file_path: str) -> None:
    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {file_path}")
        return

    print(f"--- Fidelity Check: {path.name} ---")
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            try:
                # This uses the model's self-describing USV parser
                item = GoogleMapsListItem.from_usv(line)
                print(f"\n[Record {i+1}] {item.name}")
                print(f"  Place ID: {item.place_id}")
                print(f"  Rating:   {item.average_rating if item.average_rating is not None else 'BLANK'}")
                print(f"  Reviews:  {item.reviews_count if item.reviews_count is not None else 'BLANK'}")
                print(f"  Phone:    {item.phone or 'BLANK'}")
                print(f"  Domain:   {item.domain or 'BLANK'}")
            except Exception as e:
                print(f"\n[Record {i+1}] PARSE ERROR: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/check_canary_fidelity.py <usv_file>")
        sys.exit(1)
    check_fidelity(sys.argv[1])
