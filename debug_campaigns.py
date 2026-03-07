from cocli.core.config import get_campaign, get_all_campaign_dirs, get_config_path
from cocli.core.paths import paths
import os

print(f"COCLI_DATA_HOME: {os.environ.get('COCLI_DATA_HOME')}")
print(f"paths.root: {paths.root}")
print(f"Config path: {get_config_path()}")
print(f"Active campaign: {get_campaign()}")

campaigns = get_all_campaign_dirs()
print(f"Found {len(campaigns)} campaigns:")
for c in campaigns:
    print(f"  - {c}")
