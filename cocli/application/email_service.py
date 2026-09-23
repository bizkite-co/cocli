"""SES send + IMAP monitor. Not a mail client; notes are the CRM surface."""

from __future__ import annotations

import base64
import email
import imaplib
import json
import logging
import os
import smtplib
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, UTC, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import formatdate, getaddresses, make_msgid, parsedate_to_datetime
from pathlib import Path
from typing import Callable, Optional, Protocol, Literal, Any

from cocli.application.mail_oauth import FileOAuthTokenStore, resolve_token_cache_path
from cocli.core.paths import paths
from cocli.models.companies.email_note import EmailNote, CompanyEmail
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


class MailSender(Protocol):
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
    ) -> str: ...


# Backward-compatibility alias
SesSender = MailSender


class M365SmtpSender:
    """Authenticated SMTP sender for Microsoft 365 Exchange Online (smtp.office365.com).

    Supports XOAUTH2 (via TokenProvider, using the campaign's OAuth cache) or standard
    SMTP AUTH password.
    """

    def __init__(
        self,
        host: str = "smtp.office365.com",
        port: int = 587,
        user: Optional[str] = None,
        token_provider: Optional[TokenProvider] = None,
        password: Optional[str] = None,
        auth_type: Literal["auto", "xoauth2", "login"] = "auto",
        reply_to: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.token_provider = token_provider
        self.password = password
        self.auth_type = auth_type
        self._reply_to = reply_to
        self.timeout = timeout

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
        msg = EmailMessage()
        msg["From"] = source
        msg["To"] = to_address
        if cc_addresses:
            msg["Cc"] = ", ".join(cc_addresses)
        msg["Subject"] = subject
        if self._reply_to:
            msg["Reply-To"] = self._reply_to
        unsubscribe_address = self._reply_to or source
        msg["List-Unsubscribe"] = f"<mailto:{unsubscribe_address}?subject=unsubscribe>"

        domain = source.split("@")[-1] if "@" in source else "office365.com"
        msg_id = make_msgid(domain=domain)
        msg["Message-ID"] = msg_id
        msg["Date"] = formatdate(localtime=True)

        msg.set_content(body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")

        destinations = [to_address] + list(cc_addresses or []) + list(bcc_addresses or [])

        with self._connect_smtp() as smtp:
            self._authenticate(smtp, source)
            smtp.send_message(msg, from_addr=source, to_addrs=destinations)

        return msg_id.strip("<>")

    def _connect_smtp(self) -> smtplib.SMTP:
        if self.port == 465:
            ssl_smtp = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            ssl_smtp.ehlo()
            return ssl_smtp
        smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        smtp.ehlo()
        if smtp.has_extn("STARTTLS"):
            smtp.starttls()
            smtp.ehlo()
        return smtp

    def _authenticate(self, smtp: smtplib.SMTP, source: str) -> None:
        user = self.user or source
        auth_mode = self.auth_type
        if auth_mode == "auto":
            if self.token_provider is not None:
                auth_mode = "xoauth2"
            elif self.password is not None:
                auth_mode = "login"
            else:
                raise ValueError(
                    f"M365SmtpSender cannot authenticate: neither token_provider nor password was provided for user {user}."
                )

        if auth_mode == "xoauth2":
            if self.token_provider is None:
                raise ValueError("XOAUTH2 requested but no token_provider configured.")
            token = self.token_provider.get_access_token()
            auth_str = f"user={user}\1auth=Bearer {token}\1\1"
            auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
            code, resp = smtp.docmd("AUTH", f"XOAUTH2 {auth_b64}")
            if code == 334:
                err_detail = ""
                try:
                    err_detail = base64.b64decode(resp).decode("utf-8", errors="replace")
                except Exception:
                    err_detail = str(resp)
                try:
                    smtp.docmd("")
                except Exception:
                    pass
                raise smtplib.SMTPAuthenticationError(
                    code, f"XOAUTH2 authentication failed for {user}: {err_detail}"
                )
            if code not in (235, 503):
                raise smtplib.SMTPAuthenticationError(code, resp)
        elif auth_mode == "login":
            if self.password is None:
                raise ValueError("Password login requested but no password provided.")
            smtp.login(user, self.password)
        else:
            raise ValueError(f"Unknown SMTP auth type: {auth_mode}")


class M365GraphSender:
    """Microsoft Graph API sender (POST /v1.0/users/{user_id}/sendMail).

    Supports delegated OAuth (via TokenProvider) or application client-credentials
    (tenant_id, client_id, client_secret).
    """

    def __init__(
        self,
        token_provider: Optional[TokenProvider] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        save_to_sent_items: bool = True,
        timeout: int = 30,
    ) -> None:
        self.token_provider = token_provider
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self._reply_to = reply_to
        self.save_to_sent_items = save_to_sent_items
        self.timeout = timeout

    def _get_token(self) -> str:
        if self.client_secret and self.tenant_id and self.client_id:
            url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            data = urllib.parse.urlencode(
                {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                }
            ).encode("utf-8")
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return str(payload.get("access_token") or "")
        if self.token_provider is not None:
            return self.token_provider.get_access_token()
        raise ValueError(
            "M365GraphSender requires either a token_provider or client_credentials (tenant_id, client_id, client_secret)."
        )

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
        token = self._get_token()
        user_endpoint = self.user_id or (source if "@" in source else "me")
        url = f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(user_endpoint)}/sendMail"

        message_dict: dict[str, object] = {
            "subject": subject,
            "body": {
                "contentType": "HTML" if html_body else "Text",
                "content": html_body if html_body else body,
            },
            "toRecipients": [{"emailAddress": {"address": to_address}}],
        }
        if cc_addresses:
            message_dict["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc_addresses
            ]
        if bcc_addresses:
            message_dict["bccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in bcc_addresses
            ]
        reply = self._reply_to or source
        if reply:
            message_dict["replyTo"] = [{"emailAddress": {"address": reply}}]

        payload = {
            "message": message_dict,
            "saveToSentItems": "true" if self.save_to_sent_items else "false",
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                client_id = resp.headers.get("client-request-id")
                return str(client_id or f"graph-{uuid.uuid4()}")
        except urllib.error.HTTPError as err:
            err_body = ""
            try:
                err_body = err.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(
                f"Microsoft Graph sendMail failed (HTTP {err.code}): {err_body}"
            ) from err



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
        # send_raw_email (not the simpler send_email API) so we can set
        # List-Unsubscribe - Gmail/Yahoo bulk-sender rules expect it and
        # the simple API has no header support.
        msg = EmailMessage()
        msg["From"] = source
        msg["To"] = to_address
        if cc_addresses:
            msg["Cc"] = ", ".join(cc_addresses)
        msg["Subject"] = subject
        if self._reply_to:
            msg["Reply-To"] = self._reply_to
        unsubscribe_address = self._reply_to or source
        msg["List-Unsubscribe"] = f"<mailto:{unsubscribe_address}?subject=unsubscribe>"
        # set_content() + add_alternative() builds a proper
        # multipart/alternative - `body` is always the plain-text part
        # (some clients/spam filters render only this), `html_body` (when
        # given) is the richer part clients prefer to display. SES's
        # open-tracking pixel only works when there's an HTML part.
        msg.set_content(body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")

        # SES doesn't parse the raw message's headers for delivery - a Cc
        # header alone would show the address to the recipient without
        # actually sending them anything, so it must also be listed here.
        # Bcc addresses are added to Destinations only, NOT to msg headers,
        # so recipients do not see the address.
        destinations = [to_address] + list(cc_addresses or []) + list(bcc_addresses or [])
        kwargs: dict[str, object] = {
            "Source": source,
            "Destinations": destinations,
            "RawMessage": {"Data": msg.as_bytes()},
        }
        if self._configuration_set:
            kwargs["ConfigurationSetName"] = self._configuration_set
        resp = self._client.send_raw_email(**kwargs)
        return str(resp.get("MessageId") or "")


class EmailService:
    def __init__(
        self,
        campaign_name: str,
        settings: Optional[EmailSettings] = None,
        token_provider: Optional[TokenProvider] = None,
        ses_sender: Optional[MailSender] = None,
        mail_sender: Optional[MailSender] = None,
        company_lookup: Optional[CompanyLookup] = None,
        aws_profile: Optional[str] = None,
    ) -> None:
        self.campaign_name = campaign_name
        if settings is None:
            try:
                from cocli.core.config import load_campaign_config
                raw = load_campaign_config(campaign_name) if campaign_name else {}
                settings = EmailSettings.model_validate(raw.get("email") or {})
            except Exception:
                settings = EmailSettings()
        self.settings = settings
        self._token_provider = token_provider
        self._mail_sender = mail_sender or ses_sender
        self._company_lookup = company_lookup
        self._aws_profile = aws_profile

    @property
    def _ses_sender(self) -> Optional[MailSender]:
        return self._mail_sender

    @_ses_sender.setter
    def _ses_sender(self, val: Optional[MailSender]) -> None:
        self._mail_sender = val

    def send(self, request: SendMailRequest) -> SendMailResult:
        from cocli.core.exclusions import ExclusionManager
        from cocli.application.ses_suppression_service import SesSuppressionService

        source = request.from_address or self.settings.from_address
        if not source:
            raise ValueError("from_address is required (request or campaign [email].from_address)")

        # Pre-send suppression & exclusion checks
        slug_for_check = request.company_slug or self._lookup(request.to_address)
        ex_mgr = ExclusionManager(self.campaign_name)
        if ex_mgr.is_excluded(slug=slug_for_check, domain=request.to_address):
            raise ValueError(f"Recipient {request.to_address} is locally excluded.")

        # Injected senders are tests/fakes: do not open a live SES v2 client
        # (boto3 default chain → ~/.aws credential_process → 1Password /
        # Windows Hello) just to check the account suppression list.
        # Only check SES suppression when using the SES backend.
        if self._mail_sender is None and (self.settings.backend or "ses").lower() == "ses":
            ses_suppress = SesSuppressionService(
                region=self.settings.ses_region, profile=self._aws_profile
            )
            if ses_suppress.is_suppressed(request.to_address):
                raise ValueError(
                    f"Recipient {request.to_address} is suppressed in AWS SES."
                )

        sender = self._get_sender()

        bcc_list = list(request.bcc_addresses)
        if self.settings.bcc_address and self.settings.bcc_address not in bcc_list:
            bcc_list.append(self.settings.bcc_address)
        for bcc in self.settings.bcc_addresses:
            if bcc not in bcc_list:
                bcc_list.append(bcc)

        sent_id = sender.send_email(
            source=source,
            to_address=request.to_address,
            subject=request.subject,
            body=request.body,
            html_body=request.html_body,
            cc_addresses=request.cc_addresses or None,
            bcc_addresses=bcc_list or None,
        )
        slug = request.company_slug or self._lookup(request.to_address)
        note_written = False
        if slug:
            backend_prefix = (self.settings.backend or "ses").lower()
            msg = MailMessage(
                message_id=sent_id or f"{backend_prefix}-{datetime.now(UTC).timestamp()}",
                from_address=source,
                to_addresses=[request.to_address],
                subject=request.subject,
                date=datetime.now(UTC),
                body=request.body,
            )
            self._write_note(slug, msg, direction="sent")
            note_written = True
        return SendMailResult(
            message_id=sent_id,
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
        if result.noted:
            from cocli.utils.alert_utils import send_alert

            send_alert(
                f"{result.noted} new email(s) filed as company notes "
                f"(unmatched={result.unmatched})",
                title="cocli email",
                tags=["email", "inbox"],
                cooldown_key=f"email-poll-{self.campaign_name}",
            )
        return result

    def _get_sender(self) -> MailSender:
        # Cached on first use: constructing a Boto3SesSender re-runs
        # boto3.Session(profile_name=...), which re-triggers 1Password/AWS
        # credential resolution. Uncached, a batch of N sends meant N
        # credential resolutions (the Windows-Hello-popup-storm failure
        # mode this project has hit before with per-item AWS auth loops).
        if self._mail_sender is None:
            backend = (self.settings.backend or "ses").lower()
            if backend == "ses":
                sender = Boto3SesSender(
                    self.settings.ses_region,
                    profile=self._aws_profile,
                    configuration_set=self.settings.ses_configuration_set,
                )
                sender._reply_to = self.settings.reply_to
                self._mail_sender = sender
            elif backend in ("m365", "m365_smtp", "smtp"):
                if backend == "m365" and (
                    self.settings.graph_client_secret or self.settings.graph_client_secret_env
                ):
                    self._mail_sender = self._create_graph_sender()
                else:
                    self._mail_sender = self._create_m365_smtp_sender()
            elif backend == "m365_graph":
                self._mail_sender = self._create_graph_sender()
            else:
                raise ValueError(f"Unknown email backend: {self.settings.backend}")
        return self._mail_sender

    def _ses(self) -> MailSender:
        """Backward-compatibility alias for _get_sender()."""
        return self._get_sender()

    def _create_m365_smtp_sender(self) -> M365SmtpSender:
        password = self.settings.smtp_password
        if not password and self.settings.smtp_password_env:
            password = os.environ.get(self.settings.smtp_password_env)

        token_prov = None
        if not password or self.settings.smtp_auth_type == "xoauth2":
            token_prov = self._token()

        sender = M365SmtpSender(
            host=self.settings.smtp_host,
            port=self.settings.smtp_port,
            user=self.settings.smtp_user or self.settings.imap_user,
            token_provider=token_prov,
            password=password,
            auth_type=self.settings.smtp_auth_type,
            reply_to=self.settings.reply_to,
        )
        return sender

    def _create_graph_sender(self) -> M365GraphSender:
        secret = self.settings.graph_client_secret
        if not secret and self.settings.graph_client_secret_env:
            secret = os.environ.get(self.settings.graph_client_secret_env)

        token_prov = None
        if not secret:
            token_prov = self._token()

        sender = M365GraphSender(
            token_provider=token_prov,
            tenant_id=self.settings.graph_tenant_id,
            client_id=self.settings.graph_client_id or self.settings.client_id,
            client_secret=secret,
            user_id=self.settings.graph_user_id or self.settings.imap_user,
            reply_to=self.settings.reply_to,
        )
        return sender

    def _token(self) -> TokenProvider:
        if self._token_provider is not None:
            return self._token_provider
        if not self.settings.client_id:
            raise ValueError("campaign [email].client_id is required for Microsoft OAuth")
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

    def _write_note(self, company_slug: str, message: MailMessage, *, direction: Literal["sent", "received"]) -> Path:
        notes_dir = paths.companies.entry(company_slug).path / "notes"
        dt = message.date if isinstance(message.date, datetime) else datetime.now(UTC)
        note = EmailNote(
            timestamp=dt,
            title=message.subject or "(no subject)",
            direction=direction,  # "sent" or "received"
            from_address=message.from_address,
            to_addresses=message.to_addresses if isinstance(message.to_addresses, list) else [message.to_addresses],
            date=dt,
            message_id=message.message_id,
            content=message.body.strip(),
        )
        saved_path = note.to_file(notes_dir)
        logger.info("Wrote %s mail note for %s (%s)", direction, company_slug, message.message_id)

        if direction == "received":
            from cocli.application.engagement_service import EngagementService
            from cocli.models.engagement import EngagementEvent

            EngagementService(self.campaign_name).record_event(
                EngagementEvent(
                    campaign_name=self.campaign_name,
                    company_slug=company_slug,
                    event_type="email_reply",
                    source="imap",
                    details={"subject": message.subject, "from": message.from_address},
                )
            )

        local_tz: Any
        try:
            from tzlocal import get_localzone

            local_tz = get_localzone()
        except Exception:
            local_tz = UTC

        co_name = company_slug.replace("-", " ").title()
        self.record_email_in_cache(
            CompanyEmail(
                datetime_utc=dt,
                datetime_local=dt.astimezone(local_tz),
                company_name=co_name,
                company_slug=company_slug,
                title=note.title,
                direction=direction,
                from_address=note.from_address,
                to_addresses=note.to_addresses,
                content=note.content,
                file_path=saved_path,
                message_id=note.message_id,
                status="sent",
            )
        )

        return saved_path

    def _emails_cache_path(self) -> Path:
        campaign = self.campaign_name or "default"
        return paths.campaign(campaign).path / "indexes" / "recent_emails" / "cache.json"

    def _write_emails_cache(self, emails: list[CompanyEmail]) -> None:
        try:
            cache_path = self._emails_cache_path()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "updated_at": datetime.now(UTC).isoformat(),
                "emails": [e.model_dump(mode="json") for e in emails],
            }
            cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write recent emails cache: {e}")

    def record_email_in_cache(self, email_item: CompanyEmail) -> None:
        """Write-through: prepends a newly sent/received email into cache.json without scanning."""
        try:
            emails = self.get_recent_emails(use_cache=True)
            emails = [
                e
                for e in emails
                if not (
                    (email_item.message_id and e.message_id == email_item.message_id)
                    or (
                        email_item.file_path
                        and e.file_path
                        and str(e.file_path) == str(email_item.file_path)
                    )
                )
            ]
            emails.insert(0, email_item)
            emails.sort(key=lambda e: e.datetime_utc, reverse=True)
            self._write_emails_cache(emails)
        except Exception as e:
            logger.warning(f"Failed to record email in cache: {e}")

    def rebuild_recent_emails_cache(self, days_limit: int = 30) -> list[CompanyEmail]:
        emails = self._scan_recent_emails(days_limit=days_limit)
        self._write_emails_cache(emails)
        return emails

    def get_recent_emails(
        self, days_limit: int = 30, use_cache: bool = True
    ) -> list[CompanyEmail]:
        """Return recent emails (sent and received) with their content.
        Uses cache.json for instant responses when use_cache=True.
        """
        cache_path = self._emails_cache_path()
        if use_cache and cache_path.exists():
            try:
                content = json.loads(cache_path.read_text(encoding="utf-8"))
                raw_emails = content.get("emails", [])
                return [CompanyEmail.model_validate(e) for e in raw_emails]
            except Exception as e:
                logger.warning(
                    f"Failed to read recent emails cache, falling back to disk scan: {e}"
                )

        return self.rebuild_recent_emails_cache(days_limit=days_limit)

    def _scan_recent_emails(self, days_limit: int = 30) -> list[CompanyEmail]:
        emails: list[CompanyEmail] = []
        seen_message_ids: set[str] = set()

        local_tz: Any
        try:
            from tzlocal import get_localzone

            local_tz = get_localzone()
        except Exception:
            local_tz = UTC

        now_utc = datetime.now(UTC)
        cutoff_utc = now_utc - timedelta(days=days_limit)

        # 1. Scan company notes for EmailNotes (both sent and received)
        companies_dir = paths.companies.path
        if companies_dir.exists():
            for comp_dir in companies_dir.iterdir():
                if not comp_dir.is_dir():
                    continue
                notes_dir = comp_dir / "notes"
                if not notes_dir.exists():
                    continue
                company_name = comp_dir.name.replace("-", " ").title()
                for note_file in notes_dir.glob("*-email-*.md"):
                    try:
                        email_note = EmailNote.from_file(note_file)
                        if email_note and email_note.timestamp >= cutoff_utc:
                            dt_local = email_note.timestamp.astimezone(local_tz)
                            item = CompanyEmail(
                                datetime_utc=email_note.timestamp,
                                datetime_local=dt_local,
                                company_name=company_name,
                                company_slug=comp_dir.name,
                                title=email_note.title,
                                direction=email_note.direction,
                                from_address=email_note.from_address,
                                to_addresses=email_note.to_addresses,
                                content=email_note.content,
                                file_path=note_file,
                                message_id=email_note.message_id,
                                status="sent",
                            )
                            emails.append(item)
                            if email_note.message_id:
                                seen_message_ids.add(email_note.message_id)
                    except Exception as e:
                        logger.debug(f"Error reading email note {note_file}: {e}")

        # 2. Also scan batch send log log.usv if it exists
        try:
            from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

            campaign = self.campaign_name or "default"
            log_path = SendLogEntry.get_index_dir(campaign) / "log.usv"
            if log_path.exists():
                for line in log_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        entry = SendLogEntry.from_usv(line)
                        if entry.message_id and entry.message_id in seen_message_ids:
                            continue
                        if entry.sent_at >= cutoff_utc:
                            dt_local = entry.sent_at.astimezone(local_tz)
                            emails.append(
                                CompanyEmail(
                                    datetime_utc=entry.sent_at,
                                    datetime_local=dt_local,
                                    company_name=entry.company_slug.replace("-", " ").title(),
                                    company_slug=entry.company_slug,
                                    title=entry.subject,
                                    direction="sent",
                                    from_address="",
                                    to_addresses=[entry.recipient],
                                    content=(
                                        f"(Batch send: {entry.batch_id}, template: {entry.template_id})"
                                        if not entry.error
                                        else f"Error: {entry.error}"
                                    ),
                                    message_id=entry.message_id,
                                    status=entry.status,
                                    batch_id=entry.batch_id,
                                    template_id=entry.template_id,
                                    error=entry.error,
                                    initiative=entry.initiative,
                                )
                            )
                    except Exception as e:
                        logger.debug(f"Error reading SendLogEntry: {e}")
        except Exception as e:
            logger.debug(f"Error scanning SendLogEntry: {e}")

        emails.sort(key=lambda e: e.datetime_utc, reverse=True)
        return emails


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
