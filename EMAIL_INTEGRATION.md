# Email Integration: CoCLI Campaign Outreach & Follow-ups

`cocli` supports outbound campaign outreach and personalized follow-ups with dual-backend support:
1. **Microsoft 365 Exchange Online (`m365` / `m365_smtp` / `m365_graph`)**: Recommended for primary campaign outreach from dedicated domains (e.g. `getretirementtaxanalyzer.com`) to match apex MX records, achieve native Exchange sender reputation, and ensure primary inbox placement.
2. **Amazon Simple Email Service (`ses`)**: Alternative backend for high-volume transactional or bulk notification scenarios.

## 1. Architecture Overview

- **Token Management**: `cocli` uses public-client Microsoft OAuth (`cocli/application/mail_oauth.py`) caching tokens in `~/.local/share/cocli/email-tokens/<user>.json`. Supports `offline_access`, `IMAP.AccessAsUser.All`, and `SMTP.Send`.
- **Senders**:
  - `M365SmtpSender`: Authenticates via standard SMTP (`smtp.office365.com:587`, STARTTLS) with `AUTH XOAUTH2` using cached OAuth tokens, or standard login passwords.
  - `M365GraphSender`: Sends via Microsoft Graph API (`POST /v1.0/users/{user}/sendMail`).
  - `Boto3SesSender`: Sends raw multipart/alternative emails via AWS SES.
- **Inbound Polling**: `EmailService.poll()` polls IMAP (`outlook.office365.com`) for inbound customer replies and logs them as `EmailNote` on matching company profiles.
- **TUI & CLI Surfaces**:
  - `TargetBatchesView` (Messages > Batch Email Drafts): review and bulk/individual dispatch.
  - `EnqueueFollowUpModal` (Messages > Follow-up Drafts or Company Detail): queue 1-to-1 follow-up tasks.
  - `EmailComposeModal` (bound to `m` in Company Detail): compose and send ad-hoc email.
  - CLI: `cocli email send --to ... --subject ... --body ... [--backend m365|ses]`.

## 2. Configuration (`config.toml`)

In `data/campaigns/<campaign>/config.toml`:

```toml
[email]
backend = "m365"                              # "m365", "m365_smtp", "m365_graph", or "ses"
from_address = "mark@getretirementtaxanalyzer.com"
reply_to = "mark@getretirementtaxanalyzer.com"
bcc_address = "test@bizkite.net"             # Optional audit/monitor BCC

# Microsoft 365 / SMTP settings
smtp_host = "smtp.office365.com"
smtp_port = 587
imap_host = "outlook.office365.com"
imap_user = "mark@getretirementtaxanalyzer.com"
token_cache = "~/.local/share/cocli/email-tokens/mark@getretirementtaxanalyzer.com.json"
client_id = "6fecbb2e-623e-41ae-b516-e786961f9651"

# AWS SES fallback settings
ses_region = "us-west-1"
ses_configuration_set = "cocli-outreach-roadmap"
```

## 3. DNS & Deliverability Best Practices

When sending via Microsoft 365 Exchange:
- **MX Record**: Points to `<domain-key>.mail.protection.outlook.com`.
- **SPF Record**: Ensure DNS TXT record includes Microsoft's SPF mechanism:
  `v=spf1 include:spf.protection.outlook.com ~all`
- **DKIM & DMARC**: Configured in Microsoft 365 Admin Center for the custom domain.

