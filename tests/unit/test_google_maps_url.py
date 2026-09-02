from urllib.parse import parse_qs, urlparse

from cocli.utils.google_maps_url import google_maps_url


def test_url_uses_name_street_city_and_place_id() -> None:
    url = google_maps_url(
        place_id="ChIJQ1A68rPbyYkR_dONAUWyrRo",
        name="Adams Insurance Agency",
        street_address="474 Prospect Blvd",
        city="Frederick",
    )
    assert url is not None
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert qs["query_place_id"] == ["ChIJQ1A68rPbyYkR_dONAUWyrRo"]
    assert "google" not in qs["query"]
    assert "Adams Insurance Agency" in qs["query"][0]
    assert "474 Prospect Blvd" in qs["query"][0]
    assert "Frederick" in qs["query"][0]


def test_url_without_place_id_still_searches_address() -> None:
    url = google_maps_url(
        name="Adams Insurance Agency",
        street_address="474 Prospect Blvd",
        city="Frederick",
    )
    assert url is not None
    qs = parse_qs(urlparse(url).query)
    assert "query_place_id" not in qs
    assert "Frederick" in qs["query"][0]


def test_url_never_uses_query_google() -> None:
    url = google_maps_url(place_id="ChIJQ1A68rPbyYkR_dONAUWyrRo")
    assert url is not None
    assert "query=google" not in url
