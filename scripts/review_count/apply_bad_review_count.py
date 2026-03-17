from pathlib import Path
from cocli.models.companies.company import Company
from cocli.utils.usv_utils import USVReader
import re

# Paths
recovery_file = Path(
    "data/companies/recovery/review_count/bad-company-index-records.usv"
)

# 1. Load bad company slugs
slugs_to_fix = []
if recovery_file.exists():
    with open(recovery_file, "r", encoding="utf-8") as f:
        reader = USVReader(f)
        header = next(reader)
        for row in reader:
            if row:
                slugs_to_fix.append(row[0])
else:
    print(f"Recovery file not found: {recovery_file}")
    exit(1)

# 2. Identify and Update
print(f"--- Applying Fix: Updating {len(slugs_to_fix)} companies ---")
for slug in slugs_to_fix:
    company = Company.get(slug)
    if company:
        # Check area code
        phone_str = str(company.phone_number or company.phone_1 or "")
        match = re.search(r"^1?(\d{3})", phone_str)
        area_code = match.group(1) if match else ""

        if str(company.reviews_count) == area_code:
            print(f"UPDATING {slug}: reviews_count={company.reviews_count} -> None")
            company.reviews_count = None
            company.save()
        else:
            print(f"SKIP {slug}: No match found.")
    else:
        print(f"ERROR: Company {slug} not found.")

print("--- Fix Applied ---")
