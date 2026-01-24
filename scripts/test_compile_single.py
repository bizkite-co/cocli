from pathlib import Path
from cocli.compilers.website_compiler import WebsiteCompiler
from cocli.models.company import Company
from rich.console import Console

console = Console()

def test_becker() -> None:
    becker_path = Path("/home/mstouffer/.local/share/data/companies/beckerarena-com")
    console.print(f"Testing compilation for: {becker_path}")
    
    compiler = WebsiteCompiler()
    
    # Run compilation
    try:
        compiler.compile(becker_path)
        console.print("[green]Compiler call finished.[/green]")
        
        # Now reload and check
        company = Company.from_directory(becker_path)
        if company:
            console.print(f"Post-compile services count: {len(company.services)}")
            console.print(f"Post-compile categories count: {len(company.categories)}")
            if company.categories:
                console.print(f"Categories: {company.categories}")
        else:
            console.print("[red]Failed to reload company.[/red]")
            
    except Exception as e:
        console.print(f"[red]Compilation failed with error: {e}[/red]")

if __name__ == "__main__":
    test_becker()
