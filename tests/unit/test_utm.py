from cocli.utils.utm import append_utm_params


def test_append_utm_params_to_url() -> None:
    text = "Visit https://getretirementtaxanalyzer.com for details."
    result = append_utm_params(text, campaign="roadmap", company_slug="test-company")
    assert "utm_source=email_sequence" in result
    assert "utm_medium=email" in result
    assert "utm_campaign=roadmap" in result
    assert "utm_content=test-company" in result


def test_append_utm_params_preserves_existing_query() -> None:
    text = "Check out https://getretirementtaxanalyzer.com/path?foo=bar."
    result = append_utm_params(text, campaign="roadmap", company_slug="test-co")
    assert "foo=bar" in result
    assert "utm_source=email_sequence" in result


def test_append_utm_params_with_target_domain_filter() -> None:
    text = "Link 1: https://getretirementtaxanalyzer.com. Link 2: https://google.com."
    result = append_utm_params(
        text,
        campaign="roadmap",
        company_slug="test-co",
        target_domain="getretirementtaxanalyzer.com",
    )
    assert "getretirementtaxanalyzer.com?" in result
    assert "utm_campaign=roadmap" in result
    assert "google.com?utm" not in result
