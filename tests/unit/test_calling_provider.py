from __future__ import annotations

from typing import Any
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
        patch("cocli.utils.op_utils.read_op_secrets", return_value=None),
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


def test_twilio_fetch_messages() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="AC1234567890",
        auth_token="dummy-auth-token",
        caller_id="+17144514350",
        my_phone="+17144967059",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "messages": [
            {
                "sid": "SM123",
                "from": "+19495551234",
                "to": "+17144514350",
                "body": "Hello!",
            }
        ]
    }

    with (
        patch.dict("os.environ", {}, clear=False),
        patch("requests.get", return_value=mock_resp) as mock_get,
    ):
        # Remove PYTEST_CURRENT_TEST temporarily to exercise the real requests path
        with patch.dict("os.environ", {"PYTEST_CURRENT_TEST": ""}):
            messages = provider.fetch_messages(limit=25)
            assert len(messages) == 1
            assert messages[0]["sid"] == "SM123"
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            assert "Messages.json" in args[0]
            assert kwargs["params"]["PageSize"] == 25
            assert kwargs["params"]["To"] == "+17144514350"


def test_twilio_bridge_calling_provider_with_api_key_and_secret() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        api_key="SKtest456",
        api_secret="secret789",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    assert provider.is_configured() is True

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"sid": "CA12345"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.post", return_value=mock_resp) as mock_post,
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ),
    ):
        assert provider.dial("5551234567") is True

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.twilio.com/2010-04-01/Accounts/ACtest123/Calls.json"
    assert kwargs["auth"] == ("SKtest456", "secret789")


def test_twilio_bridge_calling_provider_batch_resolves_op_secrets() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="op://Vault/Twilio/auth-token",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"sid": "CA999"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "cocli.utils.op_utils.read_op_secrets",
            return_value=["batch_resolved_token"],
        ) as mock_batch,
        patch("requests.post", return_value=mock_resp) as mock_post,
        patch(
            "cocli.utils.calling_provider.copy_to_windows_clipboard", return_value=True
        ),
    ):
        assert provider.dial("5551234567") is True

    mock_batch.assert_called_once_with("op://Vault/Twilio/auth-token")
    args, kwargs = mock_post.call_args
    assert kwargs["auth"] == ("ACtest123", "batch_resolved_token")


def test_twilio_bridge_get_account_info() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="auth_tok_secret",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "friendly_name": "My Biz Account",
        "type": "Full",
        "status": "active",
        "sid": "ACtest123",
    }

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.get", return_value=mock_resp) as mock_get,
    ):
        info = provider.get_account_info()

    assert info is not None
    assert info["friendly_name"] == "My Biz Account"
    assert info["type"] == "Full"
    assert info["status"] == "active"
    mock_get.assert_called_once()
    assert (
        mock_get.call_args[0][0]
        == "https://api.twilio.com/2010-04-01/Accounts/ACtest123.json"
    )


def test_twilio_bridge_get_incoming_phone_number() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="auth_tok_secret",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "incoming_phone_numbers": [
            {
                "sid": "PN111222333",
                "phone_number": "+19093232647",
                "friendly_name": "Main Office",
                "sms_url": "https://handler.twilio.com/twiml/EHtest",
                "sms_method": "POST",
                "voice_url": "",
                "capabilities": {"sms": True, "voice": True},
            }
        ]
    }

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.get", return_value=mock_resp) as mock_get,
    ):
        num_info = provider.get_incoming_phone_number()

    assert num_info is not None
    assert num_info["sid"] == "PN111222333"
    assert num_info["sms_url"] == "https://handler.twilio.com/twiml/EHtest"
    assert num_info["capabilities"] == {"sms": True, "voice": True}
    mock_get.assert_called_once()
    assert (
        "IncomingPhoneNumbers.json"
        in mock_get.call_args[0][0]
    )


def test_twilio_bridge_update_incoming_phone_number_sms_url() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="auth_tok_secret",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {
        "incoming_phone_numbers": [
            {
                "sid": "PN111222333",
                "phone_number": "+19093232647",
                "sms_url": "https://old.url",
            }
        ]
    }
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {"sid": "PN111222333"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.get", return_value=mock_get_resp),
        patch("requests.post", return_value=mock_post_resp) as mock_post,
    ):
        ok, sid = provider.update_incoming_phone_number_sms_url(
            "https://handler.twilio.com/twiml/EHnew"
        )

    assert ok is True
    assert sid == "PN111222333"
    mock_post.assert_called_once()
    assert (
        mock_post.call_args[0][0]
        == "https://api.twilio.com/2010-04-01/Accounts/ACtest123/IncomingPhoneNumbers/PN111222333.json"
    )
    assert mock_post.call_args[1]["data"]["SmsUrl"] == "https://handler.twilio.com/twiml/EHnew"


def test_twilio_bridge_test_voice_call_success() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="auth_tok_secret",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"sid": "CA111222333"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.post", return_value=mock_resp) as mock_post,
    ):
        ok, sid = provider.test_voice_call("+19095551234")

    assert ok is True
    assert sid == "CA111222333"
    mock_post.assert_called_once()
    assert "Calls.json" in mock_post.call_args[0][0]
    data = mock_post.call_args[1]["data"]
    assert data["To"] == "+19095551234"
    assert data["From"] == "+19093232647"
    assert "<Say" in data["Twiml"]


def test_twilio_bridge_test_voice_call_error() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="auth_tok_secret",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "code": 21216,
        "message": "Account not allowed to call +19095551234",
    }

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.post", return_value=mock_resp),
    ):
        ok, err = provider.test_voice_call("+19095551234")

    assert ok is False
    assert err is not None
    assert "21216" in err
    assert "Account not allowed to call" in err


def test_twilio_bridge_send_sms_success() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="auth_tok_secret",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"sid": "SM111222333"}

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.post", return_value=mock_resp) as mock_post,
    ):
        ok, sid = provider.send_sms(to_phone="+19095551234", body="Hello test")

    assert ok is True
    assert sid == "SM111222333"
    mock_post.assert_called_once()
    assert "Messages.json" in mock_post.call_args[0][0]
    data = mock_post.call_args[1]["data"]
    assert data["To"] == "+19095551234"
    assert data["From"] == "+19093232647"
    assert data["Body"] == "Hello test"


def test_twilio_bridge_get_trusthub_status() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="auth_tok_secret",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "sid": "BU111222333",
                "friendly_name": "My Customer Profile",
                "status": "twilio-approved",
                "policy_sid": "RN111222333",
            }
        ]
    }
    mock_policy_resp = MagicMock()
    mock_policy_resp.status_code = 200
    mock_policy_resp.json.return_value = {
        "friendly_name": "Primary customer profile for individual"
    }

    def mock_get(url: str, **kwargs: Any) -> MagicMock:
        if "Policies" in url:
            return mock_policy_resp
        return mock_resp

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.get", side_effect=mock_get),
    ):
        status = provider.get_trusthub_status()

    assert status is not None
    assert status["sid"] == "BU111222333"
    assert status["friendly_name"] == "My Customer Profile"
    assert status["status"] == "twilio-approved"
    assert "individual" in status["policy_name"].lower()


def test_twilio_bridge_get_dialing_permissions() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="auth_tok_secret",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "iso_code": "US",
        "name": "United States/Canada",
        "low_risk_numbers_enabled": True,
        "high_risk_special_numbers_enabled": False,
        "high_risk_tollfraud_numbers_enabled": False,
    }

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("requests.get", return_value=mock_resp) as mock_get,
    ):
        perms = provider.get_dialing_permissions("US")

    assert perms is not None
    assert perms["iso_code"] == "US"
    assert perms["low_risk_numbers_enabled"] is True
    assert perms["high_risk_special_numbers_enabled"] is False
    assert "Countries/US" in mock_get.call_args[0][0]


def test_twilio_bridge_low_balance_threshold_default() -> None:
    provider = TwilioBridgeCallingProvider(
        account_sid="ACtest123",
        auth_token="auth_tok_secret",
        caller_id="+19093232647",
        my_phone="+19095551234",
    )
    assert provider.low_balance_threshold == 5.0



