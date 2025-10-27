import typer
from typing import Optional
import logging

from ..core.config import get_companies_dir, get_people_dir
from ..core.utils import slugify, create_company_files, create_person_files
from ..models.company import Company
from ..models.person import Person

logger = logging.getLogger(__name__)

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
    company_slug = slugify(company_name)
    company_dir = companies_dir / company_slug

    if not company_dir.exists():
        company = Company(name=company_name)
        create_company_files(company, company_dir)
        logger.info(f"Company '{company_name}' created at {company_dir}")
    else:
        logger.info(f"Company '{company_name}' already exists at {company_dir}")

    if person_name:
        people_dir = get_people_dir()
        person_slug = slugify(person_name)
        person_dir = people_dir / person_slug
        if not person_dir.exists():
            person = Person(name=person_name, company=company_name)
            create_person_files(person, person_dir)
            logger.info(f"Person '{person_name}' created at {person_dir}")
        else:
            logger.info(f"Person '{person_name}' already exists at {person_dir}")