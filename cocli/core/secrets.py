# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations
import os
import logging
from typing import Protocol, Optional, Any, cast
from ..utils.op_utils import get_op_item, get_op_secret, read_op_secrets

logger = logging.getLogger(__name__)

class SecretProvider(Protocol):
    """Secret plugin: 1Password, env, or a future manager.

    Every cocli secret read (CLI, TUI, AWS keys, video) goes through this
    surface. Do not add a second 1Password client.
    """

    def get_secret(self, key: str) -> Optional[str]:
        """Retrieves a single secret value by key/URI."""
        ...

    def get_secrets(self, *keys: str) -> list[Optional[str]]:
        """Several keys; 1Password may use one Hello unlock for the batch."""
        ...

    def get_item(self, item_id: str) -> Optional[dict[str, Any]]:
        """Retrieves a full secret item (e.g. JSON object) by ID."""
        ...


class OnePasswordProvider:
    """The 1Password plugin. I/O lives in op_utils (SDK, linux op, Hello)."""

    def get_secret(self, key: str) -> Optional[str]:
        if not key.startswith("op://"):
            logger.debug("1Password provider: treating %r as raw key", key)
        return get_op_secret(key)

    def get_secrets(self, *keys: str) -> list[Optional[str]]:
        if len(keys) >= 2 and all(k.startswith("op://") for k in keys):
            batch = read_op_secrets(*keys)
            if batch is not None and len(batch) == len(keys):
                return list(batch)
        return [self.get_secret(key) for key in keys]

    def get_item(self, item_id: str) -> Optional[dict[str, Any]]:
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

    def get_secrets(self, *keys: str) -> list[Optional[str]]:
        return [self.get_secret(key) for key in keys]

    def get_item(self, item_id: str) -> Optional[dict[str, Any]]:
        # For items in Env, we might expect a JSON string in an env var
        val = self.get_secret(item_id)
        if val:
            import json
            try:
                return cast(dict[str, Any], json.loads(val))
            except Exception:
                pass
        return None

def get_secret_provider(provider_type: str = "auto") -> SecretProvider:
    """
    Factory to get the configured secret provider.
    'auto' detects based on environment variables.
    """
    if provider_type == "auto":
        from ..utils.op_utils import onepassword_cli_available

        if "OP_SERVICE_ACCOUNT_TOKEN" in os.environ or onepassword_cli_available():
            return OnePasswordProvider()
        return EnvSecretProvider()
    
    if provider_type == "1password":
        return OnePasswordProvider()
    elif provider_type == "env":
        return EnvSecretProvider()
    
    raise ValueError(f"Unknown secret provider type: {provider_type}")
