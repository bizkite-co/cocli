import re
from pathlib import Path
from typing import Any, List, Optional

import yaml # This import might not be needed here if models handle YAML loading

from .models import Company, Person # Import Company and Person models
from .config import get_companies_dir, get_people_dir # Import directory getters

def slugify(text: str) -> str:
    """Converts text to a filesystem-friendly slug."""
    text = text.lower()
    text = re.sub(r'[\s\W]+', '-', text)
    return text.strip('-')

def create_company_files(company_name: str, company_dir: Path) -> Path:
    """
    Creates the directory and files for a new company.
    """
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "contacts").mkdir(exist_ok=True)
    (company_dir / "meetings").mkdir(exist_ok=True)

    index_path = company_dir / "_index.md"
    if not index_path.exists():
        index_path.write_text(f"---\nname: {company_name}\n---\n\n# {company_name}\n")
    return company_dir

def create_person_files(person_name: str, person_dir: Path, company_name: str) -> Path:
    """
    Creates the markdown file for a new person.
    """
    person_dir.mkdir(parents=True, exist_ok=True)
    person_file = person_dir / f"{slugify(person_name)}.md"
    if not person_file.exists():
        content = f"# {person_name}\n\n- **Company:** {company_name}\n"
        person_file.write_text(content)
    return person_file

def _format_entity_for_fzf(entity_type: str, entity: Any) -> str:
    """
    Formats a company or person object into a string for fzf display.
    """
    if entity_type == "company":
        return f"COMPANY:{entity.name}"
    elif entity_type == "person":
        return f"PERSON:{entity.name}:{entity.company_name if entity.company_name else ''}"
    return ""

def _get_all_searchable_items() -> List[tuple[str, Any]]:
    """
    Gathers all companies and people for fuzzy searching.
    Returns a list of tuples: [("company", Company_obj), ("person", Person_obj)].
    """
    all_items = []
    companies_dir = get_companies_dir()
    people_dir = get_people_dir()

    if companies_dir.exists():
        for company_dir in companies_dir.iterdir():
            if company_dir.is_dir():
                company = Company.from_directory(company_dir)
                if company:
                    all_items.append(("company", company))

    if people_dir.exists():
        for person_file in people_dir.iterdir():
            if person_file.is_file() and person_file.suffix == ".md":
                person = Person.from_directory(person_file)
                if person:
                    all_items.append(("person", person))
    return all_items