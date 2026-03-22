from pathlib import Path

results_dir = Path(
    "/home/mstouffer/.local/share/cocli_data_dev/campaigns/roadmap/queues/gm-list/completed/results"
)
report_file = results_dir / "corrupted-records.usv"

# Define separator constants based on analysis
UNIT_SEP = b"\x1f"
RECORD_SEP = b"\x1e"

with open(report_file, "w", encoding="utf-8") as rf:
    for usv_file in results_dir.rglob("*.usv"):
        if usv_file == report_file:
            continue

        with open(usv_file, "rb") as f:
            content = f.read()

        # Identify records.
        # Based on analysis, records are separated by \x1e and fields by \x1f
        records = content.split(RECORD_SEP)

        cleaned_records = []

        for rec in records:
            # Skip empty records
            if not rec.strip():
                continue

            # Fields are separated by \x1f
            fields = rec.split(UNIT_SEP)

            # Criteria: 9 fields AND first field starts with 'ChI'
            is_valid = False
            if len(fields) == 9:
                first_field = fields[0].decode("utf-8", errors="ignore").strip()
                if first_field.startswith("ChI"):
                    is_valid = True

            if is_valid:
                cleaned_records.append(rec)
            else:
                # Log corrupted record
                rf.write(f"--- source: {usv_file} ---\n")
                # Ensure we log the raw record including any potential embedded newlines
                rf.write(rec.decode("utf-8", errors="ignore") + "\n")

        # Overwrite file with validated records
        with open(usv_file, "wb") as f:
            for rec in cleaned_records:
                # Strip potential existing whitespace/newlines around the record
                f.write(rec.strip(b"\n") + RECORD_SEP + b"\n")
