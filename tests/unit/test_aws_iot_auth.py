from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from cocli.utils.aws_iot_auth import clear_iot_sts_cache, get_iot_sts_credentials


def _token_payload(*, key: str = "AKIATEST1", expiration: str | None = None) -> str:
    body: dict[str, str] = {
        "AccessKeyId": key,
        "SecretAccessKey": "secret",
        "SessionToken": "token",
    }
    if expiration is not None:
        body["Expiration"] = expiration
    return json.dumps(body)


def test_get_iot_sts_credentials_caches_until_expiry(tmp_path) -> None:
    clear_iot_sts_cache()
    config = tmp_path / "iot_config.json"
    config.write_text("{}", encoding="utf-8")
    (tmp_path / "get_tokens.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    first = MagicMock(stdout=_token_payload(key="AKIATEST1", expiration=future))
    second = MagicMock(stdout=_token_payload(key="AKIATEST2", expiration=future))

    with patch("cocli.utils.aws_iot_auth.subprocess.run", side_effect=[first, second]) as run:
        a = get_iot_sts_credentials(iot_config_path=config)
        b = get_iot_sts_credentials(iot_config_path=config)

    assert a is not None and a["access_key"] == "AKIATEST1"
    assert b is not None and b["access_key"] == "AKIATEST1"
    assert run.call_count == 1
    clear_iot_sts_cache()


def test_get_iot_sts_credentials_refetches_when_expired(tmp_path) -> None:
    clear_iot_sts_cache()
    config = tmp_path / "iot_config.json"
    config.write_text("{}", encoding="utf-8")
    (tmp_path / "get_tokens.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    first = MagicMock(stdout=_token_payload(key="OLDKEY", expiration=past))
    second = MagicMock(stdout=_token_payload(key="NEWKEY", expiration=future))

    with patch("cocli.utils.aws_iot_auth.subprocess.run", side_effect=[first, second]) as run:
        a = get_iot_sts_credentials(iot_config_path=config)
        b = get_iot_sts_credentials(iot_config_path=config)

    assert a is not None and a["access_key"] == "OLDKEY"
    assert b is not None and b["access_key"] == "NEWKEY"
    assert run.call_count == 2
    clear_iot_sts_cache()
