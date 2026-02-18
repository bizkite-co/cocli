import os
from pathlib import Path
import platform
import tomli
import tomli_w
from typing import Optional, Any, Dict
import logging
from pydantic import BaseModel, Field

from pydantic_settings import BaseSettings
from rich.console import Console
from .paths import paths, get_validated_dir

console = Console()

logger = logging.getLogger(__name__)

def get_cocli_app_data_dir() -> Path:
    """
    Determines the root data directory for cocli application-specific files (logs, caches).
    This is distinct from the user's business data directory.
    """
    if "XDG_DATA_HOME" in os.environ:
        cocli_app_data_dir = Path(os.environ["XDG_DATA_HOME"]).expanduser() / "cocli"
    else:
        if platform.system() == "Windows":
            cocli_app_data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "cocli"
        elif platform.system() == "Darwin": # macOS
            cocli_app_data_dir = Path.home() / "Library" / "Application Support" / "cocli"
        else: # Linux and other Unix-like
            cocli_app_data_dir = Path.home() / ".local" / "share" / "cocli"

    v_path = get_validated_dir(cocli_app_data_dir, "App Data Root (Logs/Cache)")
    v_path.path.mkdir(parents=True, exist_ok=True)
    return v_path.path

def get_cocli_base_dir() -> Path:
    """
    Determines the root data directory for cocli user business data.
    Delegates to the central paths authority.
    """
    p = paths.root
    v_path = get_validated_dir(p, "User Business Data Root")
    v_path.path.mkdir(parents=True, exist_ok=True)
    return v_path.path

def get_config_dir() -> Path:
    """
    Determines the configuration directory for cocli.
    """
    if "COCLI_CONFIG_HOME" in os.environ:
        return Path(os.environ["COCLI_CONFIG_HOME"]).expanduser()
    elif "COCLI_DATA_HOME" in os.environ: # Prioritize COCLI_DATA_HOME for config
        return Path(os.environ["COCLI_DATA_HOME"]).expanduser() / "config"
    elif "XDG_CONFIG_HOME" in os.environ:
        return Path(os.environ["XDG_CONFIG_HOME"]).expanduser() / "cocli"
    else:
        # Default location based on OS
        if platform.system() == "Windows":
            return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "cocli"
        elif platform.system() == "Darwin": # macOS
            return Path.home() / "Library" / "Preferences" / "cocli"
        else: # Linux and other Unix-like
            return Path.home() / ".config" / "cocli"

def get_companies_dir() -> Path:
    """DEPRECATED: Use paths.companies.ensure()"""
    return paths.companies.ensure()

def get_people_dir() -> Path:
    """DEPRECATED: Use paths.people.ensure()"""
    return paths.people.ensure()

def get_wal_dir() -> Path:
    """DEPRECATED: Use paths.wal.ensure()"""
    return paths.wal.ensure()

def get_shared_scraped_data_dir() -> Path:
    """
    Returns the shared scraped data directory (e.g., shopify_csv).
    Previously used for all scraped data.
    DEPRECATED: Use paths.root / 'scraped_data'
    """
    p = paths.root / "scraped_data"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_scraped_data_dir() -> Path:
    """
    Legacy alias for get_shared_scraped_data_dir.
    TODO: Deprecate and remove.
    """
    return get_shared_scraped_data_dir()

def get_indexes_dir() -> Path:
    """
    Returns the base directory for shared indexes.
    Path: data/indexes/
    DEPRECATED: Use paths.indexes
    """
    p = paths.indexes
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_temp_dir() -> Path:
    """
    Returns the temporary directory for cocli.
    Path: data/temp/
    """
    p = paths.root / "temp"
    v_dir = get_validated_dir(p, "Temp Directory")
    v_dir.path.mkdir(parents=True, exist_ok=True)
    return v_dir.path

def get_scraped_areas_index_dir() -> Path:
    """
    Returns the directory for phrase-specific scraped area indexes.
    Path: data/indexes/scraped_areas/
    """
    p = paths.indexes / "scraped_areas"
    v_dir = get_validated_dir(p, "Scraped Areas Index")
    v_dir.path.mkdir(parents=True, exist_ok=True)
    return v_dir.path

def get_scraped_tiles_index_dir() -> Path:
    """
    Returns the directory for the Phase 10 witness file index.
    Path: data/indexes/scraped-tiles/
    """
    p = paths.indexes / "scraped-tiles"
    v_dir = get_validated_dir(p, "Scraped Tiles (Witness) Index")
    v_dir.path.mkdir(parents=True, exist_ok=True)
    return v_dir.path

def get_campaign_scraped_data_dir(campaign_name: str) -> Path:
    """
    Returns the scraped data directory for a specific campaign.
    Path: data/campaigns/<campaign>/scraped_data/
    """
    p = paths.campaign(campaign_name).path / "scraped_data"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_campaign_exports_dir(campaign_name: str) -> Path:
    """
    Returns the exports directory for a specific campaign.
    Path: data/campaigns/<campaign>/exports/
    """
    p = paths.campaign(campaign_name).exports
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_campaigns_dir() -> Path:
    p = paths.campaigns
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_campaign_dir(campaign_name: str) -> Optional[Path]:
    """
    Returns the directory for a specific campaign.
    """
    campaign_dir = paths.campaign(campaign_name).path
    if campaign_dir.exists() and campaign_dir.is_dir():
        return campaign_dir
    return None

def get_all_campaign_dirs() -> list[Path]:
    """
    Returns a list of all campaign directories, recursively finding those
    with a config.toml file.
    """
    campaigns_root = paths.campaigns
    if not (campaigns_root.exists() and campaigns_root.is_dir()):
        return []

    unique_dirs = []
    seen_slugs = set()

    # Find all config.toml files and use their parent directories
    for config_file in sorted(campaigns_root.glob("**/config.toml")):
        campaign_dir = config_file.parent
        # Calculate the relative path from the campaigns root to use as the name
        try:
            rel_path = campaign_dir.relative_to(campaigns_root)
            campaign_name = str(rel_path)
            # Use the full relative path as the unique key
            if campaign_name not in seen_slugs:
                seen_slugs.add(campaign_name)
                unique_dirs.append(campaign_dir)
        except ValueError:
            continue

    return unique_dirs


def _read_data_home_from_config_file() -> Optional[Path]:
    """
    Safely reads the data_home path from the config file without triggering recursion.
    """
    config_path = get_config_path()
    if config_path.exists():
        try:
            with config_path.open("rb") as f:
                data = tomli.load(f)
            if "data_home" in data:
                return Path(data["data_home"])
        except tomli.TOMLDecodeError as e:
            logger.error(f"Error decoding TOML config file {config_path}: {e}")
        except Exception as e:
            logger.error(f"Error reading config file {config_path}: {e}")
    return None


class Tui(BaseModel):
    master_width: int = 30

class Config(BaseModel):
    data_home: Path = Field(default_factory=get_cocli_base_dir)
    tui: Tui = Tui()
    campaign: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    queue_type: Optional[str] = None

def get_config() -> Config:
    config_path = get_config_path()
    return load_config(config_path)

class ScraperSettings(BaseSettings):
    google_maps_delay_seconds: float = 1.0
    google_maps_max_retries: int = 3
    google_maps_retry_delay_seconds: float = 5.0
    google_maps_cache_ttl_days: int = 30
    browser_headless: bool = True
    browser_width: int = 2000
    browser_height: int = 2000
    browser_devtools: bool = False
    proxy_url: Optional[str] = None

def load_scraper_settings() -> ScraperSettings:
    """
    Loads scraper settings from cocli_config.toml.
    """
    config_dir = get_config_dir()
    config_file = config_dir / "cocli_config.toml"

    if not config_file.exists():
        logger.warning(f"Config file not found at {config_file}. Using default scraper settings.")
        return ScraperSettings()

    try:
        with config_file.open('rb') as f: # Open in binary mode for tomli
            config_data = tomli.load(f)
            if config_data and "scraper" in config_data:
                return ScraperSettings(**config_data["scraper"])
            else:
                logger.info(f"'scraper' section not found in {config_file}. Using default scraper settings.")
                return ScraperSettings()
    except tomli.TOMLDecodeError as e:
        logger.error(f"Error decoding TOML config file {config_file}: {e}. Using default scraper settings.")
        return ScraperSettings()
    except Exception as e:
        logger.error(f"Error loading config file {config_file}: {e}. Using default scraper settings.")
        return ScraperSettings()


def load_campaign_config(campaign_name: str) -> Dict[str, Any]:
    """
    Loads the campaign-specific configuration, inheriting from parent namespace config files.
    Walks from the campaigns root down to the specific campaign directory.
    """
    from .utils import deep_merge
    campaigns_root = paths.campaigns
    campaign_dir = paths.campaign(campaign_name)
    
    # 1. Identify all possible config files in the hierarchy
    # e.g. for 'test/sub/my-campaign':
    # - data/campaigns/config.toml (if exists, though usually template)
    # - data/campaigns/test/config.toml
    # - data/campaigns/test/sub/config.toml
    # - data/campaigns/test/sub/my-campaign/config.toml
    
    config_hierarchy: list[Path] = []
    
    # Walk up from campaign_dir to campaigns_root
    current = campaign_dir.path
    while True:
        config_file = current / "config.toml"
        if config_file.exists():
            config_hierarchy.insert(0, config_file) # Parents first
        
        if current == campaigns_root or current == current.parent:
            break
        current = current.parent

    # 2. Merge them in order (top-down)
    merged_config: Dict[str, Any] = {}
    for config_file in config_hierarchy:
        try:
            with config_file.open("rb") as f:
                overrides = tomli.load(f)
                merged_config = deep_merge(merged_config, overrides)
        except Exception as e:
            logger.error(f"Error loading config layer {config_file}: {e}")

    return merged_config

def get_config_path() -> Path:
    config_dir = get_config_dir()
    return config_dir / "cocli_config.toml"

def load_config(config_path: Path) -> Config:
    if not config_path.exists():
        return Config()
    with config_path.open("rb") as f:
        data = tomli.load(f)
    return Config(**data)

def save_config(config_data: Dict[str, Any]) -> None:
    config_file = get_config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert Path objects to strings for TOML serialization
    # We do a shallow conversion as config_data is mostly flat or simple dicts
    # If deeper nesting with Path objects occurs, a recursive function would be needed.
    serializable_config: Dict[str, Any] = {}
    for k, v in config_data.items():
        if v is None:
            continue # Skip None values as TOML doesn't support them
        
        if isinstance(v, Path):
            serializable_config[k] = str(v)
        elif isinstance(v, dict):
             # Handle one level deep for nested dicts like 'campaign' or 'tui'
             serializable_config[k] = {}
             for sk, sv in v.items():
                 if sv is None:
                     continue
                 if isinstance(sv, Path):
                     serializable_config[k][sk] = str(sv)
                 else:
                     serializable_config[k][sk] = sv
        else:
            serializable_config[k] = v

    with config_file.open("wb") as f:
        tomli_w.dump(serializable_config, f)

def get_context() -> Optional[str]:
    config = load_config(get_config_path())
    if config.context:
        return config.context.get("filter")
    return None

def set_context(filter_str: Optional[str]) -> None:
    config = load_config(get_config_path())
    if config.context is None:
        config.context = {}
    if filter_str:
        config.context["filter"] = filter_str
    else:
        if "filter" in config.context:
            del config.context["filter"]
        if not config.context:
            config.context = None
    save_config(config.model_dump())

def get_campaign() -> Optional[str]:
    config = load_config(get_config_path())
    if config.campaign:
        return config.campaign.get("name")
    return None

def set_campaign(name: Optional[str]) -> None:
    config = load_config(get_config_path())
    if config.campaign is None:
        config.campaign = {}
    if name:
        config.campaign["name"] = name
    else:
        if "name" in config.campaign:
            del config.campaign["name"]
        if not config.campaign:
            config.campaign = None
    save_config(config.model_dump())

def get_editor_command() -> Optional[str]:
    """
    Returns the editor command from the config file.
    """
    config = load_config(get_config_path())
    # TODO: Move editor to its own section in the config file
    if config.context:
        return config.context.get("editor")
    return None

def get_enrichment_service_url() -> str:
    """
    Returns the URL for the enrichment service, either from an environment variable
    or defaulting to the local Docker endpoint.
    """
    return os.getenv("COCLI_ENRICHMENT_SERVICE_URL", "http://localhost:8000")

def create_default_config_file() -> None:
    """
    Creates a default cocli_config.toml file if it doesn't exist.
    """
    config_dir = get_config_dir()
    config_file = config_dir / "cocli_config.toml"

    if not config_file.exists():
        default_settings_template = """
# cocli Configuration File

# Scraper settings for Google Maps
[scraper]
# Delay in seconds between page scrolls/requests for Google Maps scraper.
# Recommended to avoid being blocked.
google_maps_delay_seconds = 20

# Maximum number of pages/scrolls to fetch for Google Maps scraper.
# Each "page" corresponds to a scroll action that loads more results.
google_maps_max_pages = 3
"""
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            with config_file.open('w', encoding='utf-8') as f: # Open in text mode for writing template string
                f.write(default_settings_template)
            logger.info(f"Created default config file at {config_file}")
        except Exception as e:
            logger.error(f"Error creating default config file {config_file}: {e}")