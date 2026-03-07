import os
import re
import sys
from pathlib import Path
from typing import List, Set

from rich.console import Console
from rich.markdown import Markdown
from rich.rule import Rule

def extract_links(content: str) -> List[str]:
    """Extract markdown links to local files."""
    # Matches [text](link.md) or [text](path/to/link.md)
    return re.findall(r'\[(?:[^\]]+)\]\(([^)]+\.md)\)', content)

def show_task(task_file: str = "task.md") -> None:
    console = Console()
    
    if not os.path.exists(task_file):
        console.print(f"[bold red]Error:[/] {task_file} not found.")
        return

    with open(task_file, "r", encoding="utf-8") as f:
        task_content = f.read()

    console.print(Rule(f"Task: {task_file}", style="bold blue"))
    console.print(Markdown(task_content))
    
    links = extract_links(task_content)
    seen_files: Set[str] = {task_file}
    
    for link in links:
        # Resolve path relative to the task_file
        link_path = (Path(task_file).parent / link).resolve()
        link_str = str(link_path)
        
        if link_str in seen_files:
            continue
            
        if link_path.exists():
            console.print(Rule(f"Linked: {link}", style="bold green"))
            with open(link_path, "r", encoding="utf-8") as f:
                link_content = f.read()
            console.print(Markdown(link_content))
            seen_files.add(link_str)
            
            # Optionally recursively extract links? 
            # For now, let's keep it to one level deep to avoid infinite loops 
            # or massive output unless requested.
        else:
            console.print(f"[yellow]Warning:[/] Linked file {link} not found at {link_path}")

if __name__ == "__main__":
    task_file = sys.argv[1] if len(sys.argv) > 1 else "task.md"
    show_task(task_file)
