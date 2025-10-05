import typer

from ..core.config import get_companies_dir
from ..models.company import Company
from ..core.utils import create_company_files

app = typer.Typer()

@app.command()
def add_email(
    company_name: str = typer.Argument(..., help="The name of the company to add the email to."),
    email: str = typer.Argument(..., help="The email address to add."),
):
    """
    Adds an email address to a company.
    """
    companies_dir = get_companies_dir()
    company_dir = companies_dir / company_name
    if not company_dir.exists():
        print(f"Company '{company_name}' not found.")
        raise typer.Exit(code=1)

    company = Company.from_directory(company_dir)
    if not company:
        print(f"Could not load company data for {company_name}")
        raise typer.Exit(code=1)

    company.email = email
    create_company_files(company, company_dir)
    print(f"Added email {email} to {company.name}")
