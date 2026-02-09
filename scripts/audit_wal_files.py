import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.utils import UNIT_SEP

def audit_wal():
    wal_dir = Path("data/campaigns/roadmap/indexes/google_maps_prospects/wal")
    if not wal_dir.exists():
        print(f"WAL directory not found: {wal_dir}")
        return

    print(f"--- Auditing WAL Files in {wal_dir} ---")
    
    broken_log = Path("broken_wal_files.log")
    broken_files = []
    total_files = 0
    
    # Expected stats
    EXPECTED_COLS = 55
    
    for usv_file in wal_dir.rglob("*.usv"):
        total_files += 1
        try:
            with open(usv_file, 'r', encoding='utf-8') as f:
                first_line = f.readline()
                if not first_line:
                    broken_files.append((usv_file, "Empty file"))
                    continue
                
                # Check for headers
                has_header = False
                if "created_at" in first_line or "place_id" in first_line or "Keyword" in first_line:
                    has_header = True
                
                # Count columns
                parts = first_line.strip("\n\x1e").split(UNIT_SEP)
                col_count = len(parts)
                
                # Check first column (should be place_id starting with ChIJ)
                first_col = parts[0]
                is_valid_pid = first_col.startswith("ChIJ")
                
                issues = []
                
                if has_header:
                    issues.append("HAS_HEADER")
                
                if col_count != EXPECTED_COLS:
                    issues.append(f"Col Count Mismatch: {col_count} (expected {EXPECTED_COLS})")
                
                if not is_valid_pid and not has_header:
                    issues.append(f"Invalid Place ID in col 1: {first_col[:20]}...")
                
                if issues:
                    broken_files.append((usv_file, "; ".join(issues)))
                    
        except Exception as e:
            broken_files.append((usv_file, f"Read Error: {e}"))

    # Report
    print(f"Total WAL Files scanned: {total_files}")
    print(f"Non-conforming files: {len(broken_files)}")
    
    if broken_files:
        with open(broken_log, "w") as f:
            f.write("--- Broken WAL Files Report ---\n")
            f.write(f"Total: {len(broken_files)} / {total_files}\n\n")
            for path, issue in broken_files:
                f.write(f"{path}: {issue}\n")
        
        print(f"Details written to {broken_log}")
        
        # Show a few examples
        print("\nExamples of broken files:")
        for path, issue in broken_files[:10]:
            print(f"  {path.name}: {issue}")

if __name__ == "__main__":
    audit_wal()
