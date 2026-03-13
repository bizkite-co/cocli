# POLICY: frictionless-data-policy-enforcement
import os
import logging
from typing import Protocol, Optional, Dict, Any, cast
from ..utils.op_utils import get_op_secret, get_op_item

logger = logging.getLogger(__name__)

class SecretProvider(Protocol):
    """
    Protocol for secret management plugins.
    Allows cocli to support different password managers (1Password, Bitwarden, etc.)
    or standard environment variables.
    """
    def get_secret(self, key: str) -> Optional[str]:
        """Retrieves a single secret value by key/URI."""
        ...

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a full secret item (e.g. JSON object) by ID."""
        ...

class OnePasswordProvider:
    """
    Implementation of SecretProvider for 1Password.
    Supports both official SDK and CLI fallback.
    """
    def get_secret(self, key: str) -> Optional[str]:
        # Handle both raw keys and op:// URIs
        if not key.startswith("op://"):
            # If it's just a key, we might need a default vault or more context
            # but for now we assume it's a valid URI if passed to 1Password
            logger.debug(f"1Password provider: treating '{key}' as raw key (no op:// prefix)")
        
        return get_op_secret(key)

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        return get_op_item(item_id)

class EnvSecretProvider:
    """
    Implementation of SecretProvider that reads from environment variables.
    Useful for CI/CD or simple deployments without a password manager.
    """
    def get_secret(self, key: str) -> Optional[str]:
        # Strip op:// prefix if present to find env var name
        env_key = key.replace("op://", "").replace("/", "_").replace(" ", "_").upper()
        return os.environ.get(env_key) or os.environ.get(key)

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        # For items in Env, we might expect a JSON string in an env var
        val = self.get_secret(item_id)
        if val:
            import json
            try:
                return cast(Dict[str, Any], json.loads(val))
            except Exception:
                pass
        return None

def get_secret_provider(provider_type: str = "auto") -> SecretProvider:
    """
    Factory to get the configured secret provider.
    'auto' detects based on environment variables.
    """
    if provider_type == "auto":
        if "OP_SERVICE_ACCOUNT_TOKEN" in os.environ or os.access("/usr/bin/op", os.X_OK):
            return OnePasswordProvider()
        return EnvSecretProvider()
    
    if provider_type == "1password":
        return OnePasswordProvider()
    elif provider_type == "env":
        return EnvSecretProvider()
    
    raise ValueError(f"Unknown secret provider type: {provider_type}")
