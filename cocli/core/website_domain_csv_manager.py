from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

from ..models.website_domain_csv import WebsiteDomainCsv
from .config import get_cocli_base_dir

CURRENT_SCRAPER_VERSION = 6

class WebsiteDomainCsvManager:
    def __init__(self, indexes_dir: Optional[Path] = None):
        if not indexes_dir:
            indexes_dir = get_cocli_base_dir() / "indexes"
        
        self.root_dir = indexes_dir
        self.atomic_dir = indexes_dir / "domains"
        self.atomic_dir.mkdir(parents=True, exist_ok=True)
        
        # Files for schema and versioning
        self.version_file = self.atomic_dir / "VERSION"
        self.header_file = self.atomic_dir / "_header.usv"
        
        # Materialized View (Cache)
        self.csv_file = indexes_dir / "domains_master.csv"
        
        self.data: Dict[str, WebsiteDomainCsv] = {}
        self._initialize_metadata()
        self._load_data()

    def _initialize_metadata(self) -> None:
        """Ensures VERSION and _header.usv exist."""
        if not self.version_file.exists():
            self.version_file.write_text("1")
        if not self.header_file.exists():
            self.header_file.write_text(WebsiteDomainCsv.get_header())

    def _load_data(self) -> None:
        """
        Loads data from individual USV files.
        For performance, we scan the atomic_dir.
        """
        # If we have thousands of files, we might want to lazy-load or use the cache.
        # For now, let's prioritize the Atomic Source of Truth.
        for usv_path in self.atomic_dir.glob("*.usv"):
            if usv_path.name.startswith("_"):
                continue
            try:
                content = usv_path.read_text(encoding="utf-8")
                item = WebsiteDomainCsv.from_usv(content)
                self.data[str(item.domain)] = item
            except Exception:
                continue

    def get_by_domain(self, domain: str) -> Optional[WebsiteDomainCsv]:
        # Check in-memory first
        if domain in self.data:
            return self.data[domain]
        
        # Check for atomic file directly (allows for out-of-process updates)
        from .text_utils import slugdotify
        usv_path = self.atomic_dir / f"{slugdotify(domain)}.usv"
        if usv_path.exists():
            try:
                content = usv_path.read_text(encoding="utf-8")
                item = WebsiteDomainCsv.from_usv(content)
                self.data[domain] = item
                return item
            except Exception:
                return None
        return None

    def add_or_update(self, item: WebsiteDomainCsv) -> None:
        item.updated_at = datetime.utcnow()
        self.data[str(item.domain)] = item
        
        # Atomic Write (Source of Truth)
        from .text_utils import slugdotify
        usv_path = self.atomic_dir / f"{slugdotify(str(item.domain))}.usv"
        usv_path.write_text(item.to_usv(), encoding="utf-8")
        
        # Background: You might want to delay cache rebuild if doing bulk updates
        # self.rebuild_cache()

    def flag_as_email_provider(self, domain: str) -> None:
        item = self.get_by_domain(domain)
        if not item:
            item = WebsiteDomainCsv(domain=domain)
        item.is_email_provider = True
        self.add_or_update(item)

    def rebuild_cache(self) -> None:
        """Rebuilds the domains_master.csv Materialized View from atomic files using DuckDB."""
        import duckdb
        import os
        import logging
        
        local_logger = logging.getLogger(__name__)
        
        usv_glob = str(self.atomic_dir / "*.usv")
        
        try:
            # Check if any .usv files exist beyond the special ones
            if not any(f.suffix == ".usv" and not f.name.startswith("_") for f in self.atomic_dir.iterdir()):
                local_logger.info("No domain index files found to cache.")
                return

            # Note: We read USV (\x1f) and write standard CSV (,) for the master cache file
            # to remain compatible with standard tools (Excel, etc).
            # We explicitly disable auto_detect and set quote/escape to empty strings
            sql = f"""
                COPY (
                    SELECT * FROM read_csv('{usv_glob}', 
                        delim='{chr(31)}', 
                        header=False, 
                        quote='', 
                        escape='',
                        auto_detect=False,
                        columns={ {k: 'VARCHAR' for k in WebsiteDomainCsv.model_fields.keys()} }
                    )
                    ORDER BY domain ASC
                ) TO '{self.csv_file}' (HEADER, DELIMITER ',');
            """
            duckdb.query(sql)
            local_logger.debug(f"Cache rebuilt successfully via DuckDB: {self.csv_file}")
        except Exception as e:
            local_logger.error(f"Failed to rebuild cache via DuckDB: {e}")
            # Fallback to shell-based join if DuckDB fails for some reason
            os.system(f"cat {self.atomic_dir}/_header.usv {self.atomic_dir}/*.usv | tr '\\x1f' ',' > {self.csv_file}")

    def save(self) -> None:
        """Legacy compatibility: In Atomic Index, we save per-item, but we can rebuild cache."""
        self.rebuild_cache()
