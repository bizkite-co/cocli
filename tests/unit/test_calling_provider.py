from __future__ import annotations

from unittest.mock import patch

from cocli.utils.calling_provider import (
    BrowserTabCallingProvider,
    GoogleVoiceEdgeAppProvider,
    get_calling_provider,
    google_voice_config,
)


def test_google_voice_config_merges_global_then_campaign_override() -> None:
    with patch(
        "cocli.core.config.load_global_config",
        return_value={"google_voice": {"edge_app_id": "abc123", "account_index": 0}},
    ), patch(
        "cocli.core.config.load_campaign_config",
        return_value={"google_voice": {"account_index": 1}},
    ):
        merged = google_voice_config("roadmap")

    assert merged == {"edge_app_id": "abc123", "account_index": 1}


def test_get_calling_provider_defaults_to_browser_tab_when_no_app_id() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, BrowserTabCallingProvider)


def test_get_calling_provider_uses_edge_app_when_configured_and_on_wsl() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config",
        return_value={"google_voice": {"edge_app_id": "bbcbahpbnakjldhdcgiblnjnfgaejidg"}},
    ), patch("cocli.utils.calling_provider.is_wsl", return_value=True):
        provider = get_calling_provider(None)

    assert isinstance(provider, GoogleVoiceEdgeAppProvider)
    assert provider.edge_app_id == "bbcbahpbnakjldhdcgiblnjnfgaejidg"


def test_get_calling_provider_ignores_app_id_off_wsl() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config",
        return_value={"google_voice": {"edge_app_id": "abc123"}},
    ), patch("cocli.utils.calling_provider.is_wsl", return_value=False):
        provider = get_calling_provider(None)

    assert isinstance(provider, BrowserTabCallingProvider)


def test_google_voice_edge_app_provider_builds_expected_command() -> None:
    provider = GoogleVoiceEdgeAppProvider("bbcbahpbnakjldhdcgiblnjnfgaejidg")
    captured: dict[str, list[str]] = {}

    def fake_spawn(command: list[str]) -> bool:
        captured["command"] = command
        return True

    with patch(
        "cocli.utils.calling_provider.find_msedge_proxy",
        return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe",
    ), patch("cocli.utils.calling_provider.spawn_detached", side_effect=fake_spawn), patch(
        "cocli.core.config.get_campaign", return_value=None
    ), patch("cocli.core.config.load_global_config", return_value={}):
        assert provider.dial("5551234567") is True

    command = captured["command"]
    assert command[0] == "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe"
    assert "--profile-directory=Default" in command
    assert "--app-id=bbcbahpbnakjldhdcgiblnjnfgaejidg" in command
    assert any(part.startswith("--app-url=") and "voice.google.com" in part for part in command)


def test_google_voice_edge_app_provider_falls_back_when_proxy_missing() -> None:
    provider = GoogleVoiceEdgeAppProvider("bbcbahpbnakjldhdcgiblnjnfgaejidg")

    with patch("cocli.utils.calling_provider.find_msedge_proxy", return_value=None), patch(
        "cocli.utils.calling_provider.open_url", return_value=True
    ) as fake_open_url, patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ):
        assert provider.dial("5551234567") is True
        fake_open_url.assert_called_once()
