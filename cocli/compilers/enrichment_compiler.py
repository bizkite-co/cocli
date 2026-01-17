from pathlib import Path
import pkgutil
import importlib
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..core.config import get_companies_dir
from .base import BaseCompiler

console = Console()

class EnrichmentCompiler:
    def __init__(self) -> None:
        self.compilers = self._discover_compilers()

    def _discover_compilers(self) -> list[BaseCompiler]:
        compilers_map = {}
        compiler_module_path = Path(__file__).parent
        for _, name, _ in pkgutil.iter_modules([str(compiler_module_path)]):
            if name != 'base' and name != 'enrichment_compiler':
                module = importlib.import_module(f'.{name}', package=__package__)
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type) and issubclass(attribute, BaseCompiler) and attribute is not BaseCompiler:
                        compilers_map[name] = attribute()
        
        # Define priority order (Google Maps first, Website last to fix generic names)
        order = ['google_maps_compiler', 'website_compiler']
        ordered_compilers = []
        for name in order:
            if name in compilers_map:
                ordered_compilers.append(compilers_map.pop(name))
        
        # Add any others discovered
        ordered_compilers.extend(compilers_map.values())
        return ordered_compilers

    def run(self, campaign_name: Optional[str] = None) -> None:
        companies_dir = get_companies_dir()
        if not companies_dir.exists():
            console.print("[bold red]Error:[/bold red] Companies directory not found.")
            return

        company_dirs = []
        if campaign_name:
            # Filter by tags in the _index.md or tags.lst
            console.print(f"[bold blue]Filtering for campaign: {campaign_name}...[/bold blue]")
            all_dirs = [d for d in companies_dir.iterdir() if d.is_dir()]
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console
            ) as progress:
                filter_task = progress.add_task("Identifying campaign members...", total=len(all_dirs))
                for d in all_dirs:
                    tags_file = d / "tags.lst"
                    if tags_file.exists():
                        tags = tags_file.read_text().splitlines()
                        if campaign_name in tags:
                            company_dirs.append(d)
                    progress.advance(filter_task)
        else:
            company_dirs = [d for d in companies_dir.iterdir() if d.is_dir()]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"Compiling enrichment ({len(company_dirs)} companies)...", total=len(company_dirs))
            for company_dir in company_dirs:
                for compiler in self.compilers:
                    compiler.compile(company_dir)
                progress.advance(task)
