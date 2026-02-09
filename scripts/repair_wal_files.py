import sys
from pathlib import Path
from datetime import datetime, UTC
from pydantic import ValidationError

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.models.google_maps_prospect import GoogleMapsProspect
from cocli.models.google_maps_raw import GoogleMapsRawResult
from cocli.core.utils import UNIT_SEP
from cocli.utils.usv_utils import USVDictReader

def repair_wal(execute: bool = False):
    broken_log = Path("broken_wal_files.log")
    if not broken_log.exists():
        print("broken_wal_files.log not found. Run audit first.")
        return

    repair_error_log = Path("repair_validation_errors.log")
    repair_error_log.write_text(f"--- Repair Validation Errors ({datetime.now(UTC)}) ---\n")

    print(f"--- Repairing WAL Files (Execute: {execute}) ---")
    
    repaired_count = 0
    error_count = 0
    
    with open(broken_log, 'r') as f:
        lines = f.readlines()
    
    file_paths = []
    for line in lines:
        if line.startswith("data/campaigns"):
            path_str = line.split(": ")[0]
            file_paths.append(Path(path_str))

    total = len(file_paths)
    print(f"Queueing {total} files for validation/repair.")

    # Get model fields for filtering
    raw_fields = set(GoogleMapsRawResult.model_fields.keys())
    prospect_fields = set(GoogleMapsProspect.model_fields.keys())

    for i, path in enumerate(file_paths):
        if not path.exists():
            continue
            
        try:
            repaired_prospect = None
            
            with open(path, 'r', encoding='utf-8') as f:
                first_line = f.readline()
                f.seek(0)
                
                # Use USVDictReader to handle header mapping
                reader = USVDictReader(f)
                row = next(reader, None)
                
                if row:
                    # Filter keys to match model
                    filtered_row = {k: v for k, v in row.items() if k in raw_fields or k in prospect_fields}
                    
                    try:
                        # Case 1: Raw Result mapping
                        if "Keyword" in first_line or "Full_Address" in first_line:
                            raw = GoogleMapsRawResult.model_validate(filtered_row)
                            repaired_prospect = GoogleMapsProspect.from_raw(raw)
                        
                        # Case 2: Headered Prospect mapping
                        elif "created_at" in first_line and "place_id" in first_line:
                            repaired_prospect = GoogleMapsProspect.model_validate(filtered_row)
                        
                        # Verify the result has the correct number of columns
                        if repaired_prospect:
                            usv_line = repaired_prospect.to_usv()
                            col_count = len(usv_line.strip().split(UNIT_SEP))
                            if col_count != 55:
                                raise ValueError(f"Repair produced wrong col count: {col_count}")

                    except ValidationError as ve:
                        with open(repair_error_log, 'a') as ef:
                            ef.write(f"VALIDATION FAILED: {path.name}\n{ve}\n\n")
                        repaired_prospect = None
                    except Exception as e:
                        with open(repair_error_log, 'a') as ef:
                            ef.write(f"MAPPING ERROR: {path.name} | {e}\n")
                        repaired_prospect = None

            if repaired_prospect:
                if execute:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(repaired_prospect.to_usv())
                repaired_count += 1
            else:
                error_count += 1
                
            if i % 1000 == 0:
                print(f"Processed {i}/{total}...")

        except Exception as e:
            print(f"Critical System Error processing {path.name}: {e}")
            error_count += 1

    print("\nProcessing Complete.")
    print(f"Successfully Validated/Mapped: {repaired_count}")
    print(f"Failed Validation: {error_count}")
    if error_count > 0:
        print(f"Details on failures written to {repair_error_log}")

if __name__ == "__main__":
    execute = "--execute" in sys.argv
    repair_wal(execute=execute)