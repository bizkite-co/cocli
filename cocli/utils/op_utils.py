import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def get_op_secret(op_path: str) -> Optional[str]:
    """
    Retrieves a secret from 1Password using the 'op' CLI.
    Expects a path like 'op://Vault/Item/Field'
    """
    if not op_path or not op_path.startswith("op://"):
        return None
        
    try:
        # We use check=True to raise an exception on non-zero exit
        # We use capture_output=True to get the secret from stdout
        result = subprocess.run(
            ["op", "read", op_path],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to read from 1Password path '{op_path}': {e.stderr}")
        return None
    except FileNotFoundError:
        logger.error("The 'op' CLI was not found in the system path.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving 1Password secret: {e}")
        return None
