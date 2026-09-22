from __future__ import annotations

from unittest.mock import patch

from cocli.utils.calling_provider import (
    BrowserTabCallingProvider,
    GoogleVoiceEdgeAppProvider,
    QuoCallingProvider,
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


def test_get_calling_provider_defaults_to_browser_tab_off_wsl() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ), patch("cocli.utils.calling_provider.is_wsl", return_value=False), patch(
        "cocli.utils.calling_provider.find_browser_app_binary", return_value=None
    ), patch("sys.platform", "linux"):
        provider = get_calling_provider(None)

    assert isinstance(provider, BrowserTabCallingProvider)


def test_get_calling_provider_returns_browser_tab_when_configured() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config",
        return_value={"google_voice": {"provider": "browser_tab"}},
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, BrowserTabCallingProvider)


def test_get_calling_provider_uses_edge_app_on_wsl_even_without_app_id() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ), patch("cocli.utils.calling_provider.is_wsl", return_value=True):
        provider = get_calling_provider(None)

    assert isinstance(provider, GoogleVoiceEdgeAppProvider)
    assert provider.edge_app_id is None


def test_get_calling_provider_uses_edge_app_when_configured_and_on_wsl() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config",
        return_value={"google_voice": {"edge_app_id": "bbcbahpbnakjldhdcgiblnjnfgaejidg"}},
    ), patch("cocli.utils.calling_provider.is_wsl", return_value=True):
        provider = get_calling_provider(None)

    assert isinstance(provider, GoogleVoiceEdgeAppProvider)
    assert provider.edge_app_id == "bbcbahpbnakjldhdcgiblnjnfgaejidg"


def test_get_calling_provider_ignores_app_id_off_wsl_when_no_browser() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config",
        return_value={"google_voice": {"edge_app_id": "abc123"}},
    ), patch("cocli.utils.calling_provider.is_wsl", return_value=False), patch(
        "cocli.utils.calling_provider.find_browser_app_binary", return_value=None
    ), patch("sys.platform", "linux"):
        provider = get_calling_provider(None)

    assert isinstance(provider, BrowserTabCallingProvider)


def test_get_calling_provider_returns_quo_provider() -> None:
    with patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config",
        return_value={"google_voice": {"provider": "quo"}},
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, QuoCallingProvider)


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
        "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
    ), patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ):
        assert provider.dial("5551234567") is True

    command = captured["command"]
    assert command[0] == "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe"
    assert command[1] == "--profile-directory=Default"
    assert command[2] == "--app-id=bbcbahpbnakjldhdcgiblnjnfgaejidg"
    assert command[3] == "--app-launch-source=4"
    assert command[4].startswith("--app-launch-url-for-shortcuts-menu-item=")
    assert "voice.google.com" in command[4]
    assert "a=nc,%2B15551234567" in command[4]
    assert not any(part.startswith("--app-url=") for part in command)


def test_google_voice_edge_app_provider_copies_cleaned_number_to_clipboard() -> None:
    """Clipboard is a paste fallback if Voice doesn't auto-dial from the
    shortcuts-menu URL; still copy whenever the PWA launch succeeds."""
    provider = GoogleVoiceEdgeAppProvider("bbcbahpbnakjldhdcgiblnjnfgaejidg")

    with patch(
        "cocli.utils.calling_provider.find_msedge_proxy",
        return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe",
    ), patch("cocli.utils.calling_provider.spawn_detached", return_value=True), patch(
        "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
    ) as fake_copy, patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ):
        assert provider.dial("5551234567") is True

    fake_copy.assert_called_once_with("+15551234567")


def test_google_voice_edge_app_provider_skips_clipboard_when_proxy_launch_fails() -> None:
    provider = GoogleVoiceEdgeAppProvider("bbcbahpbnakjldhdcgiblnjnfgaejidg")

    with patch(
        "cocli.utils.calling_provider.find_msedge_proxy",
        return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe",
    ), patch("cocli.utils.calling_provider.spawn_detached", return_value=False), patch(
        "cocli.utils.calling_provider.copy_to_windows_clipboard"
    ) as fake_copy, patch("cocli.utils.calling_provider.open_url", return_value=True), patch(
        "cocli.core.config.get_campaign", return_value=None
    ), patch("cocli.core.config.load_global_config", return_value={}):
        assert provider.dial("5551234567") is True

    fake_copy.assert_not_called()


def test_google_voice_edge_app_provider_falls_back_when_proxy_missing() -> None:
    provider = GoogleVoiceEdgeAppProvider("bbcbahpbnakjldhdcgiblnjnfgaejidg")

    with patch("cocli.utils.calling_provider.find_msedge_proxy", return_value=None), patch(
        "cocli.utils.calling_provider.open_url", return_value=True
    ) as fake_open_url, patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ):
        assert provider.dial("5551234567") is True
        fake_open_url.assert_called_once()


def test_google_voice_falls_back_to_native_app_when_pwa_not_installed() -> None:
    provider = GoogleVoiceEdgeAppProvider("stale_app_id")
    captured: dict[str, list[str]] = {}

    def fake_spawn(command: list[str]) -> bool:
        captured["command"] = command
        return True

    with patch("cocli.utils.calling_provider.is_pwa_installed", return_value=False), patch(
        "cocli.utils.calling_provider.discover_installed_voice_pwa", return_value=None
    ), patch(
        "cocli.utils.calling_provider.find_browser_app_binary",
        return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ), patch("cocli.utils.calling_provider.spawn_detached", side_effect=fake_spawn), patch(
        "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
    ) as fake_copy, patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ):
        assert provider.dial("5551234567") is True

    command = captured["command"]
    assert command[0] == "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
    assert command[1] == "--profile-directory=Default"
    assert command[2].startswith("--app=https://voice.google.com")
    assert "a=nc,%2B15551234567" in command[2]
    fake_copy.assert_called_once_with("+15551234567")


def test_google_voice_auto_discovers_pwa_when_no_app_id_configured() -> None:
    provider = GoogleVoiceEdgeAppProvider(edge_app_id=None)
    captured: dict[str, list[str]] = {}

    def fake_spawn(command: list[str]) -> bool:
        captured["command"] = command
        return True

    with patch(
        "cocli.utils.calling_provider.discover_installed_voice_pwa",
        return_value={"app_id": "discovered_voice_id", "browser": "edge", "path": "/some/path"},
    ), patch(
        "cocli.utils.calling_provider.find_msedge_proxy",
        return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe",
    ), patch("cocli.utils.calling_provider.spawn_detached", side_effect=fake_spawn), patch(
        "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
    ), patch("cocli.core.config.get_campaign", return_value=None), patch(
        "cocli.core.config.load_global_config", return_value={}
    ):
        assert provider.dial("5551234567") is True

    command = captured["command"]
    assert command[0] == "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe"
    assert command[2] == "--app-id=discovered_voice_id"


def test_quo_calling_provider_dials_via_protocol() -> None:
    provider = QuoCallingProvider()

    with patch("cocli.utils.calling_provider.open_url", return_value=True) as fake_open, patch(
        "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
    ) as fake_copy:
        assert provider.dial("5551234567") is True

    fake_open.assert_called_once_with("openphone://call?number=+15551234567")
    fake_copy.assert_called_once_with("+15551234567")


def test_quo_calling_provider_web_mode() -> None:
    provider = QuoCallingProvider(use_web=True)

    with patch("cocli.utils.calling_provider.open_url", return_value=True) as fake_open, patch(
        "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
    ):
        assert provider.dial("5551234567") is True

    fake_open.assert_called_once_with("https://my.openphone.com/call?number=+15551234567")
