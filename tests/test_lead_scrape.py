import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime
from typer.testing import CliRunner

from cocli.main import app
from cocli.models.google_maps import GoogleMapsData

runner = CliRunner()

@pytest.fixture
def mock_scrape_and_import():
    """Mocks scrape_google_maps and import_data functions."""
    with patch('cocli.commands.lead_scrape.scrape_google_maps') as mock_scrape, \
         patch('cocli.commands.lead_scrape.import_data') as mock_import:
        # Mock GoogleMapsData object
        mock_google_maps_data = GoogleMapsData(
            Place_ID="test_place_id",
            Name="Test Business",
            Full_Address="123 Test St",
            Website="http://test.com",
            Phone="+1234567890",
            Category="Test Category",
            Latitude=0.0,
            Longitude=0.0,
            Google_Maps_URL="http://maps.google.com/test",
            GMB_URL="http://gmb.google.com/test",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_scrape.return_value = [mock_google_maps_data]
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
    assert "Scraping completed. Results saved to" in result.stdout
    assert "google_maps_scrape_photographer_" in result.stdout # Check for dynamic filename
    assert ".csv" in result.stdout # Check for dynamic filename
    assert "Importing data from" in result.stdout
    assert "Data import completed successfully." in result.stdout
    mock_scrape.assert_called_once_with(
        location_param={"city": "Whittier,CA"},
        search_string="photographer",
        debug=False,
        headless=True, # Add headless=True to the assertion
    )
    
    # Extract the dynamically generated CSV path from the stdout
    output_lines = result.stdout.split('\n')
    csv_path_line = [line for line in output_lines if "Scraping completed. Results saved to" in line][0]
    scraped_csv_path_str = csv_path_line.split("Results saved to ")[1].strip()
    scraped_csv_path = Path(scraped_csv_path_str)

    mock_import.assert_called_once_with(
        importer_name="google-maps",
        file_path=scraped_csv_path,
        debug=False,
    )

def test_lead_scrape_with_cleanup(mock_scrape_and_import):
    """
    Tests successful execution of lead_scrape command with cleanup.
    """
    mock_scrape, mock_import = mock_scrape_and_import

    result = runner.invoke(app, ["lead-scrape", "photographer", "--city", "Whittier,CA", "--cleanup"])
    mock_scrape.assert_called_once_with(
        location_param={"city": "Whittier,CA"},
        search_string="photographer",
        debug=False,
        headless=True, # Add headless=True to the assertion
    )

    assert result.exit_code == 0
    assert "Scraping completed. Results saved to" in result.stdout
    assert "google_maps_scrape_photographer_" in result.stdout # Check for dynamic filename
    assert ".csv" in result.stdout # Check for dynamic filename
    assert "Data import completed successfully." in result.stdout
    assert "Cleaning up scraped CSV file:" in result.stdout
    assert "Scraped CSV file deleted." in result.stdout
    
    # Extract the dynamically generated CSV path from the stdout
    output_lines = result.stdout.split('\n')
    csv_path_line = [line for line in output_lines if "Scraping completed. Results saved to" in line][0]
    scraped_csv_path_str = csv_path_line.split("Results saved to ")[1].strip()
    scraped_csv_path = Path(scraped_csv_path_str)

    assert not scraped_csv_path.exists() # Verify file was deleted

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
    mock_scrape.return_value = [] # Ensure an empty list is returned on error

    result = runner.invoke(app, ["lead-scrape", "photographer", "--city", "Whittier,CA"])

    assert result.exit_code == 1
    assert "An unexpected error occurred during lead scrape: Scraping error\n" in result.stderr
    mock_scrape.assert_called_once_with(
        location_param={"city": "Whittier,CA"},
        search_string="photographer",
        debug=False,
    )
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
    mock_scrape.assert_called_once_with(
        location_param={"city": "Whittier,CA"},
        search_string="photographer",
        debug=False,
    )
    mock_import.assert_called_once()

def test_lead_scrape_no_csv_on_scrape_failure(mock_scrape_and_import):
    """
    Tests that no CSV cleanup is attempted if scraping fails and returns None.
    """
    mock_scrape, mock_import = mock_scrape_and_import
    mock_scrape.return_value = [] # Simulate scrape_google_maps returning an empty list on failure

    result = runner.invoke(app, ["lead-scrape", "photographer", "--city", "Whittier,CA", "--cleanup"])

    assert result.exit_code == 1
    assert "Scraping failed, no data was returned.\n" in result.stderr
    assert "Cleaning up scraped CSV file" not in result.stdout