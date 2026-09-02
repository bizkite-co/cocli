from cocli.application.enrichment_outcome import notify_from_execute_result


def test_nested_404_is_orange_warning_with_http_code() -> None:
    message, severity = notify_from_execute_result(
        {
            "status": "success",
            "op_id": "op_re_enrich",
            "result": {
                "error": "Navigation failed with status 404",
                "error_category": "navigation_failed",
                "http_status": 404,
                "url": "https://www.relationinsurance.com/locations/x",
                "all_emails": [],
            },
        }
    )
    assert severity == "warning"
    assert "HTTP 404" in message
    assert "Enrichment successful" not in message
    assert "relationinsurance.com" in message


def test_http_status_parsed_from_error_string_when_field_missing() -> None:
    message, severity = notify_from_execute_result(
        {
            "status": "success",
            "result": {"error": "Could not navigate. Error: Navigation failed with status 522"},
        }
    )
    assert severity == "warning"
    assert "HTTP 522" in message


def test_true_success_stays_information() -> None:
    message, severity = notify_from_execute_result(
        {
            "status": "success",
            "result": {"all_emails": ["a@b.com"], "error": None},
        }
    )
    assert severity == "information"
    assert "successful" in message
    assert "1 emails" in message


def test_success_counts_unique_emails_across_fields() -> None:
    message, _severity = notify_from_execute_result(
        {
            "status": "success",
            "result": {
                "email": "info@hotlead.com",
                "all_emails": ["info@hotlead.com", "sales@hotlead.com"],
                "personnel": [{"name": "Jane", "email": "jane@hotlead.com"}],
                "error": None,
            },
        }
    )
    assert "3 emails" in message
