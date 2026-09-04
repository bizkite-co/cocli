"""SES send + IMAP monitor. Not a mail client; notes are the CRM surface."""

from __future__ import annotations

import email
import imaplib
import json
import logging
from datetime import datetime, UTC
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Callable, Optional, Protocol

from cocli.application.mail_oauth import FileOAuthTokenStore, resolve_token_cache_path
from cocli.core.paths import paths
from cocli.models.companies.note import Note
from cocli.models.mail import (
    EmailSettings,
    MailMessage,
    PollMailResult,
    SendMailRequest,
    SendMailResult,
)

logger = logging.getLogger(__name__)

CompanyLookup = Callable[[str], Optional[str]]


class TokenProvider(Protocol):
    def get_access_token(self) -> str: ...


class SesSender(Protocol):
    def send_email(self, *, source: str, to_address: str, subject: str, body: str) -> str: ...


class Boto3SesSender:
    def __init__(
        self,
        region: str,
        profile: Optional[str] = None,
        configuration_set: Optional[str] = None,
    ) -> None:
        import boto3

        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self._client = session.client("ses", region_name=region)
        self._configuration_set = configuration_set
        self._reply_to: Optional[str] = None

    def send_email(self, *, source: str, to_address: str, subject: str, body: str) -> str:
        kwargs: dict[str, object] = {
            "Source": source,
            "Destination": {"ToAddresses": [to_address]},
            "Message": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        }
        if self._reply_to:
            kwargs["ReplyToAddresses"] = [self._reply_to]
        if self._configuration_set:
            kwargs["ConfigurationSetName"] = self._configuration_set
        resp = self._client.send_email(**kwargs)
        return str(resp.get("MessageId") or "")


class EmailService:
    def __init__(
        self,
        campaign_name: str,
        settings: EmailSettings,
        token_provider: Optional[TokenProvider] = None,
        ses_sender: Optional[SesSender] = None,
        company_lookup: Optional[CompanyLookup] = None,
        aws_profile: Optional[str] = None,
    ) -> None:
        self.campaign_name = campaign_name
        self.settings = settings
        self._token_provider = token_provider
        self._ses_sender = ses_sender
        self._company_lookup = company_lookup
        self._aws_profile = aws_profile

    def send(self, request: SendMailRequest) -> SendMailResult:
        source = request.from_address or self.settings.from_address
        if not source:
            raise ValueError("from_address is required (request or campaign [email].from_address)")
        sender = self._ses()
        ses_id = sender.send_email(
            source=source,
            to_address=request.to_address,
            subject=request.subject,
            body=request.body,
        )
        slug = request.company_slug or self._lookup(request.to_address)
        note_written = False
        if slug:
            msg = MailMessage(
                message_id=ses_id or f"ses-{datetime.now(UTC).timestamp()}",
                from_address=source,
                to_addresses=[request.to_address],
                subject=request.subject,
                date=datetime.now(UTC),
                body=request.body,
            )
            self._write_note(slug, msg, direction="sent")
            note_written = True
        return SendMailResult(
            message_id=ses_id,
            to_address=request.to_address,
            subject=request.subject,
            note_written=note_written,
            company_slug=slug,
        )

    def poll(self, *, limit: int = 50) -> PollMailResult:
        result = PollMailResult()
        seen = self._load_seen()
        token = self._token().get_access_token()
        user = self.settings.imap_user
        if not user:
            raise ValueError("campaign [email].imap_user is required to poll")
        imap = imaplib.IMAP4_SSL(self.settings.imap_host)
        try:
            auth = f"user={user}\1auth=Bearer {token}\1\1"
            imap.authenticate("XOAUTH2", lambda _: auth.encode("utf-8"))
            for folder in self.settings.folders:
                try:
                    typ, _ = imap.select(folder, readonly=True)
                except Exception as exc:
                    logger.warning("Could not select IMAP folder %s: %s", folder, exc)
                    continue
                if typ != "OK":
                    logger.warning("IMAP SELECT %s failed: %s", folder, typ)
                    continue
                typ, data = imap.search(None, *self._imap_search_criteria())
                if typ != "OK" or not data or not data[0]:
                    continue
                # Sequence numbers increase with arrival; newest first so a
                # just-sent round-trip is not buried under old UNSEEN mail.
                ids = list(reversed(data[0].split()))
                for msg_id in ids[:limit]:
                    result.fetched += 1
                    typ, fetched = imap.fetch(msg_id, "(RFC822)")
                    if typ != "OK" or not fetched or not fetched[0]:
                        continue
                    raw = fetched[0]
                    if not isinstance(raw, tuple) or len(raw) < 2:
                        continue
                    payload = raw[1]
                    if not isinstance(payload, (bytes, bytearray)):
                        continue
                    parsed = email.message_from_bytes(bytes(payload))
                    message = self._to_mail_message(parsed, folder)
                    if message.message_id in seen:
                        result.skipped_seen += 1
                        continue
                    counterparties = [message.from_address, *message.to_addresses]
                    slug = self._first_matching_company(counterparties)
                    seen.add(message.message_id)
                    if not slug:
                        result.unmatched += 1
                        continue
                    path = self._write_note(slug, message, direction="received")
                    result.noted += 1
                    result.notes.append(str(path))
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        self._save_seen(seen)
        return result

    def _ses(self) -> SesSender:
        if self._ses_sender is not None:
            return self._ses_sender
        sender = Boto3SesSender(
            self.settings.ses_region,
            profile=self._aws_profile,
            configuration_set=self.settings.ses_configuration_set,
        )
        sender._reply_to = self.settings.reply_to
        return sender

    def _token(self) -> TokenProvider:
        if self._token_provider is not None:
            return self._token_provider
        if not self.settings.client_id:
            raise ValueError("campaign [email].client_id is required to poll IMAP")
        return FileOAuthTokenStore(
            resolve_token_cache_path(self.settings),
            self.settings.client_id,
            self.settings.token_endpoint,
        )

    def _lookup(self, address: str) -> Optional[str]:
        addr = address.strip().lower()
        if self._company_lookup is not None:
            return self._company_lookup(addr)
        from cocli.core.email_index_manager import EmailIndexManager

        mgr = EmailIndexManager(self.campaign_name)
        domain = addr.split("@")[-1] if "@" in addr else addr
        shard = mgr.get_shard_id(domain)
        path = mgr.inbox_dir / shard / f"{addr}.usv"
        if not path.is_file():
            return None
        from cocli.models.campaigns.indexes.email import EmailEntry

        try:
            entry = EmailEntry.from_usv(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not parse email index %s: %s", path, exc)
            return None
        return entry.company_slug

    def _imap_search_criteria(self) -> tuple[str, ...]:
        """Prefer UNSEEN+FROM monitored addresses so a personal inbox is not fully scanned."""
        watched = [a.strip() for a in self.settings.monitored_addresses if a.strip()]
        if not watched:
            return ("UNSEEN",)
        if len(watched) == 1:
            return ("UNSEEN", "FROM", watched[0])
        # IMAP OR is prefix-binary: OR a OR b c
        expr = f'FROM "{watched[-1]}"'
        for addr in reversed(watched[:-1]):
            expr = f'OR FROM "{addr}" {expr}'
        return ("UNSEEN", expr)

    def _first_matching_company(self, addresses: list[str]) -> Optional[str]:
        cleaned = [_bare_address(a) for a in addresses if a]
        cleaned = [a for a in cleaned if a]
        watched = {a.strip().lower() for a in self.settings.monitored_addresses if a}
        if watched and not watched.intersection(cleaned):
            return None
        ours = (self.settings.imap_user or "").strip().lower()
        for addr in cleaned:
            if ours and addr == ours:
                continue
            slug = self._lookup(addr)
            if slug:
                return slug
        return None

    def _write_note(self, company_slug: str, message: MailMessage, *, direction: str) -> Path:
        notes_dir = paths.companies.entry(company_slug).path / "notes"
        title = f"Email {direction}: {message.subject or '(no subject)'}"
        when = message.date.isoformat() if message.date else ""
        content = (
            f"- Direction: {direction}\n"
            f"- From: {message.from_address}\n"
            f"- To: {', '.join(message.to_addresses)}\n"
            f"- Date: {when}\n"
            f"- Message-ID: {message.message_id}\n\n"
            f"{message.body.strip()}\n"
        )
        note = Note(title=title[:120], content=content)
        note.to_file(notes_dir)
        logger.info("Wrote %s mail note for %s (%s)", direction, company_slug, message.message_id)
        ts = note.timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
        slugified = note.title.lower().replace(" ", "-").replace("/", "-")
        return notes_dir / f"{ts}-{slugified}.md"

    def _seen_path(self) -> Path:
        p = paths.campaign(self.campaign_name).path / "indexes" / "mail-monitor" / "seen.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _load_seen(self) -> set[str]:
        path = self._seen_path()
        if not path.is_file():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ids = data.get("message_ids", [])
            return {str(i) for i in ids}
        except (OSError, json.JSONDecodeError, AttributeError):
            return set()

    def _save_seen(self, seen: set[str]) -> None:
        path = self._seen_path()
        path.write_text(json.dumps({"message_ids": sorted(seen)}, indent=2), encoding="utf-8")

    def _to_mail_message(self, parsed: Message, folder: str) -> MailMessage:
        message_id = str(parsed.get("Message-ID") or "").strip() or f"imap-{datetime.now(UTC).timestamp()}"
        from_addr = _bare_address(str(parsed.get("From") or ""))
        tos = [addr for _, addr in getaddresses(parsed.get_all("To", []))]
        subject = _decode_header_value(parsed.get("Subject"))
        date: Optional[datetime] = None
        raw_date = parsed.get("Date")
        if raw_date:
            try:
                date = parsedate_to_datetime(str(raw_date))
            except (TypeError, ValueError):
                date = None
        body = _extract_text_body(parsed)
        return MailMessage(
            message_id=message_id,
            from_address=from_addr,
            to_addresses=tos,
            subject=subject,
            date=date,
            body=body,
            folder=folder,
        )


def _decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _bare_address(value: str) -> str:
    addrs = [addr for _, addr in getaddresses([value])]
    if addrs and addrs[0]:
        return addrs[0].strip().lower()
    return value.strip().lower()


def _extract_text_body(parsed: Message) -> str:
    if parsed.is_multipart():
        for part in parsed.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp.lower():
                payload = part.get_payload(decode=True)
                if isinstance(payload, (bytes, bytearray)):
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    payload = parsed.get_payload(decode=True)
    if isinstance(payload, (bytes, bytearray)):
        charset = parsed.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    if isinstance(payload, str):
        return payload
    return ""
