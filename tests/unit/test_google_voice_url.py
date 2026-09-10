from __future__ import annotations

from unittest.mock import patch

from cocli.utils.google_voice_url import google_voice_url


def test_google_voice_url_default() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ):
        url = google_voice_url("5551234567")
        assert "voice.google.com/u/0/calls?" in url
        assert "authuser=bizkitellc%40gmail.com" in url or "authuser=bizkitellc@gmail.com" in url
        assert "a=nc,%2B15551234567" in url


def test_google_voice_url_custom_config() -> None:
    custom_cfg = {
        "google_voice": {
            "account_email": "custom@domain.com",
            "phone_number": "(909) 323-2647",
            "account_index": 1,
        }
    }
    with patch("cocli.core.config.get_campaign", return_value="testcamp"), patch(
        "cocli.core.config.load_campaign_config", return_value=custom_cfg
    ):
        url = google_voice_url("19093232647")
        assert "voice.google.com/u/1/calls?" in url
        assert "authuser=custom@domain.com" in url
        assert "a=nc,%2B19093232647" in url
