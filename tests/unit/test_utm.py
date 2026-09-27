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


def test_append_utm_params_with_person_slug() -> None:
    text = "Visit https://getretirementtaxanalyzer.com for details."
    result = append_utm_params(
        text,
        campaign="testimonials",
        company_slug="blauner-financial",
        person_slug="don-blauner",
    )
    assert "utm_content=blauner-financial" in result
    assert "utm_term=don-blauner" in result
    assert "utm_campaign=testimonials" in result


def test_append_utm_params_override() -> None:
    text = "Visit https://getretirementtaxanalyzer.com/feedback?utm_source=old&utm_content=placeholder&utm_term=old_term&ref=123"
    result = append_utm_params(
        text,
        campaign="testimonials",
        company_slug="calibrate-wealth",
        person_slug="dave-halvorson",
        source="email",
        override=True,
    )
    assert "ref=123" in result
    assert "utm_content=calibrate-wealth" in result
    assert "utm_term=dave-halvorson" in result
    assert "utm_source=email" in result
    assert "placeholder" not in result
    assert "old_term" not in result
