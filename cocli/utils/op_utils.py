import os
import subprocess
import logging
from typing import Optional, cast

logger = logging.getLogger(__name__)

def get_op_secret(op_path: str) -> Optional[str]:
    """
    Retrieves a secret from 1Password.
    Priority:
    1. 1Password Python SDK (via OP_SERVICE_ACCOUNT_TOKEN or Local Biometrics).
    2. Fallback to 'op' CLI if SDK is not available or fails.
    
    Expects a path like 'op://Vault/Item/Field'
    """
    if not op_path or not op_path.startswith("op://"):
        return None

    # 1. Attempt SDK Retrieval
    try:
        from onepassword.sdk import Client as NewSDKClient # type: ignore
        
        # New 1Password SDK (Official)
        if "OP_SERVICE_ACCOUNT_TOKEN" in os.environ:
            try:
                client = NewSDKClient.authenticate(
                    token=os.environ["OP_SERVICE_ACCOUNT_TOKEN"],
                    integration_name="cocli",
                    integration_version="0.1.0"
                )
                return cast(str, client.secrets.retrieve(op_path))
            except Exception as sdk_err:
                logger.debug(f"Official SDK retrieval failed: {sdk_err}")

    except ImportError:
        logger.debug("onepassword-sdk not found, falling back to CLI.")
    except Exception as e:
        logger.debug(f"SDK initialization failed: {e}")

    # 2. Fallback to 'op' CLI
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
        logger.error(f"Failed to read from 1Password path '{op_path}' via CLI: {e.stderr}")
        return None
    except FileNotFoundError:
        logger.error("The 'op' CLI was not found in the system path.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving 1Password secret via CLI: {e}")
        return None

