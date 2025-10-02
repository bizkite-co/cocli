import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from cocli.scrapers.google_maps import _extract_business_data, scrape_google_maps, LEAD_SNIPER_HEADERS

# Sample HTML content from data/maps.google.com/item.html
SAMPLE_ITEM_HTML = """
<div><div class="Nv2PK tH5CWc THOPZb " jsaction="mouseover:pane.wfvdle9;mouseout:pane.wfvdle9"><a class="hfpxzc" aria-label="Touch Photography" href="https://www.google.com/maps/place/Touch+Photography/data=!4m7!3m6!1s0x80c32af5dab38457:0x7eb1082369d23dba!8m2!3d33.9874604!4d-117.8961057!16s%2Fg%2F1td6yczy!19sChIJV4Sz2vUqw4ARuj3SaSMIsX4?authuser=0&hl=en&rclk=1" jsaction="pane.wfvdle9;focus:pane.wfvdle9;blur:pane.wfvdle9;auxclick:pane.wfvdle9;keydown:pane.wfvdle9;clickmod:pane.wfvdle9" jslog="12690;track:click,contextmenu;mutable:true;metadata:WyIwYWhVS0V3anBtUFQ5dXBDUEF4VW5KRVFJSFlPVkExSVE4QmNJQ3lnRyIsbnVsbCwwXQ=="></a><div class="rWbY0d"></div><div class="bfdHYd Ppzolf OFBs3e  "><div class="rgFiGf OyjIsf "></div><div class="hHbUWd"></div><div class="rSy5If"></div><div class="lI9IFe "><div class="y7PRA"><div class="Lui3Od T7Wufd "><div class="Z8fK3b"><div class="OyjIsf "></div><div class="UaQhfb fontBodyMedium"><div class="NrDZNb"><div class="dIDW9d"></div><span class="HTCGSb"></span><div class="qBF1Pd fontHeadlineSmall ">Touch Photography</div> <span class="muMOJe"></span></div><div class="HAthLd"></div><div class="W4Efsd"><div class="AJB7ye"><span class="wZrhX"></span> <span class="e4rVHe fontBodyMedium"><span role="img" class="ZkP5Je" aria-label="4.3 stars 16 Reviews"><span class="MW4etd" aria-hidden="true">4.3</span><div class="QBUL8c "></div><div class="QBUL8c "></div><div class="QBUL8c "></div><div class="QBUL8c "></div><div class="QBUL8c vIBWLc "></div><span class="UY7F9" aria-hidden="true">(16)</span></span></span></div></div><div class="W4Efsd"><div class="W4Efsd"><span><span>Photography studio</span></span><span> <span aria-hidden="true">·</span> <span class="google-symbols" aria-label="Wheelchair accessible entrance" role="img" data-tooltip="Wheelchair accessible entrance" jsaction="focus:pane.focusTooltip; blur:pane.blurTooltip; keydown:pane.escapeTooltip" style="font-size: 15px;"><span class="doJOZc"></span></span></span><span> <span aria-hidden="true">·</span> <span>18702 Colima Rd #106</span></span></div><div class="W4Efsd"><span><span><span style="font-weight: 400; color: rgba(25,134,57,1.00);">Open</span><span style="font-weight: 400;"> ⋅ Closes 6 PM</span></span></span><span> <span aria-hidden="true">·</span> <span class="UsdlK">(626) 810-7688</span></span></div></div></div></div></div></div><div class="Rwjeuc"><div class="etWJQ jym1ob kdfrQc k17Vqe WY7ZIb"><a class="lcr4fd S9kvJb " jsaction="pane.wfvdle12;keydown:pane.wfvdle12;mouseover:pane.wfvdle12;mouseout:pane.wfvdle12" aria-label="Visit Touch Photography's website" data-value="Website" jslog="84919;track:click;mutable:true;metadata:WyIwYWhVS0V3anBtUFQ5dXBDUEF4VW5KRVFJSFlPVkExSVE2MWdJR2lnTiwiXQ==" href="https://touchweddingstudio.wixsite.com/touch"><span class="DVeyrd "><div class="OyjIsf zemfqc"></div><span class="Cw1rxd google-symbols" aria-hidden="true" style="font-size: 18px;"></span></span><div class="R8c4Qb fontLabelMedium">Website</div></a></div><div class="etWJQ jym1ob kdfrQc k17Vqe WY7ZIb"><button class="g88MCb S9kvJb " jsaction="pane.wfvdle13;keydown:pane.wfvdle13;mouseover:pane.wfvdle13;mouseout:pane.wfvdle13" aria-label="Get directions to Touch Photography" data-value="Directions" jslog="80860;track:click;mutable:true;metadata:WyIwYWhVS0V3anBtUFQ5dXBDUEF4VW5KRVFJSFlPVkExSVE4QmNJQ3lnRyJd"><span class="DVeyrd "><div class="OyjIsf zemfqc"></div><span class="Cw1rxd google-symbols NhBTye G47vBd" aria-hidden="true" style="font-size: 18px;"></span></span><div class="R8c4Qb fontLabelMedium">Directions</div></button></div></div><div class="SpFAAb"></div></div><div class="qty3Ue"><div class="AyRUI" aria-hidden="true" style="height: 8px;">&nbsp; </div><div class="n8sPKe fontBodySmall oj2eXe ccePVe "><div class="Ahnjwc fontBodyMedium "><div class="W6VQef "><div aria-hidden="true" class="JoXfOb fCbqBc" style="width: 16px; height: 16px;"><img alt="" class="Jn12ke xcEj5d " src="https://ssl.gstatic.com/local/servicebusiness/default_user.png" style="width: 16px; height: 16px;"></div><div class="ah5Ghc "><span style="font-weight: 400;">"The pricing is reasonable, and his </span><span style="font-weight: 500;">photography</span><span style="font-weight: 400;"> skills are excellent."</span></div></div><div class="Q4BGF"></div></div></div></div><div class="gwQ6lc" jsaction="click:mLt3mc"></div></div></div></div>
"""

@pytest.fixture
def mock_playwright():
    """Mocks playwright components for testing scrape_google_maps."""
    with patch('cocli.scrapers.google_maps.sync_playwright') as mock_sync_playwright:
        mock_playwright_instance = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_locator = MagicMock()

        mock_sync_playwright.return_value.__enter__.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.locator.return_value = mock_locator

        # Mock the scrollable div behavior
        mock_locator.evaluate.side_effect = [100, 100] # Simulate no new content after first scroll
        mock_locator.all.return_value = [MagicMock(get_attribute=lambda x: "https://www.google.com/maps/place/MockBusiness/data=!4m",
                                                    locator=lambda x: MagicMock(first=MagicMock(inner_html=lambda: SAMPLE_ITEM_HTML)))]

        yield mock_page, mock_locator

@pytest.fixture
def temp_output_dir(tmp_path):
    """Provides a temporary directory for test output."""
    return tmp_path / "temp_output"

@patch('cocli.scrapers.google_maps.get_coordinates_from_zip')
def test_scrape_google_maps_functionality(mock_get_coordinates, mock_playwright, temp_output_dir):
    """
    Tests the scrape_google_maps function with mocked Playwright and a temporary directory.
    Verifies URL construction and CSV file creation.
    """
    mock_page, mock_locator = mock_playwright
    zip_code = "90210"
    search_string = "photography studio"

    # Mock the return value of get_coordinates_from_zip
    mock_get_coordinates.return_value = {"latitude": 34.0736, "longitude": -118.4004}

    scrape_google_maps({"zip_code": zip_code}, search_string, output_dir=temp_output_dir, max_results=1)

    # Verify page.goto was called with the correct URL
    expected_url_part = f"https://www.google.com/maps/search/photography+studio/@34.0736,-118.4004,15z/data=!3m2!1e3!4b1?entry=ttu"
    mock_page.goto.assert_called_once()
    assert expected_url_part in mock_page.goto.call_args[0][0]

    # Verify CSV file was created
    csv_files = list(temp_output_dir.glob("*-photography-studio-*.csv"))
    assert len(csv_files) == 1
    output_csv_path = csv_files[0]
    assert output_csv_path.exists()

    # Verify CSV content (basic check)
    with open(output_csv_path, 'r', encoding='utf-8') as f:
        content = f.read()
        assert "Touch Photography" in content
        assert "photography studio" in content
        assert LEAD_SNIPER_HEADERS[0] in content # Check for header


def test_extract_business_data_basic():
    """
    Tests the _extract_business_data function with a sample HTML snippet.
    """
    keyword = "photography studio"
    data = _extract_business_data(SAMPLE_ITEM_HTML, keyword)

    assert data["Name"] == "Touch Photography"
    assert data["Keyword"] == keyword
    assert data["Full_Address"] == "18702 Colima Rd #106"
    assert data["Street_Address"] == "18702 Colima Rd #106"
    assert data["City"] == "" # This might need more robust parsing
    assert data["Zip"] == "" # This might need more robust parsing
    assert data["State"] == "" # This might need more robust parsing
    assert data["Country"] == "" # This might need more robust parsing
    assert data["Phone_1"] == "(626) 810-7688"
    assert data["Phone_Standard_format"] == "(626) 810-7688"
    assert data["Website"] == "https://touchweddingstudio.wixsite.com/touch"
    assert data["Domain"] == "touchweddingstudio.wixsite.com"
    assert data["First_category"] == "Photography studio"
    assert data["Reviews_count"] == "16"
    assert data["Average_rating"] == "4.3"
    assert data["Business_Status"] == "Open"
    assert data["Hours"] == "Closes 6 PM"
    assert "google.com/maps/place/Touch+Photography" in data["GMB_URL"]
    assert data["Latitude"] == "33.9874604"
    assert data["Longitude"] == "-117.8961057"
    assert data["Coordinates"] == "33.9874604,-117.8961057"
    assert data["Place_ID"] == "0x80c32af5dab38457:0x7eb1082369d23dba"
    assert data["id"] is not None
    assert data["Uuid"] is not None

    # Ensure all headers are present, even if empty
    for header in LEAD_SNIPER_HEADERS:
        assert header in data

def test_extract_business_data_missing_elements():
    """
    Tests _extract_business_data with a minimal HTML snippet to ensure graceful handling of missing elements.
    """
    minimal_html = """
    <div>
        <div class="Nv2PK">
            <a class="hfpxzc" href="https://www.google.com/maps/place/Minimal+Business/data=!4m"></a>
            <div class="bfdHYd">
                <div class="lI9IFe">
                    <div class="y7PRA">
                        <div class="Lui3Od">
                            <div class="Z8fK3b">
                                <div class="UaQhfb">
                                    <div class="NrDZNb">
                                        <div class="qBF1Pd fontHeadlineSmall">Minimal Business</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    keyword = "minimal test"
    data = _extract_business_data(minimal_html, keyword)

    assert data["Name"] == "Minimal Business"
    assert data["Keyword"] == keyword
    assert data["Full_Address"] == ""
    assert data["Website"] == ""
    assert data["Reviews_count"] == ""
    assert data["Average_rating"] == ""
    assert data["Business_Status"] == ""
    assert data["Hours"] == ""
    assert "google.com/maps/place/Minimal+Business" in data["GMB_URL"]
    assert data["id"] is not None
    assert data["Uuid"] is not None

    for header in LEAD_SNIPER_HEADERS:
        assert header in data