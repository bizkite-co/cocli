import typer
import json
import shutil
from pathlib import Path
from rich.console import Console
from rich.progress import track
from cocli.core.config import get_campaign_dir
from cocli.core.text_utils import slugdotify

app = typer.Typer()
console = Console()

def get_new_path(base_dir: Path, email: str) -> Path:
    if "@" in email:
        user_part, domain_part = email.rsplit("@", 1)
    else:
        user_part, domain_part = email, "unknown"
        
    domain_slug = slugdotify(domain_part)
    email_slug = slugdotify(user_part)
    
    return base_dir / domain_slug / f"{email_slug}.json"

@app.command()
def main(campaign_name: str = typer.Argument(..., help="Campaign name to migrate")) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir or not campaign_dir.exists():
        console.print(f"[bold red]Campaign '{campaign_name}' not found.[/bold red]")
        raise typer.Exit(1)
        
    base_dir = campaign_dir / "indexes" / "emails"
    if not base_dir.exists():
        console.print("[yellow]No email index directory found.[/yellow]")
        return

    console.print(f"Migrating email index for {campaign_name} in {base_dir}...")
    
    # Collect all JSON files first to avoid modifying directory while iterating
    files_to_process = list(base_dir.rglob("*.json"))
    console.print(f"Found {len(files_to_process)} email files.")
    
    moved_count = 0
    merged_count = 0
    errors = 0
    
    for file_path in track(files_to_process, description="Migrating files..."):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            email = data.get("email")
            if not email:
                console.print(f"[red]Skipping {file_path}: No email field in JSON[/red]")
                continue
                
            new_path = get_new_path(base_dir, email)
            
            if file_path.resolve() == new_path.resolve():
                continue # Already in correct place
            
            new_path.parent.mkdir(parents=True, exist_ok=True)
            
            if new_path.exists():
                # Merge logic
                try:
                    with open(new_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    
                    # Merge tags
                    tags = set(data.get("tags", [])) | set(existing_data.get("tags", []))
                    existing_data["tags"] = sorted(list(tags))
                    
                    # Update timestamps (keep oldest first_seen, newest last_seen)
                    existing_data["first_seen"] = min(data.get("first_seen", ""), existing_data.get("first_seen", "")) or data.get("first_seen") or existing_data.get("first_seen")
                    existing_data["last_seen"] = max(data.get("last_seen", ""), existing_data.get("last_seen", ""))
                    
                    # Save merged
                    with open(new_path, 'w', encoding='utf-8') as f:
                        json.dump(existing_data, f, indent=2)
                        
                    # Remove old file
                    file_path.unlink()
                    merged_count += 1
                except Exception as e:
                    console.print(f"[red]Error merging {file_path} to {new_path}: {e}[/red]")
                    errors += 1
            else:
                # Move file
                shutil.move(str(file_path), str(new_path))
                moved_count += 1
                
        except Exception as e:
            console.print(f"[red]Error processing {file_path}: {e}[/red]")
            errors += 1

    # Cleanup empty directories
    console.print("Cleaning up empty directories...")
    for dir_path in base_dir.rglob("*"):
        if dir_path.is_dir() and not any(dir_path.iterdir()):
            try:
                dir_path.rmdir()
            except OSError:
                pass # Directory might not be empty anymore or other issue

    console.print("[bold green]Migration Complete![/bold green]")
    console.print(f"Moved: {moved_count}")
    console.print(f"Merged: {merged_count}")
    console.print(f"Errors: {errors}")

if __name__ == "__main__":
    app()
