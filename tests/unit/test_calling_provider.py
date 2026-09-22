from __future__ import annotations

from unittest.mock import MagicMock, patch

from cocli.utils.calling_provider import (
    BrowserTabCallingProvider,
    GoogleVoiceEdgeAppProvider,
    QuoCallingProvider,
    TwilioBridgeCallingProvider,
    get_calling_provider,
    google_voice_config,
)


def test_google_voice_config_merges_global_then_campaign_override() -> None:
    with (
        patch(
            "cocli.core.config.load_global_config",
            return_value={
                "google_voice": {"edge_app_id": "abc123", "account_index": 0}
            },
        ),
        patch(
            "cocli.core.config.load_campaign_config",
            return_value={"google_voice": {"account_index": 1}},
        ),
    ):
        merged = google_voice_config("roadmap")

    assert merged == {"edge_app_id": "abc123", "account_index": 1}


def test_get_calling_provider_defaults_to_browser_tab_off_wsl() -> None:
    with (
        patch("cocli.core.config.get_campaign", return_value=None),
        patch("cocli.core.config.load_global_config", return_value={}),
        patch("cocli.utils.calling_provider.is_wsl", return_value=False),
        patch(
            "cocli.utils.calling_provider.find_browser_app_binary", return_value=None
        ),
        patch("sys.platform", "linux"),
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, BrowserTabCallingProvider)


def test_get_calling_provider_returns_browser_tab_when_configured() -> None:
    with (
        patch("cocli.core.config.get_campaign", return_value=None),
        patch(
            "cocli.core.config.load_global_config",
            return_value={"google_voice": {"provider": "browser_tab"}},
        ),
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, BrowserTabCallingProvider)


def test_get_calling_provider_uses_edge_app_on_wsl_even_without_app_id() -> None:
    with (
        patch("cocli.core.config.get_campaign", return_value=None),
        patch("cocli.core.config.load_global_config", return_value={}),
        patch("cocli.utils.calling_provider.is_wsl", return_value=True),
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, GoogleVoiceEdgeAppProvider)
    assert provider.edge_app_id is None


def test_get_calling_provider_uses_edge_app_when_configured_and_on_wsl() -> None:
    with (
        patch("cocli.core.config.get_campaign", return_value=None),
        patch(
            "cocli.core.config.load_global_config",
            return_value={
                "google_voice": {"edge_app_id": "bbcbahpbnakjldhdcgiblnjnfgaejidg"}
            },
        ),
        patch("cocli.utils.calling_provider.is_wsl", return_value=True),
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, GoogleVoiceEdgeAppProvider)
    assert provider.edge_app_id == "bbcbahpbnakjldhdcgiblnjnfgaejidg"


def test_get_calling_provider_ignores_app_id_off_wsl_when_no_browser() -> None:
    with (
        patch("cocli.core.config.get_campaign", return_value=None),
        patch(
            "cocli.core.config.load_global_config",
            return_value={"google_voice": {"edge_app_id": "abc123"}},
        ),
        patch("cocli.utils.calling_provider.is_wsl", return_value=False),
        patch(
            "cocli.utils.calling_provider.find_browser_app_binary", return_value=None
        ),
        patch("sys.platform", "linux"),
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, BrowserTabCallingProvider)


def test_get_calling_provider_returns_quo_provider() -> None:
    with (
        patch("cocli.core.config.get_campaign", return_value=None),
        patch(
            "cocli.core.config.load_global_config",
            return_value={"google_voice": {"provider": "quo"}},
        ),
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, QuoCallingProvider)


def test_google_voice_edge_app_provider_builds_expected_command() -> None:
    provider = GoogleVoiceEdgeAppProvider("bbcbahpbnakjldhdcgiblnjnfgaejidg")
    captured: dict[str, list[str]] = {}

    def fake_spawn(command: list[str]) -> bool:
        captured["command"] = command
        return True

    with (
        patch(
            "cocli.utils.calling_provider.find_msedge_proxy",
            return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe",
        ),
        patch("cocli.utils.calling_provider.spawn_detached", side_effect=fake_spawn),
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ),
        patch("cocli.core.config.get_campaign", return_value=None),
        patch("cocli.core.config.load_global_config", return_value={}),
    ):
        assert provider.dial("5551234567") is True

    command = captured["command"]
    assert (
        command[0]
        == "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe"
    )
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

    with (
        patch(
            "cocli.utils.calling_provider.find_msedge_proxy",
            return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe",
        ),
        patch("cocli.utils.calling_provider.spawn_detached", return_value=True),
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ) as fake_copy,
        patch("cocli.core.config.get_campaign", return_value=None),
        patch("cocli.core.config.load_global_config", return_value={}),
    ):
        assert provider.dial("5551234567") is True

    fake_copy.assert_called_once_with("+15551234567")


def test_google_voice_edge_app_provider_skips_clipboard_when_proxy_launch_fails() -> (
    None
):
    provider = GoogleVoiceEdgeAppProvider("bbcbahpbnakjldhdcgiblnjnfgaejidg")

    with (
        patch(
            "cocli.utils.calling_provider.find_msedge_proxy",
            return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe",
        ),
        patch("cocli.utils.calling_provider.spawn_detached", return_value=False),
        patch("cocli.utils.calling_provider.copy_to_windows_clipboard") as fake_copy,
        patch("cocli.utils.calling_provider.open_url", return_value=True),
        patch("cocli.core.config.get_campaign", return_value=None),
        patch("cocli.core.config.load_global_config", return_value={}),
    ):
        assert provider.dial("5551234567") is True

    fake_copy.assert_not_called()


def test_google_voice_edge_app_provider_falls_back_when_proxy_missing() -> None:
    provider = GoogleVoiceEdgeAppProvider("bbcbahpbnakjldhdcgiblnjnfgaejidg")

    with (
        patch("cocli.utils.calling_provider.find_msedge_proxy", return_value=None),
        patch(
            "cocli.utils.calling_provider.open_url", return_value=True
        ) as fake_open_url,
        patch("cocli.core.config.get_campaign", return_value=None),
        patch("cocli.core.config.load_global_config", return_value={}),
    ):
        assert provider.dial("5551234567") is True
        fake_open_url.assert_called_once()


def test_google_voice_falls_back_to_native_app_when_pwa_not_installed() -> None:
    provider = GoogleVoiceEdgeAppProvider("stale_app_id")
    captured: dict[str, list[str]] = {}

    def fake_spawn(command: list[str]) -> bool:
        captured["command"] = command
        return True

    with (
        patch("cocli.utils.calling_provider.is_pwa_installed", return_value=False),
        patch(
            "cocli.utils.calling_provider.discover_installed_voice_pwa",
            return_value=None,
        ),
        patch(
            "cocli.utils.calling_provider.find_browser_app_binary",
            return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        ),
        patch("cocli.utils.calling_provider.spawn_detached", side_effect=fake_spawn),
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ) as fake_copy,
        patch("cocli.core.config.get_campaign", return_value=None),
        patch("cocli.core.config.load_global_config", return_value={}),
    ):
        assert provider.dial("5551234567") is True

    command = captured["command"]
    assert (
        command[0] == "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
    )
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

    with (
        patch(
            "cocli.utils.calling_provider.discover_installed_voice_pwa",
            return_value={
                "app_id": "discovered_voice_id",
                "browser": "edge",
                "path": "/some/path",
            },
        ),
        patch(
            "cocli.utils.calling_provider.find_msedge_proxy",
            return_value="/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe",
        ),
        patch("cocli.utils.calling_provider.spawn_detached", side_effect=fake_spawn),
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ),
        patch("cocli.core.config.get_campaign", return_value=None),
        patch("cocli.core.config.load_global_config", return_value={}),
    ):
        assert provider.dial("5551234567") is True

    command = captured["command"]
    assert (
        command[0]
        == "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge_proxy.exe"
    )
    assert command[2] == "--app-id=discovered_voice_id"


def test_quo_calling_provider_dials_via_protocol() -> None:
    provider = QuoCallingProvider()

    with (
        patch("cocli.utils.calling_provider.open_url", return_value=True) as fake_open,
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ) as fake_copy,
    ):
        assert provider.dial("5551234567") is True

    fake_open.assert_called_once_with("openphone://call?number=+15551234567")
    fake_copy.assert_called_once_with("+15551234567")


def test_quo_calling_provider_web_mode() -> None:
    provider = QuoCallingProvider(use_web=True)

    with (
        patch("cocli.utils.calling_provider.open_url", return_value=True) as fake_open,
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ),
    ):
        assert provider.dial("5551234567") is True

    fake_open.assert_called_once_with(
        "https://my.openphone.com/call?number=+15551234567"
    )


def test_twilio_bridge_calling_provider_is_configured() -> None:
    unconfigured = TwilioBridgeCallingProvider(account_sid="AC123")
    assert unconfigured.is_configured() is False

    configured = TwilioBridgeCallingProvider(
        account_sid="AC123",
        auth_token="token456",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    assert configured.is_configured() is True


def test_twilio_bridge_calling_provider_unconfigured_fails_gracefully() -> None:
    provider = TwilioBridgeCallingProvider()
    with patch(
        "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
    ):
        assert provider.dial("5551234567") is False


def test_twilio_bridge_calling_provider_initiates_api_call() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="secret456",
        caller_id="+19093232647",
        my_phone="+19095551234",
        recording_callback_url="https://example.com/webhook/recording",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"sid": "CA999888777", "status": "queued"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.post", return_value=mock_resp) as fake_post,
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ) as fake_copy,
    ):
        assert provider.dial("5551234567") is True

    fake_copy.assert_called_once_with("+15551234567")
    fake_post.assert_called_once()
    args, kwargs = fake_post.call_args
    assert args[0] == "https://api.twilio.com/2010-04-01/Accounts/ACtest123/Calls.json"
    assert kwargs["auth"] == ("ACtest123", "secret456")
    data = kwargs["data"]
    assert data["To"] == "+19095551234"
    assert data["From"] == "+19093232647"
    assert "<Number>+15551234567</Number>" in data["Twiml"]
    assert 'callerId="+19093232647"' in data["Twiml"]
    assert 'record="record-from-answer"' in data["Twiml"]
    assert data["RecordingStatusCallback"] == "https://example.com/webhook/recording"


def test_get_calling_provider_returns_twilio() -> None:
    with (
        patch("cocli.core.config.get_campaign", return_value=None),
        patch(
            "cocli.core.config.load_global_config",
            return_value={
                "calling": {"provider": "twilio"},
                "twilio": {
                    "account_sid": "AC123",
                    "auth_token": "token456",
                    "caller_id": "+19093232647",
                    "my_phone": "+19095551234",
                },
            },
        ),
    ):
        provider = get_calling_provider(None)

    assert isinstance(provider, TwilioBridgeCallingProvider)
    assert provider.account_sid == "AC123"
    assert provider.caller_id == "+19093232647"


def test_twilio_bridge_calling_provider_resolves_op_token() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="op://Vault/Item/auth-token",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"sid": "CA111"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "cocli.utils.op_utils.get_op_secret", return_value="resolved_token_xyz"
        ) as fake_op,
        patch("requests.post", return_value=mock_resp) as fake_post,
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ),
    ):
        assert provider.dial("5551234567") is True

    fake_op.assert_called_once_with("op://Vault/Item/auth-token")
    args, kwargs = fake_post.call_args
    assert kwargs["auth"] == ("ACtest123", "resolved_token_xyz")


def test_twilio_bridge_calling_provider_get_balance_and_cache() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="secret456",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"balance": "14.50", "currency": "USD"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.get", return_value=mock_resp) as fake_get,
    ):
        bal, curr = provider.get_balance()
        assert bal == 14.50
        assert curr == "USD"
        assert fake_get.call_count == 1

        # Second call uses cache
        bal2, curr2 = provider.get_balance()
        assert bal2 == 14.50
        assert curr2 == "USD"
        assert fake_get.call_count == 1

        # Bypass cache calls API again
        bal3, curr3 = provider.get_balance(bypass_cache=True)
        assert bal3 == 14.50
        assert fake_get.call_count == 2


def test_twilio_bridge_calling_provider_is_low_balance() -> None:
    TwilioBridgeCallingProvider.clear_balance_cache()
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="secret456",
        caller_id="+19093232647",
        my_phone="+19095551234",
        low_balance_threshold=20.0,
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"balance": "9.79", "currency": "USD"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.get", return_value=mock_resp),
    ):
        is_low, bal, curr = provider.is_low_balance()
        assert is_low is True
        assert bal == 9.79
        assert curr == "USD"

        # With lower threshold, it's not low
        is_low_custom, _, _ = provider.is_low_balance(threshold=5.0)
        assert is_low_custom is False


def test_twilio_bridge_calling_provider_class_level_cache_shared() -> None:
    TwilioBridgeCallingProvider._cached_balance = None

    provider1 = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="secret456",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    provider2 = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="secret456",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"balance": "8.50", "currency": "USD"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.get", return_value=mock_resp) as fake_get,
    ):
        bal1, _ = provider1.get_balance()
        assert bal1 == 8.50
        assert fake_get.call_count == 1

        # provider2 accesses the shared class-level cache without network call
        bal2, _ = provider2.get_balance()
        assert bal2 == 8.50
        assert fake_get.call_count == 1


def test_twilio_bridge_calling_provider_tracks_last_error() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="secret456",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "code": 21608,
        "message": "Trial accounts cannot make calls to unverified numbers.",
    }

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.post", return_value=mock_resp),
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ),
    ):
        ok = provider.dial("5551234567")
        assert ok is False
        assert provider.last_error is not None
        assert (
            "Trial accounts cannot make calls to unverified numbers"
            in provider.last_error
        )


def test_get_cached_twilio_balance_warning() -> None:
    from cocli.utils.calling_provider import get_cached_twilio_balance_warning

    TwilioBridgeCallingProvider._cached_balance = (9.79, "USD", 9999999999.0)

    with (
        patch("cocli.core.config.get_campaign", return_value=None),
        patch(
            "cocli.core.config.load_global_config",
            return_value={"calling": {"provider": "twilio"}},
        ),
    ):
        warning = get_cached_twilio_balance_warning()
        assert warning is not None
        assert "$9.79" in warning

    # When provider is google_voice, no warning is returned
    with (
        patch("cocli.core.config.get_campaign", return_value=None),
        patch(
            "cocli.core.config.load_global_config",
            return_value={"calling": {"provider": "google_voice"}},
        ),
    ):
        assert get_cached_twilio_balance_warning() is None
