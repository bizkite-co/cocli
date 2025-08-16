import pytest
from typer.testing import CliRunner
from cocli.main import app

@pytest.fixture(scope="session")
def runner():
    return CliRunner()

@pytest.fixture(scope="session")
def cli_app():
    return app