import json
import subprocess
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

def get_iot_sts_credentials(iot_config_path: Path = Path("/root/.cocli/iot/iot_config.json")) -> Optional[Dict[str, str]]:
    """
    Exchanges an IoT certificate for temporary AWS STS credentials using the helper script.
    """
    if not iot_config_path.exists():
        return None

    script_path = iot_config_path.parent / "get_tokens.sh"
    if not script_path.exists():
        logger.warning(f"IoT token script missing at {script_path}")
        return None

    try:
        # Use the proven shell script to get tokens
        result = subprocess.run([str(script_path)], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        logger.info(f"Successfully retrieved IoT STS tokens (ID: {data['AccessKeyId']})")
        return {
            "access_key": data["AccessKeyId"],
            "secret_key": data["SecretAccessKey"],
            "token": data["SessionToken"]
        }
    except Exception as e:
        logger.error(f"Failed to fetch IoT credentials via script: {e}")
        return None