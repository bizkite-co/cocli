from cocli.core.prospects_csv_manager import ProspectsIndexManager
import logging
from itertools import islice

logging.basicConfig(level=logging.INFO)

def test_100():
    manager = ProspectsIndexManager("roadmap")
    print("Attempting to parse first 100 prospects from index...")
    
    # read_all_prospects will now skip invalid ones
    count = 0
    valid_count = 0
    for p in islice(manager.read_all_prospects(), 100):
        count += 1
        valid_count += 1
        if count % 20 == 0:
            print(f"Parsed {count}...")
            
    print(f"Finished. Successfully parsed {valid_count} unique valid prospects.")

if __name__ == "__main__":
    test_100()
