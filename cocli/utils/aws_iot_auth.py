from __future__ import annotations
import json
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_cache_lock = threading.Lock()
_cached_creds: Optional[dict[str, str]] = None
_cached_until: Optional[datetime] = None
_DEFAULT_TTL = timedelta(minutes=50)


def clear_iot_sts_cache() -> None:
    """Test helper: drop the in-process STS cache."""
    global _cached_creds, _cached_until
    with _cache_lock:
        _cached_creds = None
        _cached_until = None


def _parse_expiration(raw: object) -> datetime:
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed - timedelta(seconds=60)
        except ValueError:
            pass
    return datetime.now(timezone.utc) + _DEFAULT_TTL


def get_iot_sts_credentials(iot_config_path: Optional[Path] = None) -> Optional[dict[str, str]]:
    """
    Exchanges an IoT certificate for temporary AWS STS credentials using the helper script.
    Cached in-process until expiry so enrichment finalize cannot refetch per task.
    """
    global _cached_creds, _cached_until
    now = datetime.now(timezone.utc)
    with _cache_lock:
        if _cached_creds is not None and _cached_until is not None and now < _cached_until:
            return _cached_creds

    if iot_config_path is None:
        # 1. Try RPI/Container default
        path = Path("/root/.cocli/iot/iot_config.json")
        try:
            exists = path.exists()
        except PermissionError:
            exists = False

        if not exists:
            # 2. Try User home fallback
            path = Path.home() / ".cocli" / "iot" / "iot_config.json"
        iot_config_path = path

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
        creds = {
            "access_key": data["AccessKeyId"],
            "secret_key": data["SecretAccessKey"],
            "token": data["SessionToken"]
        }
        expires = _parse_expiration(data.get("Expiration"))
        with _cache_lock:
            _cached_creds = creds
            _cached_until = expires
        return creds
    except Exception as e:
        logger.error(f"Failed to fetch IoT credentials via script: {e}")
        return None