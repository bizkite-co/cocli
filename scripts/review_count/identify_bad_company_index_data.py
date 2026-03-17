from cocli.utils.usv_utils import USVReader, USVWriter
from pathlib import Path
from cocli.models.companies.company import Company
import re

# Paths
recovery_file = Path(
    "data/campaigns/roadmap/recovery/review-count-matches-area-code.usv"
)
output_path = Path("data/companies/recovery/bad-company-index-records.usv")
output_path.parent.mkdir(parents=True, exist_ok=True)

# 1. Load bad company slugs using USVReader
bad_companies = []
if recovery_file.exists():
    with open(recovery_file, "r", encoding="utf-8") as f:
        reader = USVReader(f)
        header = next(reader)  # Consume header
        for row in reader:
            if row:
                bad_companies.append(row[0])  # company_slug is index 0
else:
    print(f"Recovery file not found: {recovery_file}")
    exit(1)

# 2. Check each bad company's index file
problematic_companies = []


# Robust area code extractor
def get_area_code(phone_str):
    if not phone_str:
        return ""
    match = re.search(r"^1?(\d{3})", str(phone_str))
    return match.group(1) if match else ""


for slug in bad_companies:
    company = Company.get(slug)
    if company and company.reviews_count is not None:
        phone_str = str(company.phone_number or company.phone_1 or "")
        area_code = get_area_code(phone_str)

        if str(company.reviews_count) == area_code:
            problematic_companies.append(
                {
                    "slug": company.slug,
                    "reviews": company.reviews_count,
                    "phone": phone_str,
                }
            )

# 3. Save to recovery file using USVWriter
output_path.parent.mkdir(parents=True, exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    writer = USVWriter(f)
    writer.writerow(["company_slug", "reviews_count", "phone"])  # Header
    for c in problematic_companies:
        writer.writerow([c["slug"], str(c["reviews"]), c["phone"]])

print(f"Found {len(problematic_companies)} problematic records.")
print(f"Path: {output_path.absolute()}")
print(f"Content:\n{output_path.read_text(encoding='utf-8')}")
