"""Consumer proof: cocli stations inspect resolves paths and calls stations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cocli.commands.stations_cmd import app


def test_inspect_with_explicit_path(tmp_path: Path) -> None:
    root = tmp_path / "queues" / "demo"
    (root / "pending").mkdir(parents=True)
    (root / "pending" / "item.json").write_text("{}", encoding="utf-8")

    runner = CliRunner()
    with patch("stations.inspect.inspect_and_render") as mock_render:
        mock_render.return_value = MagicMock()
        result = runner.invoke(app, ["inspect", "--path", str(root), "--plain"])
    assert result.exit_code == 0, result.output
    mock_render.assert_called_once()
    args, kwargs = mock_render.call_args
    assert args[0] == str(root.resolve())
    assert kwargs.get("plain") is True


def test_inspect_missing_path_exits_2(tmp_path: Path) -> None:
    runner = CliRunner()
    missing = tmp_path / "nope"
    result = runner.invoke(app, ["inspect", "--path", str(missing)])
    assert result.exit_code == 2
