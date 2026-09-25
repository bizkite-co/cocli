from __future__ import annotations

from typing import Any

from cocli.application.personalized_outreach_service import (
    ProspectContactMatch,
    PersonalizedOutreachService,
    extract_first_name,
)
from cocli.models.companies.company import Company
from cocli.models.people.person import Person


def test_extract_first_name() -> None:
    assert extract_first_name("Dr. Alice Smith") == "Alice"
    assert extract_first_name("Bob Jones") == "Bob"
    assert extract_first_name("Ms. Carol Johnson") == "Carol"
    assert extract_first_name("") is None
    assert extract_first_name("123") is None


def test_generate_copy_includes_name_and_utm() -> None:
    service = PersonalizedOutreachService("roadmap")
    subject, body = service.generate_copy(
        first_name="David",
        company_name="Apex Financial",
        company_slug="apex-financial",
    )

    assert "David," in subject
    assert len(subject) > 15
    assert "https://getretirementtaxanalyzer.com?" in body
    assert "utm_source=email_sequence" in body
    assert "utm_campaign=roadmap" in body
    assert "utm_content=apex-financial" in body
    assert "utm_term=david" in body


def test_generate_copy_collapses_newlines_for_html_templates(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Regression (2026-09-17): BaseUsvModel.to_usv() turns every real
    newline into a literal "<br>" for storage. An .html template authored
    with normal line-wrapping for source readability would otherwise pick
    up a stray <br> after every wrapped line once it round-trips through
    the pending-batch USV file, filling the rendered email with unwanted
    line breaks. generate_copy() must flatten real newlines out of HTML
    bodies (leaving literal <br> tags already in the source alone) before
    anything reaches storage."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    templates_dir = paths.campaigns / "roadmap" / "email-templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "email_intro.html").write_text(
        "---\n"
        "subject_templates:\n"
        "  - '{first_name}, hello'\n"
        "---\n"
        "<p>Hi {first_name},</p>\n"
        "<p>Line one\n"
        "<br><br>\n"
        "Line two</p>\n",
        encoding="utf-8",
    )

    service = PersonalizedOutreachService("roadmap")
    _, body = service.generate_copy(
        first_name="Bob",
        company_name="Acme Co",
        company_slug="acme-co",
        template_name="email_intro.html",
    )

    assert "\n" not in body
    assert body.count("<br>") == 2
    assert "Line one <br><br> Line two" in body


def test_generate_copy_preserves_newlines_for_md_templates() -> None:
    service = PersonalizedOutreachService("roadmap")
    _, body = service.generate_copy(
        first_name="David",
        company_name="Apex Financial",
        company_slug="apex-financial",
        template_name="email_01_pas_hook.md",
    )
    assert "\n" in body


def test_find_eligible_prospects(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    company = Company(
        name="Target Financial",
        slug="target-financial",
        domain="targetfinancial.com",
        email="info@targetfinancial.com",
        tags=["roadmap"],
    )
    company.save()

    person = Person(
        name="Edward Miller",
        email="edward@targetfinancial.com",
        company_name="Target Financial",
        slug="edward-miller",
    )
    person.save()

    # Link contact to company
    contacts_dir = paths.companies.entry("target-financial").path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    symlink = contacts_dir / "edward-miller"
    symlink.symlink_to(person.get_local_path())

    service = PersonalizedOutreachService("roadmap")
    matches = service.find_eligible_prospects(limit=10)

    assert len(matches) == 1
    assert matches[0].company_slug == "target-financial"
    assert matches[0].first_name == "Edward"
    assert matches[0].recipient_email == "edward@targetfinancial.com"


def test_find_contact_for_company_matches_the_same_rules_as_the_scanner(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """FollowUpService needs a single-company lookup with the exact same
    contact-selection rules as find_eligible_prospects()'s campaign-wide
    scan - this is that lookup, extracted rather than duplicated."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    company = Company(
        name="Target Financial",
        slug="target-financial",
        domain="targetfinancial.com",
        email="info@targetfinancial.com",
        tags=["roadmap"],
    )
    company.save()

    person = Person(
        name="Edward Miller",
        email="edward@targetfinancial.com",
        company_name="Target Financial",
        slug="edward-miller",
    )
    person.save()

    contacts_dir = paths.companies.entry("target-financial").path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    (contacts_dir / "edward-miller").symlink_to(person.get_local_path())

    service = PersonalizedOutreachService("roadmap")
    match = service.find_contact_for_company("target-financial")

    assert match is not None
    assert match.first_name == "Edward"
    assert match.recipient_email == "edward@targetfinancial.com"
    assert match.company_slug == "target-financial"


def test_find_contact_for_company_returns_none_when_unresolvable(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    service = PersonalizedOutreachService("roadmap")
    assert service.find_contact_for_company("does-not-exist") is None


class _FakeEmailResult:
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id


class _FakeEmailService:
    """Stand-in for EmailService.send() - raises for recipients in fail_for
    so per-recipient isolation can be exercised without SES/1Password."""

    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.fail_for = fail_for or set()
        self.sent_to: list[str] = []
        self.sent_requests: list[Any] = []

    def send(self, request: Any) -> _FakeEmailResult:
        self.sent_to.append(request.to_address)
        self.sent_requests.append(request)
        if request.to_address in self.fail_for:
            raise RuntimeError("SES boom")
        return _FakeEmailResult(message_id=f"msg-{request.to_address}")


def _match(slug: str, email: str, subject: str = "Hi") -> ProspectContactMatch:
    return ProspectContactMatch(
        company_slug=slug,
        company_name=slug.replace("-", " ").title(),
        recipient_email=email,
        contact_name="Contact Person",
        first_name="Contact",
        role=None,
        subject=subject,
        body=f"body for {slug}",
    )


def test_send_batch_with_html_template_populates_html_body_and_text_fallback(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """A .html template_id means the rendered body IS HTML - send_batch
    must pass it as html_body with an auto-derived plain-text fallback,
    not send raw HTML tags as the only (plain-text) body."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    match = _match("acme-co", "bob@acme.test")
    match.body = "<p>Hi Bob,</p><p>Check out our <b>product</b>.</p>"
    fake_email_service = _FakeEmailService()

    service = PersonalizedOutreachService("roadmap")
    result = service.send_batch(
        [match], template_id="email_intro.html", email_service=fake_email_service
    )

    assert result.sent == 1
    sent_request = fake_email_service.sent_requests[0]
    assert sent_request.html_body == "<p>Hi Bob,</p><p>Check out our <b>product</b>.</p>"
    assert "<" not in sent_request.body
    assert "Hi Bob," in sent_request.body
    assert "Check out our product" in sent_request.body


def test_send_batch_with_md_template_never_sets_html_body(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    match = _match("acme-co", "bob@acme.test")
    fake_email_service = _FakeEmailService()

    service = PersonalizedOutreachService("roadmap")
    service.send_batch(
        [match], template_id="email_01_pas_hook.md", email_service=fake_email_service
    )

    assert fake_email_service.sent_requests[0].html_body is None


def _write_layout_template(paths: Any, campaign: str = "roadmap") -> None:
    """A .md template with a `layout:` frontmatter key + its .njk layout,
    both in email-templates/ (the campaign-generic dir load_template()
    checks first) - the shape email_02_product_overview.md/.njk actually
    use in campaigns/roadmap/initiatives/rta/email-sequences/."""
    templates_dir = paths.campaigns / campaign / "email-templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "email_02_product_overview.md").write_text(
        "---\n"
        "subject_templates:\n"
        "  - '{first_name}, take a look'\n"
        "layout: email_02_product_overview.njk\n"
        "---\n"
        "Hi {first_name},\n\n"
        "Check out **{landing_url}**.\n",
        encoding="utf-8",
    )
    (templates_dir / "email_02_product_overview.njk").write_text(
        "<html><body>{{ content | safe }}"
        '<p><a href="{{ landing_url }}/unsubscribe">unsubscribe</a></p></body></html>',
        encoding="utf-8",
    )


def test_layout_for_template_reads_frontmatter_key(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _write_layout_template(paths)

    service = PersonalizedOutreachService("roadmap")
    assert service._layout_for_template("email_02_product_overview.md") == "email_02_product_overview.njk"
    assert service._layout_for_template("email_01_pas_hook.md") is None


def test_render_markdown_email_wraps_content_in_layout(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _write_layout_template(paths)

    service = PersonalizedOutreachService("roadmap")
    html = service.render_markdown_email(
        "Hi Bob,\n\nSome **bold** text.", "email_02_product_overview.njk"
    )

    assert "<html>" in html
    assert "<p>Hi Bob,</p>" in html
    assert "<strong>bold</strong>" in html
    assert "unsubscribe" in html


def test_send_batch_with_layout_template_renders_markdown_to_html(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """A .md template with a `layout:` key must be rendered through that
    layout at send time - markdown source becomes real HTML, not sent
    as raw markdown text with asterisks in it."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _write_layout_template(paths)

    match = _match("acme-co", "bob@acme.test", subject="Hi Bob")
    match.body = "Hi Bob,\n\nCheck out **our product**."
    fake_email_service = _FakeEmailService()

    service = PersonalizedOutreachService("roadmap")
    result = service.send_batch(
        [match], template_id="email_02_product_overview.md", email_service=fake_email_service
    )

    assert result.sent == 1
    sent = fake_email_service.sent_requests[0]
    assert sent.html_body is not None
    assert "<strong>our product</strong>" in sent.html_body
    assert "**" not in sent.html_body
    assert "Check out our product" in sent.body


def test_entry_to_match_prefers_hand_edited_rendered_outreach_file(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The whole point of writing rendered-outreach/<slug>/<template>.md
    (2026-09-17): Mark hand-edits that file (e.g. adding "As promised,")
    before sending, and entry_to_match() must pick up that edit instead
    of the frozen pending.usv snapshot from when the follow-up was
    queued."""
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

    monkeypatch.setattr(paths, "root", tmp_path)

    service = PersonalizedOutreachService("roadmap")
    match = _match("acme-co", "bob@acme.test", subject="Original subject")
    match.body = "Original body"
    entry = PendingBatchEntry(
        batch_id="b1",
        template_id="email_02_product_overview.md",
        company_slug="acme-co",
        recipient="bob@acme.test",
        subject=match.subject,
        body=match.body,
        initiative="rta",
    )

    rendered_path = service.render_and_save_draft(match, template_id="email_02_product_overview.md")
    content = rendered_path.read_text(encoding="utf-8")
    rendered_path.write_text(
        content.replace("Original body", "As promised, here's the original body"),
        encoding="utf-8",
    )

    resolved = service.entry_to_match(entry)

    assert "As promised" in resolved.body
    assert resolved.subject == "Original subject"


def test_update_pending_entry_syncs_rendered_outreach_file(tmp_path: Any, monkeypatch: Any) -> None:
    """A TUI-modal edit and a direct file edit must not silently diverge -
    update_pending_entry() writes through to the rendered-outreach file
    so entry_to_match() always has one consistent answer."""
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

    monkeypatch.setattr(paths, "root", tmp_path)
    _write_layout_template(paths)

    service = PersonalizedOutreachService("roadmap")
    match = _match("acme-co", "bob@acme.test", subject="Original subject")
    match.body = "Original body"
    service.render_and_save_draft(match, template_id="email_02_product_overview.md")
    service.append_pending_batch_entries(
        [
            PendingBatchEntry(
                batch_id="b1",
                template_id="email_02_product_overview.md",
                company_slug="acme-co",
                recipient="bob@acme.test",
                subject=match.subject,
                body=match.body,
                initiative="rta",
            )
        ]
    )

    service.update_pending_entry(
        "b1", "acme-co", subject="Edited subject", body="Edited body via TUI"
    )

    rendered_path = service._rendered_outreach_path("rta", "acme-co", "email_02_product_overview.md")
    content = rendered_path.read_text(encoding="utf-8")
    assert "Edited body via TUI" in content
    assert 'subject: Edited subject' in content
    # Other frontmatter (written by render_and_save_draft) must survive.
    assert "company_name: Acme Co" in content

    # update_pending_entry() must also keep the .html preview in sync.
    html_path = rendered_path.with_suffix(".html")
    assert html_path.exists()
    assert "Edited body via TUI" in html_path.read_text(encoding="utf-8")


def test_render_and_save_draft_writes_html_preview_when_layout_present(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Mark (2026-09-17): "we also need to emit the rendered HTML" - a
    .html sibling, in the same rendered-outreach/<slug>/ folder, so the
    actual image/testimonial/button can be reviewed, not just markdown
    source with raw HTML tags sitting in it."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _write_layout_template(paths)

    service = PersonalizedOutreachService("roadmap")
    match = _match("acme-co", "bob@acme.test", subject="Hi Bob")
    match.body = "Hi Bob,\n\nCheck out **our product**."

    md_path = service.render_and_save_draft(match, template_id="email_02_product_overview.md")

    html_path = md_path.with_suffix(".html")
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "<strong>our product</strong>" in html
    assert "**" not in html


def test_render_and_save_html_preview_reflects_latest_hand_edit(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Re-running render_and_save_html_preview() must pick up whatever is
    *currently* in the .md file, not whatever it was rendered from
    originally - this is the "stays in sync when the markdown changes"
    behavior Mark asked for."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _write_layout_template(paths)

    service = PersonalizedOutreachService("roadmap")
    match = _match("acme-co", "bob@acme.test", subject="Hi Bob")
    match.body = "Original body."
    md_path = service.render_and_save_draft(match, template_id="email_02_product_overview.md")

    md_path.write_text(
        md_path.read_text(encoding="utf-8").replace("Original body.", "As promised, edited body."),
        encoding="utf-8",
    )

    html_path = service.render_and_save_html_preview("rta", "acme-co", "email_02_product_overview.md")

    assert html_path is not None
    html = html_path.read_text(encoding="utf-8")
    assert "As promised, edited body." in html
    assert "Original body." not in html


def test_render_and_save_html_preview_returns_none_for_plain_text_template(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """A plain-text .md template (no `layout:`) has nothing to preview
    beyond its own body - no .html file should be produced."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    service = PersonalizedOutreachService("roadmap")
    match = _match("acme-co", "bob@acme.test", subject="Hi Bob")
    match.body = "Plain text body."
    md_path = service.render_and_save_draft(match, template_id="email_01_pas_hook.md")

    assert service.render_and_save_html_preview("rta", "acme-co", "email_01_pas_hook.md") is None
    assert not md_path.with_suffix(".html").exists()


def test_entry_to_match_refreshes_html_preview_as_a_side_effect(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Every time a pending entry is resolved (TUI preview, edit, or
    send), the .html sibling should be refreshed too - so it's never
    stale by the time someone actually looks at it or sends it."""
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

    monkeypatch.setattr(paths, "root", tmp_path)
    _write_layout_template(paths)

    service = PersonalizedOutreachService("roadmap")
    match = _match("acme-co", "bob@acme.test", subject="Hi Bob")
    match.body = "Original body."
    md_path = service.render_and_save_draft(match, template_id="email_02_product_overview.md")
    md_path.write_text(
        md_path.read_text(encoding="utf-8").replace("Original body.", "Edited body."),
        encoding="utf-8",
    )

    entry = PendingBatchEntry(
        batch_id="b1",
        template_id="email_02_product_overview.md",
        company_slug="acme-co",
        recipient="bob@acme.test",
        subject="stale subject",
        body="stale body",
        initiative="rta",
    )
    service.entry_to_match(entry)

    html = md_path.with_suffix(".html").read_text(encoding="utf-8")
    assert "Edited body." in html


def test_ensure_rendered_outreach_draft_creates_from_frozen_entry_when_missing(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """A batch frozen via freeze_batch()/"New Batch" never gets a
    rendered-outreach file up front (unlike FollowUpService/prepare-batch)
    - ensure_rendered_outreach_draft() must materialize one from the
    frozen row so "open HTML preview" works there too."""
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

    monkeypatch.setattr(paths, "root", tmp_path)
    _write_layout_template(paths)

    service = PersonalizedOutreachService("roadmap")
    entry = PendingBatchEntry(
        batch_id="b1",
        template_id="email_02_product_overview.md",
        company_slug="acme-co",
        recipient="bob@acme.test",
        subject="Frozen subject",
        body="Frozen body",
        initiative="rta",
    )

    rendered_path = service.ensure_rendered_outreach_draft(entry)

    assert rendered_path.exists()
    assert "Frozen body" in rendered_path.read_text(encoding="utf-8")


def test_ensure_rendered_outreach_draft_never_clobbers_an_existing_file(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """entry_to_match() returns placeholder company_name/contact_name/
    first_name for entries with no file yet - if ensure_rendered_outreach_draft()
    called render_and_save_draft() unconditionally, viewing an entry
    that already has a real rendered-outreach file (e.g. written by
    FollowUpService with the real contact name) would blow that away."""
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

    monkeypatch.setattr(paths, "root", tmp_path)
    _write_layout_template(paths)

    service = PersonalizedOutreachService("roadmap")
    real_match = _match("acme-co", "bob@acme.test", subject="Real subject")
    real_match.contact_name = "Bob Real"
    real_match.first_name = "Bob"
    real_match.body = "Hand-edited body."
    service.render_and_save_draft(real_match, template_id="email_02_product_overview.md")

    entry = PendingBatchEntry(
        batch_id="b1",
        template_id="email_02_product_overview.md",
        company_slug="acme-co",
        recipient="bob@acme.test",
        subject="Stale frozen subject",
        body="Stale frozen body",
        initiative="rta",
    )

    rendered_path = service.ensure_rendered_outreach_draft(entry)
    content = rendered_path.read_text(encoding="utf-8")

    assert "contact_name: Bob Real" in content
    assert "Hand-edited body." in content
    assert "Stale frozen body" not in content


def test_send_batch_isolates_per_recipient_failures(tmp_path: Any, monkeypatch: Any) -> None:
    """One failing recipient must not stop the others from being attempted
    and logged - same isolation discipline as requeue_enrichment_gaps."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    matches = [_match("good-co", "good@co.test"), _match("bad-co", "bad@co.test")]
    fake_email_service = _FakeEmailService(fail_for={"bad@co.test"})

    service = PersonalizedOutreachService("roadmap")
    result = service.send_batch(
        matches, template_id="email_01_pas_hook.md", email_service=fake_email_service
    )

    assert result.sent == 1
    assert result.failed == 1
    assert fake_email_service.sent_to == ["good@co.test", "bad@co.test"]

    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    index_dir = SendLogEntry.get_index_dir("roadmap")
    log_path = index_dir / "log.usv"
    entries = [SendLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
    by_slug = {e.company_slug: e for e in entries}

    assert by_slug["good-co"].status == "sent"
    assert by_slug["good-co"].message_id == "msg-good@co.test"
    assert by_slug["good-co"].batch_id == result.batch_id

    assert by_slug["bad-co"].status == "failed"
    assert by_slug["bad-co"].error is not None
    assert by_slug["bad-co"].batch_id == result.batch_id

    assert (index_dir / "datapackage.json").exists()


def test_send_batch_appends_across_calls(tmp_path: Any, monkeypatch: Any) -> None:
    """Each send_batch() call is a new batch_id but must append to, not
    overwrite, prior batches' rows in the same log."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    service = PersonalizedOutreachService("roadmap")

    first = service.send_batch(
        [_match("first-co", "first@co.test")],
        template_id="t1",
        email_service=_FakeEmailService(),
    )
    second = service.send_batch(
        [_match("second-co", "second@co.test")],
        template_id="t1",
        email_service=_FakeEmailService(),
    )

    assert first.batch_id != second.batch_id

    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    log_path = SendLogEntry.get_index_dir("roadmap") / "log.usv"
    entries = [SendLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
    assert {e.company_slug for e in entries} == {"first-co", "second-co"}


def test_load_template_prefers_generic_dir_over_rta_dir(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    generic_dir = paths.campaigns / "turboship" / "email-templates"
    generic_dir.mkdir(parents=True)
    (generic_dir / "welcome.md").write_text(
        '---\nsubject: "Generic {first_name}"\n---\n\nGeneric body {landing_url}',
        encoding="utf-8",
    )

    service = PersonalizedOutreachService("turboship")
    subject, body = service.load_template("welcome.md")

    assert subject == "Generic {first_name}"
    assert "Generic body" in body


def test_load_template_falls_back_to_rta_dir_when_generic_absent(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    rta_dir = paths.campaigns / "roadmap" / "initiatives" / "rta" / "email-sequences"
    rta_dir.mkdir(parents=True)
    (rta_dir / "legacy.md").write_text(
        '---\nsubject: "Legacy {first_name}"\n---\n\nLegacy body {landing_url}',
        encoding="utf-8",
    )

    service = PersonalizedOutreachService("roadmap")
    subject, body = service.load_template("legacy.md")

    assert subject == "Legacy {first_name}"
    assert "Legacy body" in body


def _make_eligible_prospect(
    paths: Any,
    *,
    slug: str = "acme-financial",
    company_name: str = "Acme Financial",
    first_name: str = "Bob",
    email_addr: str = "bob@acme.test",
) -> None:
    """Same setup shape as test_find_eligible_prospects above: a company
    tagged for the campaign, with a linked contact having a real first
    name and email - the minimum find_eligible_prospects() needs."""
    company = Company(
        name=company_name,
        slug=slug,
        domain=f"{slug}.test",
        email=email_addr,
        tags=["roadmap"],
    )
    company.save()

    person_slug = f"{first_name.lower()}-{slug}"
    person = Person(
        name=f"{first_name} Smith",
        email=email_addr,
        company_name=company_name,
        slug=person_slug,
    )
    person.save()

    contacts_dir = paths.companies.entry(slug).path / "contacts"
    contacts_dir.mkdir(parents=True, exist_ok=True)
    (contacts_dir / person_slug).symlink_to(person.get_local_path())


def test_freeze_batch_writes_rendered_pending_entries(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")

    pending = service.list_pending_batches()
    assert len(pending) == 1
    assert pending[0].batch_id == batch_id
    assert pending[0].template_id == "email_01_pas_hook.md"
    assert pending[0].company_slug == "acme-financial"
    assert pending[0].recipient == "bob@acme.test"
    # Fully rendered, not a raw template - no unresolved placeholders left.
    assert "{first_name}" not in pending[0].subject
    assert "Bob" in pending[0].subject


def test_freeze_batch_raises_on_bad_template_placeholder(tmp_path: Any, monkeypatch: Any) -> None:
    """A template bug must surface at freeze time, not after a batch has
    already been queued for review or send."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    template_dir = paths.campaigns / "roadmap" / "email-templates"
    template_dir.mkdir(parents=True)
    (template_dir / "broken.md").write_text(
        '---\nsubject: "Hi {first_name}"\n---\n\nSee {this_field_does_not_exist}',
        encoding="utf-8",
    )

    service = PersonalizedOutreachService("roadmap")
    import pytest

    with pytest.raises(KeyError):
        service.freeze_batch(limit=10, template_id="broken.md")

    assert service.list_pending_batches() == []


def test_send_pending_batch_sends_and_removes_only_that_batch(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")

    # An unrelated pending batch must survive untouched.
    other_index_dir = PendingBatchEntry.get_index_dir("roadmap")
    with open(other_index_dir / "pending.usv", "a", encoding="utf-8") as f:
        f.write(
            PendingBatchEntry(
                batch_id="other-batch",
                template_id="t2",
                company_slug="other-co",
                recipient="other@co.test",
                subject="Other subject",
                body="Other body",
            ).to_usv()
        )

    fake_email_service = _FakeEmailService()
    result = service.send_pending_batch(batch_id, email_service=fake_email_service)

    assert result.sent == 1
    assert result.failed == 0
    assert fake_email_service.sent_to == ["bob@acme.test"]

    remaining = service.list_pending_batches()
    assert [e.batch_id for e in remaining] == ["other-batch"]

    log_path = SendLogEntry.get_index_dir("roadmap") / "log.usv"
    sent_entries = [SendLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
    assert len(sent_entries) == 1
    assert sent_entries[0].company_slug == "acme-financial"
    assert sent_entries[0].status == "sent"


def test_send_pending_batch_uses_the_frozen_batchs_own_initiative(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The initiative recorded at freeze time must reach the send log -
    if send_pending_batch let it default, a batch frozen for a
    non-default initiative would get silently mislabeled "rta" at send."""
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(
        limit=10, template_id="email_01_pas_hook.md", initiative="wealth-manager-products"
    )

    fake_email_service = _FakeEmailService()
    service.send_pending_batch(batch_id, email_service=fake_email_service)

    log_path = SendLogEntry.get_index_dir("roadmap") / "log.usv"
    sent_entries = [SendLogEntry.from_usv(line) for line in log_path.read_text().splitlines() if line]
    assert sent_entries[0].initiative == "wealth-manager-products"


def test_send_pending_batch_restores_real_newlines_in_body(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """PendingBatchEntry.to_usv() sanitizes newlines to '<br>' for USV
    storage - the actual sent email must see real newlines back, not
    literal '<br>' text (that would itself be exactly the kind of
    send-time flaw the review step exists to catch)."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")

    fake_email_service = _FakeEmailService()
    service.send_pending_batch(batch_id, email_service=fake_email_service)

    sent_body = fake_email_service.sent_requests[0].body
    assert "<br>" not in sent_body
    assert "\n" in sent_body


def test_send_batch_threads_cc_addresses_through(tmp_path: Any, monkeypatch: Any) -> None:
    """cc mark@bizkite.net on a one-off send (Mark, 2026-09-17) - cc_addresses
    must reach the actual SendMailRequest, not just be accepted and dropped."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    match = _match("acme-co", "bob@acme.test")
    fake_email_service = _FakeEmailService()

    service = PersonalizedOutreachService("roadmap")
    service.send_batch(
        [match],
        template_id="email_01_pas_hook.md",
        email_service=fake_email_service,
        cc_addresses=["mark@bizkite.net"],
    )

    assert fake_email_service.sent_requests[0].cc_addresses == ["mark@bizkite.net"]


def test_send_batch_stamps_rendered_outreach_file_with_sent_receipt(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Mark (2026-09-17): "should we put a receipt next to every sent
    one" - yes, stamped into the existing rendered-outreach file's
    frontmatter (sent_at + message_id) rather than moved to a
    subdirectory, so entry_to_match()/ensure_rendered_outreach_draft()'s
    stable-path assumption still holds."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    match = _match("acme-co", "bob@acme.test", subject="Hi Bob")
    match.body = "Original body"
    service = PersonalizedOutreachService("roadmap")
    rendered_path = service.render_and_save_draft(match, template_id="email_01_pas_hook.md")

    fake_email_service = _FakeEmailService()
    service.send_batch(
        [match], template_id="email_01_pas_hook.md", email_service=fake_email_service
    )

    content = rendered_path.read_text(encoding="utf-8")
    assert "sent_at:" in content
    assert "message_id: msg-bob@acme.test" in content
    # The body itself must survive untouched.
    assert "Original body" in content


def test_send_one_pending_entry_leaves_batch_siblings_untouched(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """send-pending must send exactly one company's row, even if it
    happens to share a batch_id with other recipients (a bulk
    freeze_batch()) - unlike send_pending_batch(), which sends every row
    sharing that batch_id (Mark, 2026-09-17: "as a one-off without
    disrupting the regular workflow")."""
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

    monkeypatch.setattr(paths, "root", tmp_path)
    service = PersonalizedOutreachService("roadmap")
    service.append_pending_batch_entries(
        [
            PendingBatchEntry(
                batch_id="shared-batch",
                template_id="email_01_pas_hook.md",
                company_slug="acme-co",
                recipient="bob@acme.test",
                subject="Hi Bob",
                body="Body for Bob",
                initiative="rta",
            ),
            PendingBatchEntry(
                batch_id="shared-batch",
                template_id="email_01_pas_hook.md",
                company_slug="other-co",
                recipient="carol@other.test",
                subject="Hi Carol",
                body="Body for Carol",
                initiative="rta",
            ),
        ]
    )

    fake_email_service = _FakeEmailService()
    result = service.send_one_pending_entry(
        "shared-batch", "acme-co", email_service=fake_email_service
    )

    assert result.sent == 1
    assert fake_email_service.sent_to == ["bob@acme.test"]

    remaining = service.list_pending_batches()
    assert len(remaining) == 1
    assert remaining[0].company_slug == "other-co"


def test_html_templated_entry_preserves_literal_br_tags_through_send(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Regression: to_usv()'s newline->'<br>' storage sanitization is
    indistinguishable from a real, intentional <br> tag in HTML content -
    entry_to_match() must not "unescape" those back into raw newlines for
    an .html-templated entry, or genuine line breaks silently disappear
    from the rendered email (HTML doesn't render bare \\n as a break)."""
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_pending_batch import PendingBatchEntry

    monkeypatch.setattr(paths, "root", tmp_path)
    service = PersonalizedOutreachService("roadmap")

    html_body = "<p>Hi Bob,</p>\n<p>Line one<br>Line two</p>"
    entry = PendingBatchEntry(
        batch_id="b1",
        template_id="email_intro.html",
        company_slug="acme-co",
        recipient="bob@acme.test",
        subject="Hello",
        body=html_body,
    )
    service.append_pending_batch_entries([entry])

    fake_email_service = _FakeEmailService()
    service.send_pending_batch("b1", email_service=fake_email_service)

    sent = fake_email_service.sent_requests[0]
    assert sent.html_body is not None
    # The literal <br> between "Line one" and "Line two" must survive
    # exactly - not be turned into an invisible raw newline. The other
    # real \n in the source (between the two <p> tags) also becomes a
    # <br> on the way through USV storage, which is harmless in HTML
    # (an extra line break), unlike silently losing an intentional one.
    assert "Line one<br>Line two" in sent.html_body


def test_update_pending_entry_persists_edit_and_sends_it(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The "add my own text on top of the template, then send" step
    (Mark, 2026-09-16) - the edit must survive to the actual send, and
    must not touch any other row in the same pending.usv."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths, slug="edit-me-co", email_addr="edit@me.test")
    _make_eligible_prospect(paths, slug="leave-alone-co", email_addr="leave@alone.test")

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")

    updated = service.update_pending_entry(
        batch_id,
        "edit-me-co",
        subject="Edited subject",
        body="A quick personal note.\n\nRest of the template body.",
    )
    assert updated is True

    pending = {e.company_slug: e for e in service.list_pending_batches()}
    assert "A quick personal note." in pending["edit-me-co"].body.replace("<br>", "\n")
    # The other row must be untouched.
    assert pending["leave-alone-co"].subject != "Edited subject"

    fake_email_service = _FakeEmailService()
    service.send_pending_batch(batch_id, email_service=fake_email_service)

    sent = {r.to_address: r for r in fake_email_service.sent_requests}
    assert sent["edit@me.test"].subject == "Edited subject"
    assert "A quick personal note." in sent["edit@me.test"].body


def test_update_pending_entry_returns_false_when_not_found(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    service = PersonalizedOutreachService("roadmap")
    assert service.update_pending_entry("no-such-batch", "no-co", subject="x", body="y") is False


def test_discard_pending_batch_removes_without_sending(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_eligible_prospect(paths)

    service = PersonalizedOutreachService("roadmap")
    batch_id = service.freeze_batch(limit=10, template_id="email_01_pas_hook.md")

    fake_email_service = _FakeEmailService()
    service.discard_pending_batch(batch_id)

    assert service.list_pending_batches() == []
    assert fake_email_service.sent_to == []


def test_compute_unsubscribe_rate(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.application.personalized_outreach_service import compute_unsubscribe_rate
    from cocli.core.exclusions import ExclusionManager
    from cocli.core.paths import paths
    from cocli.models.campaigns.indexes.email_send_log import SendLogEntry

    monkeypatch.setattr(paths, "root", tmp_path)

    index_dir = SendLogEntry.get_index_dir("roadmap")
    index_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        SendLogEntry(
            batch_id="b1", template_id="t1", company_slug=f"co-{i}",
            recipient=f"co{i}@test.com", subject="Hi", status="sent",
        )
        for i in range(4)
    ] + [
        SendLogEntry(
            batch_id="b1", template_id="t1", company_slug="co-failed",
            recipient="failed@test.com", subject="Hi", status="failed", error="boom",
        )
    ]
    with open(index_dir / "log.usv", "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.to_usv())

    ExclusionManager("roadmap").add_exclusion(
        slug="co-1", domain="co1@test.com", reason="unsubscribe:COMPLAINT"
    )
    ExclusionManager("roadmap").add_exclusion(
        slug="co-wrong-trade", domain="wrong@test.com", reason="to-call-nonconforming"
    )

    stats = compute_unsubscribe_rate("roadmap")

    assert stats.sent_count == 4
    assert stats.unsubscribed_count == 1
    assert stats.rate == 0.25


def _make_initiative(
    paths: Any, initiative: str, categories: dict[str, dict[str, str]]
) -> None:
    """categories: {category_name: {relative_file_path: content}}."""
    base = paths.campaigns / "roadmap" / "initiatives" / initiative
    base.mkdir(parents=True, exist_ok=True)
    for category, files in categories.items():
        cat_dir = base / category
        for rel_path, content in files.items():
            file_path = cat_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")


def test_list_initiatives_lists_subdirectories_only(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    initiatives_dir = paths.campaigns / "roadmap" / "initiatives"
    initiatives_dir.mkdir(parents=True)
    (initiatives_dir / "README.md").write_text("not an initiative", encoding="utf-8")
    (initiatives_dir / "rta").mkdir()
    (initiatives_dir / "wealth-manager-products").mkdir()

    service = PersonalizedOutreachService("roadmap")
    assert service.list_initiatives() == ["rta", "wealth-manager-products"]


def test_list_initiative_categories_only_returns_existing_ones(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_initiative(
        paths,
        "rta",
        {
            "email-sequences": {"t.md": "x"},
            "rendered-outreach": {"acme/t.md": "x"},
            "tracking": {"utm.csv": "x"},
        },
    )
    _make_initiative(paths, "wealth-manager-products", {})

    service = PersonalizedOutreachService("roadmap")
    assert service.list_initiative_categories("rta") == [
        "email-sequences",
        "rendered-outreach",
        "tracking",
    ]
    assert service.list_initiative_categories("wealth-manager-products") == []


def test_list_initiative_templates_is_a_literal_folder_listing(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """Must not merge in the campaign-generic email-templates/ dir - that
    merge is list_templates()'s job for the CLI batch commands."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_initiative(paths, "rta", {"email-sequences": {"email_01_pas_hook.md": "x"}})

    generic_dir = paths.campaigns / "roadmap" / "email-templates"
    generic_dir.mkdir(parents=True)
    (generic_dir / "generic_only.md").write_text("x", encoding="utf-8")

    service = PersonalizedOutreachService("roadmap")
    assert service.list_initiative_templates("rta") == ["email_01_pas_hook.md"]


def test_list_category_files_covers_flat_and_nested(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_initiative(
        paths,
        "rta",
        {
            "tracking": {"utm-matrix.csv": "x", "gtm-events.json": "{}"},
            "rendered-outreach": {
                "acme-financial/email_01_pas_hook.md": "x",
                "other-co/email_01_pas_hook.md": "x",
            },
        },
    )

    service = PersonalizedOutreachService("roadmap")
    tracking_files = service.list_category_files("rta", "tracking")
    assert [f.name for f in tracking_files] == ["gtm-events.json", "utm-matrix.csv"]

    outreach_files = service.list_category_files("rta", "rendered-outreach")
    assert [f"{f.parent.name}/{f.name}" for f in outreach_files] == [
        "acme-financial/email_01_pas_hook.md",
        "other-co/email_01_pas_hook.md",
    ]


def test_list_category_files_missing_category_returns_empty(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_initiative(paths, "rta", {})

    service = PersonalizedOutreachService("roadmap")
    assert service.list_category_files("rta", "tracking") == []


def test_generate_copy_uses_the_given_initiative_not_hardcoded_rta(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """A second initiative's own email-sequences/ template must resolve
    correctly - not silently fall through to rta's (or the default
    hardcoded copy) because the initiative was never actually threaded
    through."""
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_initiative(
        paths,
        "wealth-manager-products",
        {
            "email-sequences": {
                "wmp_hook.md": '---\nsubject: "WMP hi {first_name}"\n---\n\nWMP body for {company_name}'
            }
        },
    )

    service = PersonalizedOutreachService("roadmap")
    subject, body = service.generate_copy(
        first_name="Sample",
        company_name="Sample Co",
        company_slug="sample-co",
        template_name="wmp_hook.md",
        initiative="wealth-manager-products",
    )

    assert subject == "WMP hi Sample"
    assert "WMP body for Sample Co" in body


def test_list_templates_includes_all_initiatives(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_initiative(paths, "rta", {"email-sequences": {"email_01.md": "x"}})
    _make_initiative(paths, "testimonials", {"email-sequences": {"request_testimonial.md": "x"}})

    service = PersonalizedOutreachService("roadmap")
    templates = service.list_templates()
    assert "email_01.md" in templates
    assert "request_testimonial.md" in templates


def test_list_templates_with_initiative(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_initiative(paths, "rta", {"email-sequences": {"email_01.md": "x"}})
    _make_initiative(paths, "testimonials", {"email-sequences": {"request_testimonial.md": "x"}})

    service = PersonalizedOutreachService("roadmap")
    choices = service.list_templates_with_initiative()
    assert ("[rta] email_01.md", "email_01.md", "rta") in choices
    assert ("[testimonials] request_testimonial.md", "request_testimonial.md", "testimonials") in choices


def test_template_path_fallback_across_initiatives(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)
    _make_initiative(paths, "testimonials", {"email-sequences": {"request_testimonial.md": "x"}})

    service = PersonalizedOutreachService("roadmap")
    # Even if caller passes default initiative="rta", fallback locates it in testimonials
    path = service._template_path("request_testimonial.md", initiative="rta")
    assert path.exists()
    assert "testimonials" in str(path)


def test_find_eligible_prospects_filters_by_tag(tmp_path: Any, monkeypatch: Any) -> None:
    from cocli.core.paths import paths

    monkeypatch.setattr(paths, "root", tmp_path)

    c1 = Company(name="Target Alpha", slug="target-alpha", tags=["roadmap", "testimonial-target"], email="alpha@test.com")
    c1.save()
    p1 = Person(name="Alice Alpha", email="alpha@test.com", company_name="Target Alpha", slug="alice-alpha")
    p1.save()
    contacts1 = paths.companies.entry("target-alpha").path / "contacts"
    contacts1.mkdir(parents=True)
    (contacts1 / "alice-alpha").symlink_to(p1.get_local_path())

    c2 = Company(name="Target Beta", slug="target-beta", tags=["roadmap"], email="beta@test.com")
    c2.save()
    p2 = Person(name="Bob Beta", email="beta@test.com", company_name="Target Beta", slug="bob-beta")
    p2.save()
    contacts2 = paths.companies.entry("target-beta").path / "contacts"
    contacts2.mkdir(parents=True)
    (contacts2 / "bob-beta").symlink_to(p2.get_local_path())

    service = PersonalizedOutreachService("roadmap")
    all_matches = service.find_eligible_prospects(limit=10)
    assert len(all_matches) == 2

    tagged_matches = service.find_eligible_prospects(limit=10, tag="testimonial-target")
    assert len(tagged_matches) == 1
    assert tagged_matches[0].company_slug == "target-alpha"

