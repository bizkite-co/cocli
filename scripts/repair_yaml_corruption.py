import os
import re
import yaml
from pathlib import Path
import typer
from rich.console import Console
from rich.progress import track
from typing import Any, Optional

# Add path to import cocli
import sys
sys.path.append(os.getcwd())

from cocli.core.text_utils import is_valid_email
from cocli.core.config import get_companies_dir

app = typer.Typer()
console = Console()

PYTHON_OBJ_PATTERN = re.compile(r'!!python/object/new:cocli\.models\.email_address\.EmailAddress\s*\n\s*-\s*([^\s\n]+)')

def fix_yaml_corruption(content: str) -> str:
    """Removes python object tags from YAML content."""
    # Replace !!python/object/new:cocli.models.email_address.EmailAddress\n  - email@addr.com
    # with just the email address.
    fixed = PYTHON_OBJ_PATTERN.sub(r'\1', content)
    # Also handle cases where it might be a single value instead of a list item
    fixed = re.sub(r'!!python/object/new:cocli\.models\.email_address\.EmailAddress\s*\n\s*([^\s\n]+)', r'\1', fixed)
    return fixed

def clean_emails(data: Any) -> Any:
    """Recursively clean emails in a data structure."""
    if isinstance(data, dict):
        new_dict: dict[str, Any] = {}
        for k, v in data.items():
            if k == "email" and isinstance(v, str):
                if is_valid_email(v):
                    new_dict[k] = v
                else:
                    new_dict[k] = None
            elif k == "all_emails" and isinstance(v, list):
                new_dict[k] = [e for e in v if isinstance(e, str) and is_valid_email(e)]
            else:
                new_dict[k] = clean_emails(v)
        return new_dict
    elif isinstance(data, list):
        return [clean_emails(item) for item in data]
    return data

def process_file(file_path: Path) -> bool:
    if not file_path.exists():
        return False
    
    try:
        content = file_path.read_text()
        if not content.startswith("---"):
            return False

        parts = content.split("---")
        if len(parts) < 3:
            return False

        yaml_str = parts[1]
        markdown_body = "---".join(parts[2:])

        # 1. Fix corruption
        fixed_yaml_str = fix_yaml_corruption(yaml_str)
        
        # 2. Parse and Clean
        try:
            data = yaml.safe_load(fixed_yaml_str)
        except yaml.YAMLError:
            # If still failing, try one more aggressive cleanup or just report
            console.print(f"[red]Failed to parse YAML after fix for {file_path}[/red]")
            return False

        if not data:
            return False

        cleaned_data = clean_emails(data)
        
        # 3. Save back
        new_yaml_str = yaml.safe_dump(cleaned_data, sort_keys=False)
        new_content = f"---\n{new_yaml_str}---\n{markdown_body}"
        
        if new_content != content:
            file_path.write_text(new_content)
            return True
    except Exception as e:
        console.print(f"[red]Error processing {file_path}: {e}[/red]")
    return False

@app.command()
def main(
    target_dir: Optional[Path] = typer.Argument(
        None, 
        help="Directory to scan. Defaults to the active campaign's companies directory."
    )
) -> None:
    """
    Scans a directory of Markdown files (recursively or flat structure) to repair
    common YAML corruption issues, specifically:
    1. Removes `!!python/object` tags left by pickle serialization errors.
    2. Scrubs invalid or junk emails (e.g., .png, .js, 'logo@2x') using `is_valid_email`.
    
    Operates on `_index.md` and `enrichments/website.md` files within the target structure.
    """
    if target_dir is None:
        target_dir = get_companies_dir()
        console.print(f"No directory specified. Using active campaign companies: [bold]{target_dir}[/bold]")
    
    if not target_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Directory {target_dir} does not exist.")
        raise typer.Exit(1)

    all_dirs = [d for d in target_dir.iterdir() if d.is_dir()]
    
    fixed_count = 0
    console.print(f"Processing [bold]{len(all_dirs)}[/bold] items in {target_dir}...")
    
    for company_dir in track(all_dirs, description="Fixing data..."):
        # Fix _index.md
        if process_file(company_dir / "_index.md"):
            fixed_count += 1
            
        # Fix enrichments/website.md
        if process_file(company_dir / "enrichments" / "website.md"):
            fixed_count += 1
            
    console.print(f"[green]Done![/green] Fixed/Cleaned [bold]{fixed_count}[/bold] files.")

if __name__ == "__main__":
    app()
