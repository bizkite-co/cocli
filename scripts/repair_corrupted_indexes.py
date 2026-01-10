from pathlib import Path
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_companies_dir

console = Console()

def repair_single_file(file_path: Path) -> bool:
    if not file_path.exists():
        return False

    content = file_path.read_text()
    if "!!python/object/new:cocli.models.email_address.EmailAddress" not in content:
        return False

    lines = content.splitlines()
    new_lines = []
    skip_next = False
    repaired = False
    
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
            
        if "email: !!python/object/new:cocli.models.email_address.EmailAddress" in line:
            if i + 1 < len(lines) and lines[i+1].strip().startswith("- "):
                actual_email = lines[i+1].strip().replace("- ", "").strip()
                new_lines.append(f"email: {actual_email}")
                skip_next = True
                repaired = True
            else:
                new_lines.append(line.replace("!!python/object/new:cocli.models.email_address.EmailAddress", "").strip())
                repaired = True
        elif "!!python/object/new:cocli.models.email_address.EmailAddress" in line:
            cleaned = line.replace("!!python/object/new:cocli.models.email_address.EmailAddress", "")
            cleaned = cleaned.replace("args: [", "").replace("]", "").replace("'", "").replace('"', "")
            new_lines.append(cleaned)
            repaired = True
        else:
            new_lines.append(line)
            
    if repaired:
        file_path.write_text("\n".join(new_lines) + "\n")
        return True
    return False

def repair_all(batch_size: int = 100) -> None:
    companies_dir = get_companies_dir()
    company_paths = [p for p in companies_dir.iterdir() if p.is_dir()]
    
    repaired_total = 0
    
    # We find ALL corrupted files first
    corrupted_paths = []
    for company_path in track(company_paths, description="Scanning for corruption..."):
        index_path = company_path / "_index.md"
        if index_path.exists() and "!!python/object/new:cocli.models.email_address.EmailAddress" in index_path.read_text():
            corrupted_paths.append(index_path)
            
    console.print(f"Found {len(corrupted_paths)} corrupted files.")
    
    # Repair in batches
    for i in range(0, len(corrupted_paths), batch_size):
        batch = corrupted_paths[i:i + batch_size]
        console.print(f"Processing batch {i//batch_size + 1} ({len(batch)} files)...")
        for path in batch:
            if repair_single_file(path):
                repaired_total += 1
                
    console.print(f"[bold green]Repaired {repaired_total} total files.[/bold green]")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        repair_single_file(Path(sys.argv[1]))
    else:
        repair_all()
