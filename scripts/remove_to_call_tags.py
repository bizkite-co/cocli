from pathlib import Path

# Remove "to-call" tag from all companies
companies_dir = Path("/home/mstouffer/.local/share/cocli_data_dev/companies")

for tags_file in companies_dir.rglob("tags.lst"):
    try:
        tags = [t.strip() for t in tags_file.read_text().splitlines() if t.strip()]
        if "to-call" in tags:
            tags.remove("to-call")
            tags_file.write_text("\n".join(tags) + "\n")
            print(f"Removed tag from {tags_file}")
    except Exception as e:
        print(f"Error processing {tags_file}: {e}")

for index_file in companies_dir.rglob("_index.md"):
    try:
        content = index_file.read_text()
        if "to-call" in content:
            # Simple line-by-line replacement for YAML tags
            new_lines = []
            for line in content.splitlines():
                if line.strip() != "- to-call":
                    new_lines.append(line)
            index_file.write_text("\n".join(new_lines) + "\n")
            print(f"Removed tag from {index_file}")
    except Exception as e:
        print(f"Error processing {index_file}: {e}")
