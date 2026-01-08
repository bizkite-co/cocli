import csv
import os
from pathlib import Path

csv_file = "anomalous_emails.csv"

if not Path(csv_file).exists():
    print(f"Error: {csv_file} not found. Run the audit script first.")
    exit(1)

with open(csv_file, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        json_path = Path(row['path'])
        if json_path.exists():
            print(f"Removing anomalous email record: {json_path}")
            os.remove(json_path)
            
            # If the parent directory (domain slug) is now empty, remove it too
            domain_dir = json_path.parent
            if domain_dir.is_dir() and not any(domain_dir.iterdir()):
                print(f"Removing empty domain directory: {domain_dir}")
                domain_dir.rmdir()

print("Cleanup complete.")
