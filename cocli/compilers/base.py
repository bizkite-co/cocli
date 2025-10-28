from abc import ABC, abstractmethod
from pathlib import Path

class BaseCompiler(ABC):
    @abstractmethod
    def compile(self, company_dir: Path) -> None:
        pass
