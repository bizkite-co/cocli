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

            if len(rows[0]) < 9 or len(rows[0]) > 10:
                console.print(
                    f"[yellow]Skipping {usv_file.relative_to(results_dir)}: {len(rows[0])} fields[/yellow]"
                )
                skipped += 1
                continue

            num_fields = len(rows[0])
            if num_fields < 9 or num_fields > 10:
                console.print(
                    f"[yellow]Skipping {usv_file.relative_to(results_dir)}: {num_fields} fields[/yellow]"
                )
                skipped += 1
                continue

            for row in rows:
                # Pad to 10 fields if necessary
                # Re-check row length inside the row loop
                if len(row) == 9:
                    row.insert(3, None)  # Insert category at index 3
                elif len(row) > 10:
                    row = row[:10]
                elif len(row) < 9:
                    # Skip rows that are too short even if the first row was 9
                    continue

                writer.writerow(row)
                count += 1


print(f"Compiled {count} records to {compiled_path}. Skipped {skipped} files.")
