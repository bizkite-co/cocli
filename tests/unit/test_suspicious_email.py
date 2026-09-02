from pathlib import Path
from unittest.mock import patch

from cocli.core.paths import paths
from cocli.core.suspicious_email import (
    REASON_PLACEHOLDER,
    REASON_ROT13,
    classify_scraped_email,
    rot13,
    snippet_around,
)
from cocli.models.campaigns.queues.scraped_email_invalid import (
    enqueue_scraped_email_invalid,
)


def test_example_com_is_placeholder() -> None:
    assert classify_scraped_email("email@example.com") == REASON_PLACEHOLDER


def test_rot13_pbz_tld() -> None:
    encoded = "bssvpr@fhzzreftvyypcn.pbz"
    assert rot13(encoded) == "office@summersgillcpa.com"
    assert classify_scraped_email(encoded) == REASON_ROT13


def test_real_office_email_is_kept() -> None:
    assert classify_scraped_email("office@summersgillspa.com") is None
    assert classify_scraped_email("jane@hotlead.com") is None


def test_snippet_around_collapses_whitespace() -> None:
    html = "contact us at\n  bssvpr@fhzzreftvyypcn.pbz  today"
    snip = snippet_around(html, "bssvpr@fhzzreftvyypcn.pbz", width=20)
    assert "bssvpr@fhzzreftvyypcn.pbz" in snip
    assert "\n" not in snip


def test_enqueue_writes_pending_usv(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        dest = enqueue_scraped_email_invalid(
            campaign_name="roadmap",
            company_slug="summers-gill",
            domain="summersgillspa.com",
            email="bssvpr@fhzzreftvyypcn.pbz",
            reason=REASON_ROT13,
            witness_relpath="raw/enrichment/ab/summersgillspa.com/witness.html",
            context_snippet="mailto:bssvpr@fhzzreftvyypcn.pbz",
        )
        assert dest is not None
        assert dest.exists()
        body = dest.read_text()
        assert "bssvpr@fhzzreftvyypcn.pbz" in body
        assert REASON_ROT13 in body
        assert "witness.html" in body
