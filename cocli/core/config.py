import os
from pathlib import Path
import platform
import yaml
from pydantic import BaseModel, Field

def get_cocli_base_dir() -> Path:
    """
    Determines the root data directory for cocli, respecting environment variables.
    Order of precedence: COCLI_DATA_HOME > XDG_DATA_HOME > default.
    """
    if "COCLI_DATA_HOME" in os.environ:
        cocli_base_dir = Path(os.environ["COCLI_DATA_HOME"]).expanduser()
    elif "XDG_DATA_HOME" in os.environ:
        cocli_base_dir = Path(os.environ["XDG_DATA_HOME"]).expanduser() / "cocli"
    else:
        # Default location based on OS
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

class ScraperSettings(BaseModel):
    google_maps_delay_seconds: int = Field(20, description="Delay in seconds between page scrolls/requests for Google Maps scraper.")
    google_maps_max_pages: int = Field(3, description="Maximum number of pages/scrolls to fetch for Google Maps scraper.")

def load_scraper_settings() -> ScraperSettings:
    """
    Loads scraper settings from cocli_config.yml.
    """
    config_dir = get_config_dir()
    config_file = config_dir / "cocli_config.yml"

    if not config_file.exists():
        print(f"Warning: Config file not found at {config_file}. Using default scraper settings.")
        return ScraperSettings()

    try:
        with config_file.open('r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
            if config_data and "scraper" in config_data:
                return ScraperSettings(**config_data["scraper"])
            else:
                print(f"Warning: 'scraper' section not found in {config_file}. Using default scraper settings.")
                return ScraperSettings()
    except Exception as e:
        print(f"Error loading config file {config_file}: {e}. Using default scraper settings.")
        return ScraperSettings()