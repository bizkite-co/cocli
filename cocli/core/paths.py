from pathlib import Path
from pydantic import BaseModel, field_validator, ConfigDict
import logging
from typing import Any, Union

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
    def resolve_and_validate(cls, v: Any) -> Path:
        if isinstance(v, ValidatedPath):
            return v.path
            
        p = Path(v).expanduser()
        
        # Check for broken symlinks before resolving
        if p.is_symlink() and not p.exists():
            raise FileNotFoundError(f"Path Authority Error: Broken symlink detected at '{p}'")
            
        resolved = p.resolve()
        
        # 1. Root Safety Check
        if str(resolved) in ["/", ".", ""]:
            raise ValueError(f"Path Authority Error: Path '{v}' resolved to system root. This is forbidden.")

        # 2. Parent Existence Check
        # We allow the final component to not exist (e.g. creating a new file), 
        # but the PARENT of that component must exist.
        if not resolved.parent.exists():
            raise FileNotFoundError(f"Path Authority Error: Base directory '{resolved.parent}' does not exist for {v}")
            
        return resolved

    def __truediv__(self, other: Union[str, Path]) -> "ValidatedPath":
        """Allow using / operator, returning a new ValidatedPath to maintain protection."""
        new_path = self.path / other
        return ValidatedPath(path=new_path, description=f"{self.description} -> {other}")

    def exists(self) -> bool:
        return self.path.exists()

    def is_dir(self) -> bool:
        return self.path.is_dir()

    def is_file(self) -> bool:
        return self.path.is_file()

    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        self.path.mkdir(parents=parents, exist_ok=exist_ok)

    def iterdir(self) -> Any:
        return self.path.iterdir()

    def glob(self, pattern: str) -> Any:
        return self.path.glob(pattern)

    @property
    def parent(self) -> "ValidatedPath":
        return ValidatedPath(path=self.path.parent, description=f"Parent of {self.description}")

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem

    def resolve(self) -> Path:
        """Returns the raw resolved Path object."""
        return self.path

    def __fspath__(self) -> str:
        """Allow passing directly to open() and other os functions."""
        return str(self.path)

    def __str__(self) -> str:
        return str(self.path)

    def __repr__(self) -> str:
        return f"ValidatedPath(path={self.path}, desc={self.description})"

def get_validated_dir(path: Path, description: str) -> ValidatedPath:
    """Helper to create a validated path with immediate feedback."""
    try:
        return ValidatedPath(path=path, description=description)
    except FileNotFoundError as e:
        logger.critical(f"FATAL CONFIG ERROR: {e}")
        # In a CLI context, we want to crash hard
        print(f"\n[bold red]FATAL ERROR:[/bold red] {e}")
        print("[dim]Please check your COCLI_DATA_HOME or symlinks.[/dim]\n")
        exit(1)
