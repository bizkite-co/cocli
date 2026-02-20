import logging
import yaml
from typing import Optional
import typer
from cocli.models.companies.company import Company
from cocli.models.phone import PhoneNumber
from cocli.core.config import get_companies_dir, get_people_dir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = typer.Typer()

@app.command()
def migrate(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show changes without applying them."),
    limit: Optional[int] = typer.Option(None, "--limit", help="Limit the number of records to process."),
) -> None:
    """
    Migrates all phone numbers in the data directory to the new digit-only format.
    """
    # 1. Migrate Companies
    logger.info("Starting Company phone migration...")
    count = 0
    companies_dir = get_companies_dir()
    for company_dir in sorted(companies_dir.iterdir()):
        if not company_dir.is_dir():
            continue
            
        index_path = company_dir / "_index.md"
        if not index_path.exists():
            continue
            
        content = index_path.read_text()
        if not (content.startswith("---") and "---" in content[3:]):
            continue
            
        frontmatter_str = content.split("---", 2)[1]
        try:
            data = yaml.safe_load(frontmatter_str) or {}
        except Exception:
            continue

        changed = False
        phone_fields = ["phone_1", "phone_number", "phone_from_website"]
        for field in phone_fields:
            val = data.get(field)
            if val and isinstance(val, str):
                try:
                    phone_obj = PhoneNumber.model_validate(val)
                    if str(phone_obj) != val:
                        logger.info(f"Company {company_dir.name}: {field} '{val}' -> '{phone_obj}'")
                        changed = True
                except Exception:
                    pass

        if changed:
            if not dry_run:
                # Load via model and save to ensure all fields are cleaned
                company = Company.get(company_dir.name)
                if company:
                    company.save()
            count += 1
            
        if limit and count >= limit:
            break

    logger.info(f"Migrated {count} companies.")

    # 2. Migrate People
    logger.info("Starting Person phone migration...")
    count = 0
    people_dir = get_people_dir()
    for person_dir in sorted(people_dir.iterdir()):
        if not person_dir.is_dir():
            continue
        
        for person_file in person_dir.glob("*.md"):
            content = person_file.read_text()
            if not (content.startswith("---") and "---" in content[3:]):
                continue
                
            frontmatter_str = content.split("---", 2)[1]
            try:
                data = yaml.safe_load(frontmatter_str) or {}
            except Exception:
                continue
                
            val = data.get("phone")
            if val and isinstance(val, str):
                try:
                    phone_obj = PhoneNumber.model_validate(val)
                    if str(phone_obj) != val:
                        logger.info(f"Person {person_dir.name}: phone '{val}' -> '{phone_obj}'")
                        if not dry_run:
                            # Use Person.from_file or similar
                            from cocli.models.people.person import Person
                            person = Person.from_file(person_file, person_dir.name)
                            if person:
                                from cocli.core.utils import create_person_files
                                create_person_files(person, person_dir)
                        count += 1
                except Exception:
                    pass
        
        if limit and count >= limit:
            break

    logger.info(f"Migrated {count} people.")

if __name__ == "__main__":
    app()
