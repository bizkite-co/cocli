import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from typer.testing import CliRunner

from cocli.main import app

runner = CliRunner()

@pytest.fixture
def mock_scrape_and_import():
    """Mocks scrape_google_maps and import_data functions."""
    with patch('cocli.commands.lead_scrape.scrape_google_maps') as mock_scrape, \
         patch('cocli.commands.lead_scrape.import_data') as mock_import:
        mock_scrape.return_value = Path("/tmp/test_scraped_data.csv")
        mock_import.return_value = None
        yield mock_scrape, mock_import

def test_lead_scrape_success(mock_scrape_and_import):
    """
    Tests successful execution of lead_scrape command without cleanup.
    """
    mock_scrape, mock_import = mock_scrape_and_import
    result = runner.invoke(app, ["lead-scrape", "photographer", "--city", "Whittier,CA"])

    assert result.exit_code == 0
    assert "Starting lead scrape for query: 'photographer'" in result.stdout
    assert "Scraping Google Maps..." in result.stdout
    assert "Scraping completed. Results saved to /tmp/test_scraped_data.csv" in result.stdout
    assert "Importing data from /tmp/test_scraped_data.csv..." in result.stdout
    assert "Data import completed successfully." in result.stdout
    assert "Scraped CSV file deleted." not in result.stdout

    mock_scrape.assert_called_once_with(
        location_param={"city": "Whittier,CA"},
        search_string="photographer",
        output_dir=Path("/home/mstouffer/.local/share/cocli_data/scraped_data"),
        debug=False,
    )
    mock_import.assert_called_once_with(
        importer_name="lead-sniper",
        file_path=Path("/tmp/test_scraped_data.csv"),
        debug=False,
    )

def test_lead_scrape_with_cleanup(mock_scrape_and_import):
    """
    Tests successful execution of lead_scrape command with cleanup.
    """
    mock_scrape, mock_import = mock_scrape_and_import

    # Create a dummy file to be "cleaned up"
    dummy_csv_path = Path("/tmp/test_scraped_data.csv")
    dummy_csv_path.touch()
    mock_scrape.return_value = dummy_csv_path

    result = runner.invoke(app, ["lead-scrape", "photographer", "--city", "Whittier,CA", "--cleanup"])
    mock_scrape.assert_called_once_with(
        location_param={"city": "Whittier,CA"},
        search_string="photographer",
        output_dir=Path("/home/mstouffer/.local/share/cocli_data/scraped_data"),
        debug=False,
    )

    assert result.exit_code == 0
    assert "Scraping completed. Results saved to /tmp/test_scraped_data.csv" in result.stdout
    assert "Data import completed successfully." in result.stdout
    assert "Cleaning up scraped CSV file: /tmp/test_scraped_data.csv" in result.stdout
    assert "Scraped CSV file deleted." in result.stdout
    assert not dummy_csv_path.exists() # Verify file was deleted

def test_lead_scrape_no_location_param():
    """
    Tests lead_scrape command when no location parameter is provided.
    """
    result = runner.invoke(app, ["lead-scrape", "photographer"])
    assert result.exit_code == 1
    assert "Error: Either --zip or --city must be provided.\n" in result.stderr

def test_lead_scrape_both_location_params():
    """
    Tests lead_scrape command when both zip_code and city are provided.
    """
    result = runner.invoke(app, ["lead-scrape", "photographer", "--zip", "90210", "--city", "Whittier,CA"])
    assert result.exit_code == 1
    assert "Error: Cannot provide both --zip and --city. Please choose one.\n" in result.stderr

def test_lead_scrape_scraping_failure(mock_scrape_and_import):
    """
    Tests lead_scrape command when scraping fails.
    """
    mock_scrape, mock_import = mock_scrape_and_import
    mock_scrape.side_effect = Exception("Scraping error")
    mock_scrape.return_value = None # Ensure no path is returned on error

    result = runner.invoke(app, ["lead-scrape", "photographer", "--city", "Whittier,CA"])

    assert result.exit_code == 1
    assert "An unexpected error occurred during lead scrape: Scraping error\n" in result.stderr
    mock_scrape.assert_called_once()
    mock_import.assert_not_called() # Import should not be called if scraping fails

def test_lead_scrape_import_failure(mock_scrape_and_import):
    """
    Tests lead_scrape command when import fails.
    """
    mock_scrape, mock_import = mock_scrape_and_import
    mock_import.side_effect = Exception("Import error")

    result = runner.invoke(app, ["lead-scrape", "photographer", "--city", "Whittier,CA"])

    assert result.exit_code == 1
    assert "An unexpected error occurred during lead scrape: Import error\n" in result.stderr
    mock_scrape.assert_called_once()
    mock_import.assert_called_once()

def test_lead_scrape_no_csv_on_scrape_failure(mock_scrape_and_import):
    """
    Tests that no CSV cleanup is attempted if scraping fails and returns None.
    """
    mock_scrape, mock_import = mock_scrape_and_import
    mock_scrape.return_value = None # Simulate scrape_google_maps returning None on failure

    result = runner.invoke(app, ["lead-scrape", "photographer", "--city", "Whittier,CA", "--cleanup"])

    assert result.exit_code == 1
    assert "Scraping failed, no CSV file was generated.\n" in result.stderr
    assert "Cleaning up scraped CSV file" not in result.stdout