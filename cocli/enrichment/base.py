from abc import ABC, abstractmethod
from ..models.companies.company import Company

class EnrichmentScript(ABC):
    @abstractmethod
    def get_script_name(self) -> str:
        """Returns a unique name for the enrichment script."""
        pass

    @abstractmethod
    def run(self, company: Company) -> Company:
        """
        Runs the enrichment script on the given company and returns the updated Company object.
        """
        pass