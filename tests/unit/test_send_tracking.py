from __future__ import annotations

from cocli.utils.send_tracking import inject_send_guid

DOMAIN = "https://getretirementtaxanalyzer.com"


def test_appends_token_to_a_url_with_an_existing_html_escaped_query_string() -> None:
    """The actual real-world shape: a Jinja-rendered <a href="..."> in an
    HTML email body, with &amp; separators already present."""
    html = (
        '<a href="https://getretirementtaxanalyzer.com/testimonials/'
        '?utm_source=email&amp;utm_medium=outreach&amp;utm_term=don">link</a>'
    )

    result = inject_send_guid(html, "abc123guid", DOMAIN)

    assert 'utm_term=don&amp;t=abc123guid">' in result
    # The separator style already in the URL must be preserved, not mixed.
    assert "&t=" not in result


def test_appends_token_to_a_url_with_a_plain_query_string() -> None:
    text = "visit https://getretirementtaxanalyzer.com/testimonials/?utm_source=email"

    result = inject_send_guid(text, "abc123guid", DOMAIN)

    assert result == "visit https://getretirementtaxanalyzer.com/testimonials/?utm_source=email&t=abc123guid"


def test_adds_a_question_mark_for_a_url_with_no_existing_query_string() -> None:
    """The actual bug this was built to fix: the unsubscribe link had no
    query string at all (`.../unsubscribe`), zero identifying info."""
    text = 'visit <a href="https://getretirementtaxanalyzer.com/unsubscribe">unsubscribe</a>'

    result = inject_send_guid(text, "abc123guid", DOMAIN)

    assert 'href="https://getretirementtaxanalyzer.com/unsubscribe?t=abc123guid"' in result


def test_rewrites_every_matching_link_not_just_the_first() -> None:
    text = (
        "https://getretirementtaxanalyzer.com/testimonials/?utm_source=email and also "
        "https://getretirementtaxanalyzer.com/unsubscribe"
    )

    result = inject_send_guid(text, "abc123guid", DOMAIN)

    assert result.count("t=abc123guid") == 2


def test_leaves_unrelated_domains_untouched() -> None:
    text = "see https://example.com/page and https://getretirementtaxanalyzer.com/signup/"

    result = inject_send_guid(text, "abc123guid", DOMAIN)

    assert "https://example.com/page" in result
    assert "t=abc123guid" not in result.split("and")[0]
    assert "getretirementtaxanalyzer.com/signup/?t=abc123guid" in result
