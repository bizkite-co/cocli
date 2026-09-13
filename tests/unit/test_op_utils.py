"""1Password helper prefers native linux ``op``, not Windows cmd.exe."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cocli.core.secrets import OnePasswordProvider
from cocli.utils.op_utils import get_op_secret


def test_onepassword_provider_batches_two_refs_for_one_hello() -> None:
    with patch(
        "cocli.core.secrets.read_op_secrets",
        return_value=["AKIATEST", "secret"],
    ) as batch:
        values = OnePasswordProvider().get_secrets(
            "op://Private/AWS_Civilton_Main/aws_access_key_id",
            "op://Private/AWS_Civilton_Main/aws_secret_access_key",
        )
    assert values == ["AKIATEST", "secret"]
    batch.assert_called_once()


def test_get_op_secret_falls_back_to_op_read_paused() -> None:
    paused = MagicMock()
    paused.returncode = 0
    paused.stdout = "AKIATEST\n"
    paused.stderr = ""
    with patch("cocli.utils.op_utils._read_via_linux_op", return_value=None), patch(
        "cocli.utils.op_utils.os.path.isfile", return_value=True
    ), patch("cocli.utils.op_utils.run_windows_cmd", return_value=paused) as run:
        value = get_op_secret("op://Private/AWS_Civilton_Main/aws_access_key_id")

    assert value == "AKIATEST"
    assert run.call_args.args[0].endswith("op-read-paused.cmd")
    assert "op://Private/AWS_Civilton_Main/aws_access_key_id" in run.call_args.args


def test_get_op_secret_uses_linux_op_not_windows_exe() -> None:
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "AKIATEST\n"
    fake.stderr = ""
    with patch("cocli.utils.op_utils.shutil.which", return_value="/usr/bin/op"), patch(
        "cocli.utils.op_utils.subprocess.run", return_value=fake
    ) as run:
        value = get_op_secret("op://Private/AWS_Civilton_Main/aws_access_key_id")

    assert value == "AKIATEST"
    cmd = run.call_args.args[0]
    assert cmd[0] == "/usr/bin/op"
    assert cmd[1] == "read"
    assert not any(str(part).endswith("op.exe") for part in cmd)
    assert not any("cmd.exe" in str(part) for part in cmd)
