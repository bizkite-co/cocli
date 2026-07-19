"""Consumer proof: cocli stations inspect resolves paths and calls stations."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

from typer.testing import CliRunner

from cocli.commands.stations_cmd import app


def _install_fake_stations_inspect(render: MagicMock) -> None:
    """Inject a fake stations.inspect so tests do not need stations>=0.2.0."""
    pkg = ModuleType("stations")
    inspect_mod = ModuleType("stations.inspect")
    inspect_mod.inspect_and_render = render  # type: ignore[attr-defined]
    pkg.inspect = inspect_mod  # type: ignore[attr-defined]
    sys.modules["stations"] = pkg
    sys.modules["stations.inspect"] = inspect_mod


def test_inspect_with_explicit_path(tmp_path: Path) -> None:
    root = tmp_path / "queues" / "demo"
    (root / "pending").mkdir(parents=True)
    (root / "pending" / "item.json").write_text("{}", encoding="utf-8")

    mock_render = MagicMock(return_value=MagicMock())
    _install_fake_stations_inspect(mock_render)

    runner = CliRunner()
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
