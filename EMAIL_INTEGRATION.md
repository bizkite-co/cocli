# Email Integration Plan: CoCLI + Mutt-Setup

This document outlines the strategy for integrating email-sending capabilities into the CoCLI TUI by leveraging the existing `mutt-setup` infrastructure for OAuth2 token management.

## 1. Objective
Enable users to send emails directly from the Company and Person detail screens in CoCLI.

## 2. Architecture Overview
- **Token Management**: CoCLI will use `mutt-setup/scripts/mutt_oauth2.py` as a subprocess to retrieve OAuth2 access tokens for configured profiles (Office 365 or Gmail).
- **Email Sending**: CoCLI will implement a lightweight `EmailService` using Python's built-in `smtplib` with `AUTH XOAUTH2`.
- **UI**: A new `EmailCompose` screen in Textual will provide the interface for drafting and sending emails.
- **Logging**: Sent emails will be automatically saved as "Notes" in the corresponding company/person directory to maintain a communication history.

## 3. Implementation Steps

### Phase 1: Mutt-Setup Fix & Preparation
- **Fix `mutt-setup` bug**: Resolve the `NameError` in `mutt-setup/scripts/op_integration.py` by adding `import os`.
- **Standardize Profiles**: Ensure `mutt-setup` profiles are correctly configured in `~/.config/mutt-setup/accounts/`.

### Phase 2: CoCLI Core Integration
- **Update Configuration**:
    - Add `email` section to `cocli/core/config.py`.
    - Fields: `mutt_setup_path` (absolute path), `default_profile` (profile name), `from_address`.
- **Create `EmailService`**:
    - Location: `cocli/application/email_service.py`.
    - Method `get_token(profile)`: Runs `mutt_oauth2.py` and captures stdout.
    - Method `send_email(to, subject, body, profile)`:
        - Authenticates via SMTP (`smtp.office365.com:587` or `smtp.gmail.com:587`).
        - Uses `XOAUTH2` authentication string: `user={user}\x01auth=Bearer {token}\x01\x01`.
- **Update Models**: Ensure `Company` and `Person` models have consistent `email` field handling.

### Phase 3: TUI Implementation
- **Create `EmailCompose` Screen**:
    - Location: `cocli/tui/widgets/email_compose.py`.
    - Fields: `To`, `Subject`, `Body` (multi-line).
    - Actions: `Send (Enter/Ctrl+S)`, `Cancel (Esc)`.
- **Integrate with `CompanyDetail`**:
    - Add `Binding("m", "compose_email", "Email")` to `CompanyDetail`.
    - Logic:
        - If `InfoTable` is focused and "Email" row selected -> Use company email.
        - If `ContactsTable` is focused and a contact selected -> Use contact email.
- **Integrate with `PersonDetail`**:
    - Add `Binding("m", "compose_email", "Email")`.
    - Logic: Pre-fill with person's email.
- **Communication History**:
    - Upon successful send, trigger `action_add_note()` logic to save a record of the email.

## 4. Level of Effort (LOE)

| Task | Estimated Time | Complexity |
| :--- | :--- | :--- |
| **Phase 1: Mutt-Setup Fix** | 0.5 hours | Low |
| **Phase 2: EmailService (SMTP/OAuth)** | 3-4 hours | Medium |
| **Phase 3: EmailCompose Screen** | 4-6 hours | Medium/High |
| **Phase 3: TUI Bindings & Logic** | 2-3 hours | Medium |
| **Phase 3: History/Notes Integration** | 1-2 hours | Low |
| **Total** | **10.5 - 15.5 hours** | **Medium** |

## 5. Risks & Considerations
- **1Password CLI**: Requires `op` to be authenticated. CoCLI should detect if `mutt_oauth2.py` fails due to 1Password being locked and notify the user.
- **SMTP Limitations**: Modern providers have rate limits and security policies. `XOAUTH2` is the preferred method for Office 365/Gmail.
- **TUI Suspension**: If the email body requires a full editor (NVim), we might need to use the `app.suspend()` pattern similar to how notes are edited.
- **Dependency**: `mutt-setup` must be present on the system. We should add a check for its existence in `cocli`'s startup or config validation.
