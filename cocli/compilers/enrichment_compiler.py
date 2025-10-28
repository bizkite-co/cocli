from pathlib import Path
import pkgutil
import importlib

from rich.console import Console

from ..core.config import get_companies_dir
from .base import BaseCompiler

console = Console()

class EnrichmentCompiler:
    def __init__(self) -> None:
        self.compilers = self._discover_compilers()

    def _discover_compilers(self) -> list[BaseCompiler]:
        compilers = []
        compiler_module_path = Path(__file__).parent
        for _, name, _ in pkgutil.iter_modules([str(compiler_module_path)]):
            if name != 'base' and name != 'enrichment_compiler':
                module = importlib.import_module(f'.{name}', package=__package__)
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if isinstance(attribute, type) and issubclass(attribute, BaseCompiler) and attribute is not BaseCompiler:
                        compilers.append(attribute())
        return compilers

    def run(self) -> None:
        companies_dir = get_companies_dir()
        if not companies_dir.exists():
            console.print("[bold red]Error:[/bold red] Companies directory not found.")
            return

        for company_dir in companies_dir.iterdir():
            if company_dir.is_dir():
                for compiler in self.compilers:
                    compiler.compile(company_dir)
