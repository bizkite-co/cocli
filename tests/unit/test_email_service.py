from __future__ import annotations

import email as email_pkg
from email import policy as email_policy
from email.message import EmailMessage
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from cocli.application.email_service import Boto3SesSender, EmailService
from cocli.application.mail_oauth import FileOAuthTokenStore, build_authorize_url
from cocli.core.paths import paths
from cocli.models.mail import EmailSettings, SendMailRequest


class FakeSes:
    def __init__(self) -> None:
        self.sent: list[dict[str, Optional[str]]] = []

    def send_email(
        self,
        *,
        source: str,
        to_address: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> str:
        self.sent.append(
            {"source": source, "to": to_address, "subject": subject, "body": body, "html_body": html_body}
        )
        return "ses-msg-1"


class FakeTokens:
    def get_access_token(self) -> str:
        return "tok"


def test_send_writes_company_note(tmp_path: Path) -> None:
    paths.root = tmp_path
    company_dir = paths.companies.entry("acme", ensure=True).path
    (company_dir / "notes").mkdir(parents=True, exist_ok=True)

    ses = FakeSes()
    settings = EmailSettings(from_address="outreach@example.com")
    service = EmailService(
        "test-campaign",
        settings,
        ses_sender=ses,
        company_lookup=lambda addr: "acme" if addr == "bob@acme.test" else None,
    )
    result = service.send(
        SendMailRequest(
            to_address="bob@acme.test",
            subject="Hello",
            body="We would like to talk.",
        )
    )
    assert result.message_id == "ses-msg-1"
    assert result.note_written is True
    assert result.company_slug == "acme"
    assert ses.sent[0]["to"] == "bob@acme.test"
    notes = list((company_dir / "notes").glob("*.md"))
    assert len(notes) == 1
    text = notes[0].read_text()
    assert "We would like to talk." in text
    assert "bob@acme.test" in text


def test_ses_sender_constructed_once_and_cached(mocker) -> None:
    """A batch of N sends must trigger one 1Password/AWS credential
    resolution, not N - Boto3SesSender.__init__ calls boto3.Session(...),
    so _ses() must cache the sender instead of rebuilding it per send."""
    from cocli.application import email_service as email_service_mod

    mock_sender = mocker.Mock()
    mock_sender.send_email.return_value = "ses-msg-1"
    mock_ctor = mocker.patch.object(
        email_service_mod, "Boto3SesSender", return_value=mock_sender
    )

    settings = EmailSettings(from_address="outreach@example.com")
    service = EmailService(
        "test-campaign", settings, company_lookup=lambda addr: None
    )

    service._ses()
    service._ses()
    service._ses()

    mock_ctor.assert_called_once()


def test_boto3_sender_sets_list_unsubscribe_header_via_raw_send(mocker) -> None:
    """Gmail/Yahoo bulk-sender rules expect List-Unsubscribe; the simple
    send_email API has no header support, so this must go via
    send_raw_email - assert on the actual decoded header, not just that
    send_raw_email was called."""
    mock_client = mocker.Mock()
    mock_client.send_raw_email.return_value = {"MessageId": "ses-raw-1"}
    mocker.patch("boto3.Session").return_value.client.return_value = mock_client

    sender = Boto3SesSender("us-west-1", configuration_set="prs-default")
    sender._reply_to = "mark@getretirementtaxanalyzer.com"

    message_id = sender.send_email(
        source="mark@getretirementtaxanalyzer.com",
        to_address="bob@acme.test",
        subject="Hello",
        body="We would like to talk.",
    )

    assert message_id == "ses-raw-1"
    mock_client.send_raw_email.assert_called_once()
    call_kwargs = mock_client.send_raw_email.call_args.kwargs
    assert call_kwargs["Source"] == "mark@getretirementtaxanalyzer.com"
    assert call_kwargs["Destinations"] == ["bob@acme.test"]
    assert call_kwargs["ConfigurationSetName"] == "prs-default"

    raw = call_kwargs["RawMessage"]["Data"]
    parsed = email_pkg.message_from_bytes(raw, policy=email_policy.default)
    assert parsed["List-Unsubscribe"] == "<mailto:mark@getretirementtaxanalyzer.com?subject=unsubscribe>"
    assert parsed["Reply-To"] == "mark@getretirementtaxanalyzer.com"
    assert parsed["Subject"] == "Hello"
    assert parsed.get_content().strip() == "We would like to talk."


def test_boto3_sender_sends_multipart_alternative_when_html_body_given(mocker) -> None:
    mock_client = mocker.Mock()
    mock_client.send_raw_email.return_value = {"MessageId": "ses-raw-html"}
    mocker.patch("boto3.Session").return_value.client.return_value = mock_client

    sender = Boto3SesSender("us-west-1")
    message_id = sender.send_email(
        source="mark@getretirementtaxanalyzer.com",
        to_address="bob@acme.test",
        subject="Hello",
        body="Plain fallback text.",
        html_body="<p>Rich <b>HTML</b> body.</p>",
    )

    assert message_id == "ses-raw-html"
    raw = mock_client.send_raw_email.call_args.kwargs["RawMessage"]["Data"]
    parsed = email_pkg.message_from_bytes(raw, policy=email_policy.default)
    assert parsed.is_multipart()
    text_part = parsed.get_body(preferencelist=("plain",))
    html_part = parsed.get_body(preferencelist=("html",))
    assert text_part is not None and "Plain fallback text." in text_part.get_content()
    assert html_part is not None and "<b>HTML</b>" in html_part.get_content()


def test_boto3_sender_omits_html_part_when_not_given(mocker) -> None:
    mock_client = mocker.Mock()
    mock_client.send_raw_email.return_value = {"MessageId": "ses-raw-text-only"}
    mocker.patch("boto3.Session").return_value.client.return_value = mock_client

    sender = Boto3SesSender("us-west-1")
    sender.send_email(
        source="mark@getretirementtaxanalyzer.com",
        to_address="bob@acme.test",
        subject="Hello",
        body="Just text.",
    )

    raw = mock_client.send_raw_email.call_args.kwargs["RawMessage"]["Data"]
    parsed = email_pkg.message_from_bytes(raw, policy=email_policy.default)
    assert not parsed.is_multipart()


def test_boto3_sender_list_unsubscribe_falls_back_to_source_without_reply_to(mocker) -> None:
    mock_client = mocker.Mock()
    mock_client.send_raw_email.return_value = {"MessageId": "ses-raw-2"}
    mocker.patch("boto3.Session").return_value.client.return_value = mock_client

    sender = Boto3SesSender("us-west-1")

    sender.send_email(
        source="outreach@example.com",
        to_address="bob@acme.test",
        subject="Hi",
        body="Body",
    )

    raw = mock_client.send_raw_email.call_args.kwargs["RawMessage"]["Data"]
    parsed = email_pkg.message_from_bytes(raw, policy=email_policy.default)
    assert parsed["List-Unsubscribe"] == "<mailto:outreach@example.com?subject=unsubscribe>"
    assert parsed["Reply-To"] is None


def test_build_authorize_url_includes_client_and_login_hint() -> None:
    settings = EmailSettings(client_id="abc-123", imap_user="mark@example.com")
    url = build_authorize_url(settings)
    assert "abc-123" in url
    assert "mark%40example.com" in url or "mark@example.com" in url
    assert "response_type=code" in url


def test_file_token_store_uses_unexpired_cache(tmp_path: Path) -> None:
    cache = tmp_path / "token.json"
    cache.write_text(
        '{"access_token":"abc","refresh_token":"r","access_token_expiration":"2099-01-01T00:00:00"}',
        encoding="utf-8",
    )
    store = FileOAuthTokenStore(cache, "client", "https://example.test/token")
    assert store.get_access_token() == "abc"


def test_poll_notes_unseen_matching_from(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    paths.root = tmp_path
    company_dir = paths.companies.entry("acme", ensure=True).path
    (company_dir / "notes").mkdir(parents=True, exist_ok=True)

    msg = EmailMessage()
    msg["From"] = "Bob <bob@acme.test>"
    msg["To"] = "mark@bizkite.co"
    msg["Subject"] = "Quote"
    msg["Message-ID"] = "<id-1@acme.test>"
    msg.set_content("Please send a quote.")

    class FakeImap:
        def __init__(self, _host: str) -> None:
            pass

        def authenticate(self, _mech: str, _cb: object) -> None:
            return None

        def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
            assert folder == "INBOX"
            return "OK", [b"1"]

        def search(self, _charset: object, _crit: str) -> tuple[str, list[bytes]]:
            return "OK", [b"1 2"]

        def fetch(self, mid: bytes, _spec: str) -> tuple[str, list[tuple[bytes, bytes]]]:
            if mid == b"1":
                other = EmailMessage()
                other["From"] = "unrelated@example.com"
                other["To"] = "mark@bizkite.co"
                other["Subject"] = "old"
                other["Message-ID"] = "<old@example.com>"
                other.set_content("nope")
                return "OK", [(b"1", other.as_bytes())]
            return "OK", [(mid, msg.as_bytes())]

        def logout(self) -> None:
            return None

    monkeypatch.setattr("cocli.application.email_service.imaplib.IMAP4_SSL", FakeImap)

    settings = EmailSettings(
        from_address="outreach@example.com",
        imap_user="mark@bizkite.co",
        folders=["INBOX"],
    )
    service = EmailService(
        "test-campaign",
        settings,
        token_provider=FakeTokens(),
        company_lookup=lambda addr: "acme" if addr == "bob@acme.test" else None,
    )
    with patch("cocli.utils.alert_utils.send_alert", return_value=True) as alert:
        result = service.poll(limit=10)
    assert result.fetched == 2
    assert result.noted == 1
    assert result.unmatched == 1
    alert.assert_called_once()
    assert "1 new email" in str(alert.call_args.args[0])
    notes = list((company_dir / "notes").glob("*.md"))
    assert len(notes) == 1
    assert "Quote" in notes[0].read_text()

    # Second poll: same Message-IDs are recorded as seen even if IMAP still returns UNSEEN
    with patch("cocli.utils.alert_utils.send_alert") as alert2:
        result2 = service.poll(limit=10)
    assert result2.skipped_seen == 2
    assert result2.noted == 0
    alert2.assert_not_called()
