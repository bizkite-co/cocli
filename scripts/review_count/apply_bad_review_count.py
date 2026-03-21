from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.utils.usv_utils import USVReader
import re

recovery_file = (
    paths.companies.path / "recovery" / "misaligned-review-count-records.usv"
)

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

print(f"--- Applying Fix: Updating {len(slugs_to_fix)} companies ---")
for slug in slugs_to_fix:
    company = Company.get(slug)
    if company:
        phone_str = str(company.phone_number or company.phone_1 or "")
        match_phone = re.search(r"^1?[^\\d]*(\\d{3})", phone_str)
        area_code = match_phone.group(1) if match_phone else ""

        street_addr = str(company.street_address or "")
        match_addr = re.search(r"^(\d+)", street_addr)
        street_number = match_addr.group(1) if match_addr else ""

        if (
            str(company.reviews_count) == area_code
            or str(company.reviews_count) == street_number
        ):
            print(f"UPDATING {slug}: reviews_count={company.reviews_count} -> None")
            company.reviews_count = None
            company.save()
        else:
            print(f"SKIP {slug}: No match found.")
    else:
        print(f"ERROR: Company {slug} not found.")

print("--- Fix Applied ---")
