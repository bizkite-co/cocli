from pathlib import Path
from cocli.models.companies.company import Company
import re

# Paths
recovery_file = Path(
    "data/companies/recovery/review_count/bad-company-index-records.usv"
)
# Note: This script is for REVIEWing the plan only.
# It does NOT apply changes.

# 1. Load bad company slugs
slugs_to_fix = []
if recovery_file.exists():
    with open(recovery_file, "r", encoding="utf-8") as f:
        # Use USVReader here because we used USVWriter to write it
        from cocli.utils.usv_utils import USVReader

        reader = USVReader(f)
        header = next(reader)
        for row in reader:
            if row:
                slugs_to_fix.append(row[0])
else:
    print(f"Recovery file not found: {recovery_file}")
    exit(1)

# 2. Identify and Plan the update
print(f"--- Plan: Updating {len(slugs_to_fix)} companies ---")
for slug in slugs_to_fix:
    company = Company.get(slug)
    if company:
        # Check if the reviews_count matches the area code
        phone_str = str(company.phone_number or company.phone_1 or "")
        match = re.search(r"^1?(\d{3})", phone_str)
        area_code = match.group(1) if match else ""

        current_reviews = company.reviews_count

        # Only print if we are actually making a change
        if current_reviews is not None and str(current_reviews) == area_code:
            print(f"PLAN: Update {slug}: reviews_count={current_reviews} -> '' (blank)")
        elif current_reviews is not None:
            print(
                f"SKIP: {slug}: reviews_count={current_reviews} does not match area_code={area_code}"
            )
        else:
            print(f"SKIP: {slug}: reviews_count is already None")
    else:
        print(f"ERROR: Company {slug} not found.")

print("--- End of Plan ---")
