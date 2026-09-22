from __future__ import annotations

import email as email_pkg
from email import policy as email_policy
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

from cocli.application.email_service import Boto3SesSender, EmailService
from cocli.application.mail_oauth import FileOAuthTokenStore, build_authorize_url
from cocli.core.paths import paths
from cocli.models.mail import EmailSettings, SendMailRequest


class FakeSes:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_email(
        self,
        *,
        source: str,
        to_address: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        cc_addresses: Optional[list[str]] = None,
        bcc_addresses: Optional[list[str]] = None,
    ) -> str:
        self.sent.append(
            {
                "source": source,
                "to": to_address,
                "subject": subject,
                "body": body,
                "html_body": html_body,
                "cc_addresses": cc_addresses,
                "bcc_addresses": bcc_addresses,
            }
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


def test_send_with_injected_sender_does_not_open_boto3_session(tmp_path: Path) -> None:
    """FakeSes tests must not hit boto3's default credential chain
    (1Password credential_process / Windows Hello)."""
    paths.root = tmp_path
    settings = EmailSettings(from_address="outreach@example.com")
    service = EmailService(
        "test-campaign",
        settings,
        ses_sender=FakeSes(),
        company_lookup=lambda addr: None,
    )
    with patch("boto3.Session") as session_ctor:
        service.send(
            SendMailRequest(
                to_address="bob@acme.test",
                subject="Hello",
                body="Body",
            )
        )
    session_ctor.assert_not_called()


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


def test_boto3_sender_cc_sets_header_and_extends_destinations(mocker) -> None:
    """A Cc header alone wouldn't actually deliver anything - SES reads
    Destinations, not the raw message's headers - so cc_addresses must
    land in both places (2026-09-17, Mark: cc mark@bizkite.net on a
    one-off follow-up send)."""
    mock_client = mocker.Mock()
    mock_client.send_raw_email.return_value = {"MessageId": "ses-raw-cc"}
    mocker.patch("boto3.Session").return_value.client.return_value = mock_client

    sender = Boto3SesSender("us-west-1")
    sender.send_email(
        source="mark@getretirementtaxanalyzer.com",
        to_address="bob@acme.test",
        subject="Hello",
        body="Body text.",
        cc_addresses=["mark@bizkite.net"],
    )

    call_kwargs = mock_client.send_raw_email.call_args.kwargs
    assert call_kwargs["Destinations"] == ["bob@acme.test", "mark@bizkite.net"]

    raw = call_kwargs["RawMessage"]["Data"]
    parsed = email_pkg.message_from_bytes(raw, policy=email_policy.default)
    assert parsed["Cc"] == "mark@bizkite.net"


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


def test_send_applies_bcc_from_settings(tmp_path: Path) -> None:
    paths.root = tmp_path
    ses = FakeSes()
    settings = EmailSettings(
        from_address="outreach@example.com",
        bcc_address="team@example.com",
        bcc_addresses=["audit@example.com"],
    )
    service = EmailService(
        "test-campaign",
        settings,
        ses_sender=ses,
        company_lookup=lambda addr: None,
    )
    service.send(
        SendMailRequest(
            to_address="bob@acme.test",
            subject="Hello",
            body="Body",
            bcc_addresses=["extra@example.com"],
        )
    )
    assert len(ses.sent) == 1
    sent_bcc = ses.sent[0]["bcc_addresses"]
    assert sent_bcc == ["extra@example.com", "team@example.com", "audit@example.com"]


def test_boto3_ses_sender_includes_bcc_in_destinations_not_headers(mocker) -> None:
    fake_client = mocker.MagicMock()
    fake_client.send_raw_email.return_value = {"MessageId": "ses-raw-123"}
    fake_session = mocker.MagicMock()
    fake_session.client.return_value = fake_client
    mocker.patch("boto3.Session", return_value=fake_session)

    sender = Boto3SesSender(region="us-west-1")
    sender.send_email(
        source="outreach@example.com",
        to_address="bob@acme.test",
        subject="Hello",
        body="Hello world",
        cc_addresses=["cc@example.com"],
        bcc_addresses=["bcc@example.com"],
    )
    fake_client.send_raw_email.assert_called_once()
    kwargs = fake_client.send_raw_email.call_args[1]
    assert kwargs["Destinations"] == ["bob@acme.test", "cc@example.com", "bcc@example.com"]

    raw_bytes = kwargs["RawMessage"]["Data"]
    parsed = email_pkg.message_from_bytes(raw_bytes, policy=email_policy.default)
    assert parsed["To"] == "bob@acme.test"
    assert parsed["Cc"] == "cc@example.com"
    assert parsed["Bcc"] is None


def test_m365_smtp_sender_message_formatting_and_headers(mocker) -> None:
    from cocli.application.email_service import M365SmtpSender

    mock_smtp = mocker.MagicMock()
    mock_smtp.__enter__.return_value = mock_smtp
    mock_smtp.docmd.return_value = (235, b"2.7.0 Authentication successful")
    mocker.patch("smtplib.SMTP", return_value=mock_smtp)

    sender = M365SmtpSender(
        host="smtp.office365.com",
        port=587,
        user="mark@getretirementtaxanalyzer.com",
        token_provider=FakeTokens(),
        reply_to="mark@getretirementtaxanalyzer.com",
    )

    msg_id = sender.send_email(
        source="mark@getretirementtaxanalyzer.com",
        to_address="bob@acme.test",
        subject="Roadmap Introduction",
        body="Plain text content.",
        html_body="<p>Rich <b>HTML</b> content.</p>",
        cc_addresses=["cc@example.com"],
        bcc_addresses=["bcc@example.com"],
    )

    assert msg_id
    mock_smtp.starttls.assert_called_once()
    mock_smtp.send_message.assert_called_once()

    call_args = mock_smtp.send_message.call_args
    sent_msg = call_args[0][0]
    from_addr = call_args[1]["from_addr"]
    to_addrs = call_args[1]["to_addrs"]

    assert from_addr == "mark@getretirementtaxanalyzer.com"
    assert to_addrs == ["bob@acme.test", "cc@example.com", "bcc@example.com"]
    assert sent_msg["From"] == "mark@getretirementtaxanalyzer.com"
    assert sent_msg["To"] == "bob@acme.test"
    assert sent_msg["Cc"] == "cc@example.com"
    assert sent_msg["Bcc"] is None  # Bcc must NOT be exposed in headers
    assert sent_msg["Reply-To"] == "mark@getretirementtaxanalyzer.com"
    assert "<mailto:mark@getretirementtaxanalyzer.com?subject=unsubscribe>" in sent_msg["List-Unsubscribe"]
    assert sent_msg.is_multipart()


def test_m365_smtp_sender_xoauth2_auth_command(mocker) -> None:
    import base64
    from cocli.application.email_service import M365SmtpSender

    mock_smtp = mocker.MagicMock()
    mock_smtp.__enter__.return_value = mock_smtp
    mock_smtp.docmd.return_value = (235, b"2.7.0 Authentication successful")
    mocker.patch("smtplib.SMTP", return_value=mock_smtp)

    sender = M365SmtpSender(
        user="mark@getretirementtaxanalyzer.com",
        token_provider=FakeTokens(),
    )

    sender.send_email(
        source="mark@getretirementtaxanalyzer.com",
        to_address="bob@acme.test",
        subject="Hello",
        body="Test",
    )

    # Verify docmd was called with AUTH XOAUTH2
    auth_calls = [c for c in mock_smtp.docmd.call_args_list if c[0][0] == "AUTH"]
    assert len(auth_calls) == 1
    auth_cmd = auth_calls[0][0][1]
    assert auth_cmd.startswith("XOAUTH2 ")
    b64_payload = auth_cmd[len("XOAUTH2 "):]
    decoded = base64.b64decode(b64_payload).decode("utf-8")
    assert "user=mark@getretirementtaxanalyzer.com\x01auth=Bearer tok\x01\x01" == decoded


def test_m365_smtp_sender_xoauth2_failure_raises_error(mocker) -> None:
    import base64
    import smtplib
    import pytest
    from cocli.application.email_service import M365SmtpSender

    mock_smtp = mocker.MagicMock()
    mock_smtp.__enter__.return_value = mock_smtp
    # Return 334 error challenge from Exchange Online
    err_json = base64.b64encode(b'{"status":"401","error":"invalid_token"}')
    mock_smtp.docmd.return_value = (334, err_json)
    mocker.patch("smtplib.SMTP", return_value=mock_smtp)

    sender = M365SmtpSender(
        user="mark@getretirementtaxanalyzer.com",
        token_provider=FakeTokens(),
    )

    with pytest.raises(smtplib.SMTPAuthenticationError) as exc_info:
        sender.send_email(
            source="mark@getretirementtaxanalyzer.com",
            to_address="bob@acme.test",
            subject="Hello",
            body="Test",
        )
    assert "XOAUTH2 authentication failed" in str(exc_info.value)
    assert "invalid_token" in str(exc_info.value)


def test_m365_smtp_sender_password_login(mocker) -> None:
    from cocli.application.email_service import M365SmtpSender

    mock_smtp = mocker.MagicMock()
    mock_smtp.__enter__.return_value = mock_smtp
    mocker.patch("smtplib.SMTP", return_value=mock_smtp)

    sender = M365SmtpSender(
        user="mark@getretirementtaxanalyzer.com",
        password="secret-password",
        auth_type="login",
    )

    sender.send_email(
        source="mark@getretirementtaxanalyzer.com",
        to_address="bob@acme.test",
        subject="Hello",
        body="Test",
    )

    mock_smtp.login.assert_called_once_with("mark@getretirementtaxanalyzer.com", "secret-password")


def test_m365_graph_sender_send(mocker) -> None:
    import json
    from cocli.application.email_service import M365GraphSender

    mock_resp = mocker.MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.headers.get.side_effect = lambda k, default=None: (
        "test-req-123" if k == "client-request-id" else default
    )
    mock_urlopen = mocker.patch("urllib.request.urlopen", return_value=mock_resp)

    sender = M365GraphSender(
        token_provider=FakeTokens(),
        user_id="mark@getretirementtaxanalyzer.com",
        reply_to="reply@example.com",
    )

    result_id = sender.send_email(
        source="mark@getretirementtaxanalyzer.com",
        to_address="bob@acme.test",
        subject="Graph Test",
        body="Plain text",
        html_body="<p>HTML</p>",
        cc_addresses=["cc@example.com"],
        bcc_addresses=["bcc@example.com"],
    )

    assert result_id == "test-req-123"
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "https://graph.microsoft.com/v1.0/users/mark%40getretirementtaxanalyzer.com/sendMail"
    assert req.headers["Authorization"] == "Bearer tok"

    payload = json.loads(req.data.decode("utf-8"))
    assert payload["message"]["subject"] == "Graph Test"
    assert payload["message"]["body"]["contentType"] == "HTML"
    assert payload["message"]["toRecipients"] == [{"emailAddress": {"address": "bob@acme.test"}}]
    assert payload["message"]["ccRecipients"] == [{"emailAddress": {"address": "cc@example.com"}}]
    assert payload["message"]["bccRecipients"] == [{"emailAddress": {"address": "bcc@example.com"}}]
    assert payload["message"]["replyTo"] == [{"emailAddress": {"address": "reply@example.com"}}]


def test_email_service_backend_selection(mocker) -> None:
    from cocli.application.email_service import Boto3SesSender, EmailService, M365GraphSender, M365SmtpSender

    # SES backend
    ses_settings = EmailSettings(backend="ses", from_address="outreach@example.com")
    service_ses = EmailService("campaign", ses_settings)
    assert isinstance(service_ses._get_sender(), Boto3SesSender)

    # M365 default backend -> M365SmtpSender
    m365_settings = EmailSettings(
        backend="m365",
        imap_user="mark@getretirementtaxanalyzer.com",
        client_id="cid",
        from_address="mark@getretirementtaxanalyzer.com",
    )
    service_m365 = EmailService("campaign", m365_settings, token_provider=FakeTokens())
    assert isinstance(service_m365._get_sender(), M365SmtpSender)

    # M365 Graph backend
    graph_settings = EmailSettings(
        backend="m365_graph",
        imap_user="mark@getretirementtaxanalyzer.com",
        client_id="cid",
        from_address="mark@getretirementtaxanalyzer.com",
    )
    service_graph = EmailService("campaign", graph_settings, token_provider=FakeTokens())
    assert isinstance(service_graph._get_sender(), M365GraphSender)


def test_send_with_m365_writes_note_without_touching_ses_suppression(tmp_path: Path, mocker) -> None:
    paths.root = tmp_path
    company_dir = paths.companies.entry("acme", ensure=True).path
    (company_dir / "notes").mkdir(parents=True, exist_ok=True)

    fake_sender = mocker.MagicMock()
    fake_sender.send_email.return_value = "m365-msg-id"

    mocker.patch("cocli.application.email_service.EmailService._get_sender", return_value=fake_sender)
    suppress_mock = mocker.patch("cocli.application.ses_suppression_service.SesSuppressionService")

    settings = EmailSettings(backend="m365", from_address="mark@getretirementtaxanalyzer.com")
    service = EmailService(
        "test-campaign",
        settings,
        company_lookup=lambda addr: "acme" if addr == "bob@acme.test" else None,
    )

    result = service.send(
        SendMailRequest(
            to_address="bob@acme.test",
            subject="Hello from M365",
            body="Checking in.",
        )
    )

    assert result.message_id == "m365-msg-id"
    assert result.note_written is True
    assert result.company_slug == "acme"
    suppress_mock.assert_not_called()  # AWS SES suppression check bypassed for M365
    notes = list((company_dir / "notes").glob("*.md"))
    assert len(notes) == 1
    assert "Checking in." in notes[0].read_text()


