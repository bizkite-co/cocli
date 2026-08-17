"""Regression test for the domain-too-long crash (rwg_token query strings).

Google's outbound website links often carry an rwg_token redirect-tracking
query string with no path segment before it, e.g.
https://cydremodeling.com?rwg_token=...2cGPeoWxfG7GpFtQ%3D%3D. The domain
regex used [^/]+ alone, which only stops at '/' - not '?' or '#' - so the
entire query string was captured as the "domain", blowing past
GoogleMapsListItem's 100-char cap and crashing (nacking) the whole scan
task, discarding every other result already found in it. See task-agent
ticket
regression-gm-list-stuck-at-60-for-months-broken-stealth-script-and-no-backoff-on-google-block-detection.
"""

from bs4 import BeautifulSoup

from cocli.scrapers.google.google_maps_parsers.extract_website import extract_website


def _soup_with_website_link(href: str) -> BeautifulSoup:
    html = f'<div><a data-value="Website" href="{href}">Website</a></div>'
    return BeautifulSoup(html, "html.parser")


def test_query_string_is_stripped_from_domain() -> None:
    href = (
        "https://cydremodeling.com?rwg_token=AA2ezPMXaZjIkGmHKlj"
        "d92_2cGPeoWxfG7GpFtQ%3D%3D"
    )
    result = extract_website(_soup_with_website_link(href), "", debug=False)

    assert result["Domain"] == "cydremodeling.com"
    assert len(result["Domain"]) <= 100


def test_fragment_is_also_stripped_from_domain() -> None:
    result = extract_website(
        _soup_with_website_link("https://example.com#some-anchor"), "", debug=False
    )
    assert result["Domain"] == "example.com"


def test_normal_domain_with_path_still_works() -> None:
    result = extract_website(
        _soup_with_website_link("https://www.example.com/contact-us"), "", debug=False
    )
    assert result["Domain"] == "example.com"


def test_bare_domain_still_works() -> None:
    result = extract_website(_soup_with_website_link("https://example.com"), "", debug=False)
    assert result["Domain"] == "example.com"
