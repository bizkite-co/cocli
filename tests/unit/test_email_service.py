from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from cocli.application.email_service import EmailService, FileOAuthTokenStore
from cocli.core.paths import paths
from cocli.models.mail import EmailSettings, SendMailRequest


class FakeSes:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send_email(self, *, source: str, to_address: str, subject: str, body: str) -> str:
        self.sent.append(
            {"source": source, "to": to_address, "subject": subject, "body": body}
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
    result = service.poll(limit=10)
    assert result.fetched == 2
    assert result.noted == 1
    assert result.unmatched == 1
    notes = list((company_dir / "notes").glob("*.md"))
    assert len(notes) == 1
    assert "Quote" in notes[0].read_text()

    # Second poll: same Message-IDs are recorded as seen even if IMAP still returns UNSEEN
    result2 = service.poll(limit=10)
    assert result2.skipped_seen == 2
    assert result2.noted == 0
