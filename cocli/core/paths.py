import os
from pathlib import Path
from pydantic import BaseModel, field_validator, ConfigDict
import logging

logger = logging.getLogger(__name__)

class ValidatedPath(BaseModel):
    """
    A robust path object that ensures the directory exists and is absolute.
    Prevents silent failures where missing directories return False for exists().
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    path: Path
    description: str = "Generic Data Directory"

    @field_validator("path", mode="before")
    @classmethod
    def resolve_and_validate(cls, v: any) -> Path:
        p = Path(v).expanduser().resolve()
        
        # 1. Root Safety Check
        if str(p) in ["/", ".", ""]:
            raise ValueError(f"Path Authority Error: Path '{v}' resolved to system root. This is forbidden.")

        # 2. Parent Existence Check
        if not p.parent.exists():
            raise FileNotFoundError(f"Path Authority Error: Base directory '{p.parent}' does not exist for {v}")
            
        return p

    def __truediv__(self, other: str) -> Path:
        """Allow using / operator like a normal Path object."""
        return self.path / other

    def exists(self) -> bool:
        return self.path.exists()

    def __str__(self) -> str:
        return str(self.path)

def get_validated_dir(path: Path, description: str) -> ValidatedPath:
    """Helper to create a validated path with immediate feedback."""
    try:
        return ValidatedPath(path=path, description=description)
    except FileNotFoundError as e:
        logger.critical(f"FATAL CONFIG ERROR: {e}")
        # In a CLI context, we want to crash hard
        print(f"\n[bold red]FATAL ERROR:[/bold red] {e}")
        print(f"[dim]Please check your COCLI_DATA_HOME or symlinks.[/dim]\n")
        exit(1)
