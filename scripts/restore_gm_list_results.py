import re
from pathlib import Path

# The file containing all records (original + corrupted)
corrupted_file = Path(
    "/home/mstouffer/.local/share/cocli_data_dev/campaigns/roadmap/queues/gm-list/completed/results/corrupted-records.usv"
)

# Pattern to match the source markers
source_marker_pattern = re.compile(r"^--- source: (.*) ---$")

current_target_file = None
current_content = []


def write_and_reset():
    global current_target_file, current_content
    if current_target_file and current_content:
        # Ensure directory exists
        current_target_file.parent.mkdir(parents=True, exist_ok=True)
        # Write the content
        with open(current_target_file, "wb") as f:
            for rec in current_content:
                f.write(rec + b"\n")
        current_content = []


with open(corrupted_file, "rb") as f:
    for line in f:
        line = line.rstrip(b"\n")
        if not line:
            continue

        match = source_marker_pattern.match(line.decode("utf-8", errors="ignore"))
        if match:
            # We hit a new source file, commit the current buffer
            write_and_reset()
            current_target_file = Path(match.group(1))
        else:
            # Add line to current buffer
            current_content.append(line)

# Commit last buffer
write_and_reset()
print("Restoration complete.")
