#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Unit separator is \x1f
US = "\x1f"

def consolidate():
    campaign = "roadmap"
    recovery_dir = Path(f"/home/mstouffer/.local/share/cocli_data/campaigns/{campaign}/recovery")
    output_file = recovery_dir / "consolidated_pid_name_map.usv"
    
    pid_name_map = {}
    
    # Files to check specifically for PID/Name mappings
    files_to_check = [
        "master_pid_name_map.usv",
        "hollow_hydrated_master.usv",
        "hollow_hydrated.usv",
        "healed_prospects_index.usv"
    ]
    
    pid_pattern = re.compile(r'(ChIJ[a-zA-Z0-9_-]{10,})')

    for fname in files_to_check:
        f_path = recovery_dir / fname
        if not f_path.exists():
            continue
            
        print(f"Processing {fname}...")
        try:
            lines = f_path.read_text().splitlines()
            for line in lines:
                # 1. Try USV Split
                parts = line.split(US)
                if len(parts) >= 2:
                    pid = parts[0].strip()
                    name = parts[1].strip()
                    if pid.startswith("ChIJ") and len(name) >= 3:
                        pid_name_map[pid] = name
                        continue
                
                # 2. Try Regex + Remaining line
                match = pid_pattern.search(line)
                if match:
                    pid = match.group(1)
                    remaining = line.replace(pid, "").strip()
                    if len(remaining) >= 3:
                        pid_name_map[pid] = remaining

        except Exception as e:
            print(f"Error processing {fname}: {e}")

    if not pid_name_map:
        print("No PID/Name mappings found.")
        return

    print(f"Found {len(pid_name_map)} unique Place ID to Name mappings.")

    # Save to consolidated file
    from cocli.core.text_utils import slugify
    
    with open(output_file, 'w') as f:
        for pid, name in sorted(pid_name_map.items()):
            slug = slugify(name)
            f.write(f"{pid}{US}{name}{US}{slug}\n")

    print("-" * 40)
    print(f"Saved consolidated map to: {output_file}")
    
    # 3. VERIFY
    if output_file.exists() and output_file.stat().st_size > 0:
        print("Consolidation successful. You can now remove the source files:")
        for fname in files_to_check:
            if (recovery_dir / fname).exists():
                print(f"  rm data/campaigns/roadmap/recovery/{fname}")

if __name__ == "__main__":
    consolidate()