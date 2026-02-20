from pathlib import Path
from cocli.models.companies.company import Company
from rich.console import Console

console = Console()

files = [
    "/home/mstouffer/.local/share/data/companies/myflooringspecialist-com/",
    "/home/mstouffer/.local/share/data/companies/scoutfloors-com/",
    "/home/mstouffer/.local/share/data/companies/comflors-com/"
]

for f in files:
    path = Path(f)
    console.print(f"Testing load for: [bold]{path.name}[/bold]")
    try:
        company = Company.from_directory(path)
        if company:
            console.print(f"  [green]SUCCESS[/green]: Loaded {company.name}")
            console.print(f"  Email: {company.email}")
        else:
            console.print("  [red]FAILED[/red]: from_directory returned None")
    except Exception as e:
        console.print(f"  [red]ERROR[/red]: {e}")
