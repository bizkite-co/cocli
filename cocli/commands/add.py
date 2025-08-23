import typer
from typing import Optional

from ..core.config import get_companies_dir, get_people_dir
from ..core.utils import slugify, create_company_files, create_person_files

app = typer.Typer()

@app.command()
def add(
    company_name: str = typer.Option(
        ..., "--company", "-c", help="Name of the company"
    ),
    person_name: Optional[str] = typer.Option(
        None, "--person", "-p", help="Name of the person"
    ),
):
    """
    Add a new company or a person to an existing company.
    """
    companies_dir = get_companies_dir()
    company_dir = companies_dir / slugify(company_name)

    if not company_dir.exists():
        create_company_files(company_name, company_dir)
        print(f"Company '{company_name}' created at {company_dir}")
    else:
        print(f"Company '{company_name}' already exists at {company_dir}")

    if person_name:
        people_dir = get_people_dir()
        person_dir = people_dir / slugify(person_name)
        if not person_dir.exists():
            create_person_files(person_name, person_dir, company_name)
            print(f"Person '{person_name}' created at {person_dir}")
        else:
            print(f"Person '{person_name}' already exists at {person_dir}")