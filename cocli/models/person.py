from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Person(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None # Added to link person to company

    @classmethod
    def from_directory(cls, person_file: Path) -> Optional["Person"]:
        if not person_file.exists() or not person_file.suffix == ".md":
            return None
