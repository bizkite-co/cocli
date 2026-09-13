"""Campaign AWS profiles resolve IAM keys through get_op_secret, not cmd.exe."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from cocli.core.reporting import (
    _op_refs_from_credential_process,
    get_boto3_session,
)


def test_op_refs_from_credential_process() -> None:
    cmd = (
        '/home/mstouffer/.aws/scripts/1password-aws-credentials.sh '
        '"op://Private/AWS_Civilton_Main/aws_access_key_id" '
        '"op://Private/AWS_Civilton_Main/aws_secret_access_key"'
    )
    refs = _op_refs_from_credential_process(cmd)
    assert refs == (
        "op://Private/AWS_Civilton_Main/aws_access_key_id",
        "op://Private/AWS_Civilton_Main/aws_secret_access_key",
    )


def test_get_boto3_session_uses_op_utils_for_1password_profile(
    tmp_path: Path, monkeypatch: Any
) -> None:
    cfg = tmp_path / "config"
    cfg.write_text(
        "[profile mark]\n"
        "region = us-east-1\n"
        "credential_process = /tmp/1password-aws-credentials.sh "
        '"op://Private/AWS_Civilton_Main/aws_access_key_id" '
        '"op://Private/AWS_Civilton_Main/aws_secret_access_key"\n'
        "\n"
        "[profile bizkite-support]\n"
        "region = us-east-1\n"
        "role_arn = arn:aws:iam::123:role/assumed-from-mark\n"
        "source_profile = mark\n"
    )
    monkeypatch.setenv("AWS_CONFIG_FILE", str(cfg))
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    pair = ["AKIATEST", "secret"]
    assumed = {
        "Credentials": {
            "AccessKeyId": "ASIAASSUMED",
            "SecretAccessKey": "assumed-secret",
            "SessionToken": "token",
        }
    }
    sts = MagicMock()
    sts.assume_role.return_value = assumed
    assumed_session = MagicMock()

    def fake_session(**kwargs: Any) -> MagicMock:
        if kwargs.get("profile_name"):
            raise RuntimeError(f"skip profile {kwargs['profile_name']}")
        built = MagicMock()
        if kwargs.get("aws_session_token"):
            return assumed_session
        built.client.return_value = sts
        return built

    provider = MagicMock()
    provider.get_secrets.return_value = pair
    with patch(
        "cocli.utils.aws_iot_auth.get_iot_sts_credentials", return_value=None
    ), patch(
        "cocli.core.secrets.get_secret_provider", return_value=provider
    ), patch(
        "cocli.core.reporting.boto3.Session", side_effect=fake_session
    ) as ctor:
        result = get_boto3_session(
            {"aws": {"profile": "bizkite-support"}, "campaign": {"name": "turboship"}}
        )

    assert result is assumed_session
    key_call = next(
        c for c in ctor.call_args_list if c.kwargs.get("aws_access_key_id") == "AKIATEST"
    )
    assert key_call.kwargs["aws_secret_access_key"] == "secret"
    sts.assume_role.assert_called_once()
