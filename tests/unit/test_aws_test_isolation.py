"""Default pytest isolation must not use the user's 1Password AWS chain."""

from __future__ import annotations

import os

import boto3


def test_boto3_default_session_uses_dummy_testing_keys() -> None:
    creds = boto3.Session().get_credentials()
    assert creds is not None
    frozen = creds.get_frozen_credentials()
    assert frozen.access_key == "testing"
    assert frozen.secret_key == "testing"
    assert os.environ["AWS_ACCESS_KEY_ID"] == "testing"
    config_file = os.environ["AWS_CONFIG_FILE"]
    assert "cocli_test_data" in config_file.replace("\\", "/")
    assert "1password" not in open(config_file, encoding="utf-8").read().lower()
