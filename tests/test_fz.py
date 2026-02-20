import pytest
from click.testing import CliRunner
from slugify import slugify
import typer

from cocli.main import app
from cocli.core.paths import paths
from cocli.core.cache import build_cache

runner = CliRunner()

@pytest.fixture
def setup_test_environment(mock_cocli_env, mocker):
    """
    Sets up a mock cocli environment with a test company.
    """
    company_name = "Test Company"
    company_slug = slugify(company_name)
    company_dir = paths.companies / company_slug
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "_index.md").write_text(f"---\nname: {company_name}\ntags: [test]\n---")
    
    # Mock campaign to None so build_cache and search use global cache
    mocker.patch('cocli.commands.fz.get_campaign', return_value=None)
    mocker.patch('cocli.core.config.get_campaign', return_value=None)
    mocker.patch('cocli.application.search_service.get_campaign', return_value=None)
    
    build_cache()
    return company_name, mock_cocli_env

def test_fz_finds_and_views_company(setup_test_environment, mocker):
    """
    Integration test for the fz command.
    """
    company_name, _ = setup_test_environment
    company_slug = slugify(company_name)

    mock_view_company = mocker.patch('cocli.commands.fz.view_company')
    # We MUST patch the run_fzf in the correct module
    mock_run_fzf = mocker.patch('cocli.commands.fz.run_fzf')
    mock_run_fzf.return_value = f'COMPANY:{company_name} -- {company_slug}'

    # Get the click object from typer for CliRunner
    click_app = typer.main.get_command(app)
    result = runner.invoke(click_app, ["fz"])

    assert result.exit_code == 0
    assert mock_run_fzf.called
    mock_view_company.assert_called_once_with(company_slug=company_slug)

def test_fz_with_none_filter_in_config(setup_test_environment, mocker):
    """
    Tests that the fz command correctly handles a context filter with the literal value "None".
    """
    company_name, _ = setup_test_environment
    company_slug = slugify(company_name)

    mocker.patch('cocli.commands.fz.get_context', return_value="None")
    mock_view_company = mocker.patch('cocli.commands.fz.view_company')
    mock_run_fzf = mocker.patch('cocli.commands.fz.run_fzf')
    mock_run_fzf.return_value = f'COMPANY:{company_name} -- {company_slug}'

    click_app = typer.main.get_command(app)
    result = runner.invoke(click_app, ["fz"])

    assert result.exit_code == 0
    assert mock_run_fzf.called
    mock_view_company.assert_called_once_with(company_slug=company_slug)
