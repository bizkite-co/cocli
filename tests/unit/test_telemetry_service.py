from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from cocli.application.telemetry_service import GoogleTelemetryProvider


class _FakeHTTPResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_register_event_custom_dimension_is_idempotent() -> None:
    """The actual point: re-registering an already-registered dimension
    (e.g. a second deploy, or a second person running the same command)
    must return the existing registration rather than attempting a
    second POST - GA4's Admin API 400s on a duplicate parameterName."""
    provider = GoogleTelemetryProvider("roadmap")

    existing_list = {
        "customDimensions": [
            {
                "name": "properties/510155544/customDimensions/15938593682",
                "parameterName": "button_label",
                "displayName": "Button Label",
                "scope": "EVENT",
            }
        ]
    }

    responses = [_FakeHTTPResponse(existing_list)]

    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="faketoken\n")), patch(
        "urllib.request.urlopen", side_effect=responses
    ) as mock_urlopen:
        result = provider.register_event_custom_dimension(
            "510155544", "button_label", "Button Label"
        )

    assert result["parameterName"] == "button_label"
    assert result["name"] == "properties/510155544/customDimensions/15938593682"
    # Only the list GET happened - no POST was attempted for a duplicate.
    assert mock_urlopen.call_count == 1


def test_register_event_custom_dimension_creates_when_not_already_present() -> None:
    provider = GoogleTelemetryProvider("roadmap")

    empty_list: dict[str, Any] = {}
    created = {
        "name": "properties/510155544/customDimensions/99999",
        "parameterName": "cta_label",
        "displayName": "CTA Label",
        "scope": "EVENT",
    }

    responses = [_FakeHTTPResponse(empty_list), _FakeHTTPResponse(created)]

    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="faketoken\n")), patch(
        "urllib.request.urlopen", side_effect=responses
    ) as mock_urlopen:
        result = provider.register_event_custom_dimension(
            "510155544", "cta_label", "CTA Label"
        )

    assert result == created
    assert mock_urlopen.call_count == 2


def test_query_cta_clicks_filters_by_event_name_and_requests_button_label() -> None:
    provider = GoogleTelemetryProvider("roadmap")

    report = {
        "dimensionHeaders": [{"name": "pagePath"}, {"name": "customEvent:button_label"}],
        "metricHeaders": [{"name": "eventCount"}],
        "rows": [
            {
                "dimensionValues": [{"value": "/signup/"}, {"value": "Request a Callback"}],
                "metricValues": [{"value": "3"}],
            }
        ],
    }

    captured_payload: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int = 30) -> _FakeHTTPResponse:
        captured_payload.update(json.loads(req.data.decode("utf-8")))
        return _FakeHTTPResponse(report)

    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="faketoken\n")), patch(
        "urllib.request.urlopen", side_effect=fake_urlopen
    ):
        rows = provider.query_cta_clicks("510155544", days=7)

    assert rows == [{"pagePath": "/signup/", "customEvent:button_label": "Request a Callback", "eventCount": "3"}]
    assert {"name": "customEvent:button_label"} in captured_payload["dimensions"]
    assert captured_payload["dimensionFilter"]["filter"]["fieldName"] == "eventName"
    assert captured_payload["dimensionFilter"]["filter"]["stringFilter"]["value"] == "cta_click"
