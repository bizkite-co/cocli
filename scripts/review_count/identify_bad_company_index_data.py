from cocli.utils.usv_utils import USVReader, USVWriter
from cocli.core.paths import paths
from cocli.models.companies.company import Company
import re

campaign_name = "roadmap"

recovery_file = (
    paths.campaign(campaign_name).path
    / "recovery"
    / "review-count-matches-area-code.usv"
)
recovery_dir = paths.companies.path / "recovery"
output_path = recovery_dir / "bad-company-index-records.usv"

bad_companies = []
if recovery_file.exists():
    with open(recovery_file, "r", encoding="utf-8") as f:
        reader = USVReader(f)
        header = next(reader)
        for row in reader:
            if row:
                bad_companies.append(row[0])
else:
    print(f"Recovery file not found: {recovery_file}")
    exit(1)

problematic_companies = []


def get_area_code(phone_str):
    if not phone_str:
        return ""
    match = re.search(r"^1?[^\\d]*(\\d{3})", str(phone_str))
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

recovery_dir.mkdir(parents=True, exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    writer = USVWriter(f)
    writer.writerow(["company_slug", "reviews_count", "phone"])
    for c in problematic_companies:
        writer.writerow([c["slug"], str(c["reviews"]), c["phone"]])

print(f"Found {len(problematic_companies)} problematic records.")
print(f"Path: {output_path}")
if problematic_companies:
    print(f"Content:\n{output_path.read_text(encoding='utf-8')[:500]}")
