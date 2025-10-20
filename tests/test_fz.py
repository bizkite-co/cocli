import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path

from cocli.main import app
from cocli.core.utils import slugify

runner = CliRunner()

@pytest.fixture
def setup_test_environment(tmp_path, mocker):
    # Create a temporary base directory for all cocli data
    cocli_base_dir = tmp_path / "cocli"
    cocli_base_dir.mkdir()

    # Create subdirectories
    companies_dir = cocli_base_dir / "companies"
    companies_dir.mkdir()
    people_dir = cocli_base_dir / "people"
    people_dir.mkdir()

    # Delete cache file if it exists
    cache_file = cocli_base_dir / "fz_cache.json"
    if cache_file.exists():
        cache_file.unlink()

    # Create a test company
    company_name = "Test Company"
    company_slug = slugify(company_name)
    company_dir = companies_dir / company_slug
    company_dir.mkdir()
    index_path = company_dir / "_index.md"
    index_path.write_text(f'''---
name: {company_name}
domain: testcompany.com
tags: ["test"]
---
This is a test company.
''')

    tags_path = company_dir / "tags.lst"
    tags_path.write_text("test\n")

    # Patch the config functions to use the temporary directory
    mocker.patch('cocli.core.cache.get_cocli_base_dir', return_value=cocli_base_dir)
    mocker.patch('cocli.core.cache.get_companies_dir', return_value=companies_dir)
    mocker.patch('cocli.core.cache.get_people_dir', return_value=people_dir)

    # Create a temporary config file for the test
    test_config_dir = cocli_base_dir / "config"
    test_config_dir.mkdir()
    test_config_path = test_config_dir / "cocli_config.toml"
    test_config_path.write_text('[campaign]\nname = "test"\n')
    mocker.patch('cocli.core.config.get_config_path', return_value=test_config_path)

    return company_name, cocli_base_dir

def test_fz_finds_and_views_company(setup_test_environment, mocker):
    """
    Integration test for the fz command.
    - Ensures the cache is built correctly.
    - Ensures fzf is called with the correct input.
    - Ensures the selected company is viewed.
    """
    company_name, cocli_base_dir = setup_test_environment
    company_slug = slugify(company_name)

    mock_view_company = mocker.patch('cocli.commands.fz.view_company')

    with patch('cocli.commands.fz.run_fzf') as mock_run_fzf:

        # Simulate fzf selecting the test company
        mock_run_fzf.return_value = f'COMPANY:{company_name} -- {company_slug}'

        # Run the fz command
        result = runner.invoke(app, ["fz"])

        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")

        assert result.exit_code == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"

        # Verify that fzf was called with the test company
        fzf_input = mock_run_fzf.call_args[0][0]
        assert company_name in fzf_input

        mock_view_company.assert_called_once_with(company_slug=company_slug)

def test_fz_with_none_filter_in_config(setup_test_environment, mocker):
    """
    Tests that the fz command correctly handles a context filter with the literal value "None".
    It should treat it as if there is no filter.
    """
    company_name, _ = setup_test_environment
    company_slug = slugify(company_name)

    # Mock get_context to return the problematic "None" string
    mocker.patch('cocli.commands.fz.get_context', return_value="None")

    mock_view_company = mocker.patch('cocli.commands.fz.view_company')

    with patch('cocli.commands.fz.run_fzf') as mock_run_fzf:

        # Simulate fzf selecting the test company
        mock_run_fzf.return_value = f'COMPANY:{company_name} -- {company_slug}'

        # Run the fz command
        result = runner.invoke(app, ["fz"])

        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")

        assert result.exit_code == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"

        # Verify that fzf was called with the test company, indicating the filter was ignored
        fzf_input = mock_run_fzf.call_args[0][0]
        assert company_name in fzf_input

        # Verify that view_company was called
        mock_view_company.assert_called_once_with(company_slug=company_slug)