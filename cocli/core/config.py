import os
from pathlib import Path
import platform
import tomli
import tomli_w
from typing import Optional, Any, Dict
import logging

from pydantic_settings import BaseSettings
from rich.console import Console

console = Console()

logger = logging.getLogger(__name__)

def get_cocli_base_dir() -> Path:
    """
    Determines the root data directory for cocli.
    Order of precedence: COCLI_DATA_HOME (env var) > data.home (config file) > XDG_DATA_HOME (env var) > default.
    """
    # 1. Environment variable
    if "COCLI_DATA_HOME" in os.environ:
        cocli_base_dir = Path(os.environ["COCLI_DATA_HOME"]).expanduser()
        cocli_base_dir.mkdir(parents=True, exist_ok=True)
        return cocli_base_dir

    # 2. Config file
    config = load_config()
    if "data" in config and "home" in config["data"]:
        cocli_base_dir = Path(config["data"]["home"]).expanduser()
        cocli_base_dir.mkdir(parents=True, exist_ok=True)
        return cocli_base_dir

    # 3. XDG_DATA_HOME
    if "XDG_DATA_HOME" in os.environ:
        cocli_base_dir = Path(os.environ["XDG_DATA_HOME"]).expanduser() / "cocli"
    else:
        # 4. Default location based on OS
        if platform.system() == "Windows":
            cocli_base_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "cocli"
        elif platform.system() == "Darwin": # macOS
            cocli_base_dir = Path.home() / "Library" / "Application Support" / "cocli"
        else: # Linux and other Unix-like
            cocli_base_dir = Path.home() / ".local" / "share" / "cocli"

    cocli_base_dir.mkdir(parents=True, exist_ok=True)

    return cocli_base_dir

def get_config_dir() -> Path:
    """
    Determines the configuration directory for cocli.
    """
    if "COCLI_CONFIG_HOME" in os.environ:
        return Path(os.environ["COCLI_CONFIG_HOME"]).expanduser()
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
    companies_dir = get_cocli_base_dir() / "companies"
    companies_dir.mkdir(parents=True, exist_ok=True)
    return companies_dir

def get_people_dir() -> Path:
    people_dir = get_cocli_base_dir() / "people"
    people_dir.mkdir(parents=True, exist_ok=True)
    return people_dir

def get_scraped_data_dir() -> Path:
    scraped_data_dir = get_cocli_base_dir() / "scraped_data"
    scraped_data_dir.mkdir(parents=True, exist_ok=True)
    return scraped_data_dir

def get_campaigns_dir() -> Path:
    campaigns_dir = get_cocli_base_dir() / "campaigns"
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    return campaigns_dir


def get_campaign_dir(campaign_name: str) -> Optional[Path]:
    """
    Returns the directory for a specific campaign.
    """
    campaigns_dir = get_campaigns_dir()
    campaign_dir = campaigns_dir / campaign_name
    if campaign_dir.exists() and campaign_dir.is_dir():
        return campaign_dir
    return None

def get_all_campaign_dirs() -> list[Path]:
    """
    Returns a list of all campaign directories.
    """
    campaigns_dir = get_campaigns_dir()
    if campaigns_dir.exists() and campaigns_dir.is_dir():
        return [d for d in campaigns_dir.iterdir() if d.is_dir()]
    return []


class ScraperSettings(BaseSettings):
    google_maps_delay_seconds: float = 1.0
    google_maps_max_retries: int = 3
    google_maps_retry_delay_seconds: float = 5.0
    google_maps_cache_ttl_days: int = 30
    browser_headless: bool = True
    browser_width: int = 2500
    browser_height: int = 2000
    browser_devtools: bool = False

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


def get_config_path() -> Path:
    config_dir = get_config_dir()
    return config_dir / "cocli_config.toml"

def load_config() -> Dict[str, Any]:
    config_file = get_config_path()
    if not config_file.exists():
        return {}
    with config_file.open("rb") as f:
        return tomli.load(f)

def save_config(config_data: Dict[str, Any]) -> None:
    config_file = get_config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("wb") as f:
        tomli_w.dump(config_data, f)

def get_context() -> Optional[str]:
    config = load_config()
    context_config: Optional[Dict[str, Any]] = config.get("context")
    if context_config:
        return context_config.get("filter")
    return None

def set_context(filter_str: Optional[str]) -> None:
    config = load_config()
    context_config = config.get("context", {})
    if "context" not in config:
        config["context"] = context_config
    if filter_str:
        context_config["filter"] = filter_str
    else:
        if "filter" in context_config:
            del context_config["filter"]
        if not context_config:
            if "context" in config:
                del config["context"]
    save_config(config)

def get_campaign() -> Optional[str]:
    config = load_config()
    campaign_config: Optional[Dict[str, Any]] = config.get("campaign")
    if campaign_config:
        return campaign_config.get("name")
    return None

def set_campaign(name: Optional[str]) -> None:
    config = load_config()
    campaign_config = config.get("campaign", {})
    if "campaign" not in config:
        config["campaign"] = campaign_config
    if name:
        campaign_config["name"] = name
    else:
        if "name" in campaign_config:
            del campaign_config["name"]
        if not campaign_config:
            if "campaign" in config:
                del config["campaign"]
    save_config(config)

def get_editor_command() -> Optional[str]:
    """
    Returns the editor command from the config file.
    """
    config = load_config()
    # TODO: Move editor to its own section in the config file
    context_config: Optional[Dict[str, Any]] = config.get("context")
    if context_config:
        return context_config.get("editor")
    return None


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