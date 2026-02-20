import importlib
import pkgutil
from pathlib import Path
from typing import List, Optional, Dict
import logging
import yaml
from cocli.core.text_utils import slugify
from datetime import datetime

from .base import EnrichmentScript
from ..models.companies.company import Company

logger = logging.getLogger(__name__)

class EnrichmentManager:
    def __init__(self, company_data_dir: Path):
        self.company_data_dir = company_data_dir
        self.scripts: Dict[str, EnrichmentScript] = {}
        self._discover_scripts()

    def _discover_scripts(self) -> None:
        """Discovers all enrichment scripts in the 'enrichment' package."""
        enrichment_package = importlib.import_module("cocli.enrichment")
        for _, name, is_pkg in pkgutil.iter_modules(enrichment_package.__path__):
            if not is_pkg and name != "base" and name != "manager": # Exclude base and manager files
                try:
                    module = importlib.import_module(f"cocli.enrichment.{name}")
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, EnrichmentScript)
                            and attr is not EnrichmentScript
                        ):
                            script_instance = attr()
                            self.scripts[script_instance.get_script_name()] = script_instance
                            logger.info(f"Discovered enrichment script: {script_instance.get_script_name()}")
                except Exception as e:
                    logger.error(f"Error loading enrichment script {name}: {e}")

    def get_available_script_names(self) -> List[str]:
        """Returns a list of names of all discovered enrichment scripts."""
        return list(self.scripts.keys())

    def _get_company_path(self, company_name: str) -> Path:
        """Returns the path to a company's directory."""
        # Assuming company directories are directly under company_data_dir
        # and named after the company (e.g., company_data_dir/Acme Corp)
        return self.company_data_dir / slugify(company_name)

    def _load_company(self, company_name: str) -> Optional[Company]:
        """Loads a Company object from its _index.md file."""
        company_dir = self._get_company_path(company_name)
        return Company.from_directory(company_dir)

    def _save_company(self, company: Company) -> None:
        """Saves the updated Company object back to its _index.md file."""
        company_dir = self._get_company_path(company.name)
        index_path = company_dir / "_index.md"

        # Read existing content to preserve markdown
        content = index_path.read_text()
        frontmatter_str = ""
        markdown_content = ""

        if content.startswith("---") and "---" in content[3:]:
            parts = content.split("---", 2)
            frontmatter_str = parts[1]
            markdown_content = parts[2]
            existing_frontmatter = yaml.safe_load(frontmatter_str) or {}
        else:
            existing_frontmatter = {}
            markdown_content = content

        # Convert Company object to dictionary, excluding fields that are not part of frontmatter
        # or are managed separately (like 'tags' which is handled by from_directory/save_company)
        company_dict = company.model_dump(exclude_unset=True, exclude={"tags"})

        # Merge new data into existing frontmatter
        updated_frontmatter = {**existing_frontmatter, **company_dict}

        # Reconstruct the _index.md file
        new_content = "---\n"
        new_content += yaml.dump(updated_frontmatter, sort_keys=False, default_flow_style=False)
        new_content += "---\n"
        new_content += markdown_content

        index_path.write_text(new_content)
        logger.info(f"Saved updated company data for {company.name} to {index_path}")

    def _update_run_tracking(self, company_name: str, script_name: str) -> None:
        """Updates the run tracking file for a given company and script."""
        company_dir = self._get_company_path(company_name)
        run_tracking_dir = company_dir / ".enrichment-job-runs"
        run_tracking_dir.mkdir(parents=True, exist_ok=True)

        run_file_path = run_tracking_dir / script_name
        # Touch the file to update its modification timestamp
        run_file_path.touch()
        logger.info(f"Updated run tracking for {company_name} with script {script_name}")

    def run_enrichment_script(self, company_name: str, script_name: str) -> bool:
        """
        Runs a specific enrichment script on a given company.
        Returns True if successful, False otherwise.
        """
        if script_name not in self.scripts:
            logger.error(f"Enrichment script '{script_name}' not found.")
            return False

        company = self._load_company(company_name)
        if not company:
            logger.error(f"Company '{company_name}' not found.")
            return False

        script = self.scripts[script_name]
        try:
            updated_company = script.run(company)
            self._save_company(updated_company)
            self._update_run_tracking(company_name, script_name)
            logger.info(f"Successfully ran enrichment script '{script_name}' on '{company_name}'.")
            return True
        except Exception as e:
            logger.error(f"Failed to run enrichment script '{script_name}' on '{company_name}': {e}")
            return False

    def get_last_run_time(self, company_name: str, script_name: str) -> Optional[datetime]:
        """
        Returns the last run time of a script for a company, or None if never run.
        """
        company_dir = self._get_company_path(company_name)
        run_file_path = company_dir / ".enrichment-job-runs" / script_name
        if run_file_path.exists():
            return datetime.fromtimestamp(run_file_path.stat().st_mtime)
        return None

    def get_unenriched_companies(self, script_name: str) -> List[str]:
        """
        Returns a list of company names that have not been enriched by the given script.
        """
        unenriched_companies = []
        for company_dir in self.company_data_dir.iterdir():
            if company_dir.is_dir() and not company_dir.name.startswith('.'):
                company_name = company_dir.name
                if not self.get_last_run_time(company_name, script_name):
                    unenriched_companies.append(company_name)
        return unenriched_companies
