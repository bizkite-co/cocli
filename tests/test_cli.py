def test_help_command(runner, cli_app):
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert "Commands" in result.stdout