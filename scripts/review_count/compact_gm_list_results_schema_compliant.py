from pathlib import Path
from cocli.utils.usv_utils import USVReader, USVWriter
from rich.console import Console
import json

console = Console()

# Settings

results_dir = Path(
    "/home/mstouffer/.local/share/cocli_data_dev/campaigns/roadmap/queues/gm-list/completed/results"
)
compiled_path = results_dir / "compiled.usv"
dp_path = results_dir / "datapackage.json"

# Load schema
with open(dp_path) as f:
    schema = json.load(f)
fields = schema["resources"][0]["schema"]["fields"]
field_names = [f["name"] for f in fields]
print(f"Schema fields ({len(field_names)}): {field_names}")

# Collect all files
usv_files = [
    f
    for f in results_dir.rglob("*.usv")
    if f.name
    not in [
        "compiled.usv",
        "compacted.usv",
        "results.usv",
        "corrupted-records.usv",
        "results.invalid.usv",
    ]
]

# Stack and append all
count = 0
skipped = 0
with open(compiled_path, "w", encoding="utf-8") as f_out:
    writer = USVWriter(f_out)
    for usv_file in usv_files:
        with open(usv_file, "r", encoding="utf-8") as f_in:
            reader = USVReader(f_in)
            rows = list(reader)
            if not rows:
                console.print(
                    f"[yellow]Skipping {usv_file.relative_to(results_dir)}: Empty file[/yellow]"
                )
                skipped += 1
                continue

            num_fields = len(rows[0])

            # The files have 9 fields. If we add category, it becomes 10.
            # We want to support 9 or 10.
            if num_fields < 8 or num_fields > 10:
                skipped += 1
                continue

            for row in rows:
                # Pad to 10 fields if necessary
                if len(row) == 8:
                    row.insert(3, None)  # Category
                    row.insert(5, None)  # Domain
                elif len(row) == 9:
                    row.insert(3, None)  # Category
                elif len(row) > 10:
                    row = row[:10]

                writer.writerow(row)
                count += 1


print(f"Compiled {count} records to {compiled_path}. Skipped {skipped} files.")
