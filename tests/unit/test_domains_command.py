from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from cocli.commands.domains import app


def test_set_employee_directory_then_show(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    runner = CliRunner()

    set_result = runner.invoke(
        app,
        ["set-employee-directory", "higginbotham.com", "https://www.higginbotham.com/about/employee-directory/"],
    )
    assert set_result.exit_code == 0
    assert "Saved" in set_result.output

    show_result = runner.invoke(app, ["show", "higginbotham.com"])
    assert show_result.exit_code == 0
    assert "https://www.higginbotham.com/about/employee-directory/" in show_result.output


def test_show_reports_no_record_when_none_exists(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["show", "nowhere.example"])
    assert result.exit_code == 0
    assert "No domain record" in result.output
