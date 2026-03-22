from pathlib import Path
from cocli.utils.usv_utils import normalize_usv_record_separators

results_dir = Path(
    "/home/mstouffer/.local/share/cocli_data_dev/campaigns/roadmap/queues/gm-list/completed/results"
)

metrics = {
    "total_records": 0,
    "valid_records": 0,
    "phone": 0,
    "website": 0,
    "reviews_count": 0,
}


def is_valid(row):
    # Criteria: 9 fields AND first field starts with 'ChI'
    if len(row) == 9 and row[0].startswith("ChI"):
        return True
    return False


# Iterate through all restored USV files
for usv_file in results_dir.rglob("*.usv"):
    if usv_file.name == "corrupted-records.usv" or usv_file.name == "datapackage.json":
        continue

    with open(usv_file, "rb") as f:
        # Use proper normalization
        content = normalize_usv_record_separators(f.read())

    # Split records
    records = [r for r in content.split("\n") if r.strip()]

    cleaned_records = []
    for rec in records:
        fields = rec.split("\x1f")

        if is_valid(fields):
            cleaned_records.append(rec)

            # Update metrics
            metrics["valid_records"] += 1
            if fields[3] and fields[3].strip():
                metrics["phone"] += 1
            if fields[4] and fields[4].strip():
                metrics["website"] += 1
            if fields[5] and fields[5].strip():
                metrics["reviews_count"] += 1

        metrics["total_records"] += 1

    # Save cleaned file
    with open(usv_file, "w", encoding="utf-8") as f:
        for rec in cleaned_records:
            f.write(rec + "\n")

print(f"Cleaning complete. Metrics: {metrics}")
