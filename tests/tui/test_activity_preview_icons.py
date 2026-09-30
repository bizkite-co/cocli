from cocli.tui.widgets.company_detail import format_activity_preview


def _call_activity(recording_path=None):
    return {
        "title": "Logged call",
        "content": "Left a voicemail",
        "activity_type": "call",
        "metadata": {"disposition": "Connected", "recording_path": recording_path},
        "is_scheduled": False,
    }


def test_plain_call_uses_phone_emoji_styled_non_red():
    """Mark prefers the shape of the full-color phone emoji ("\U0001F4DE")
    over the monochrome dingbat - he only wants it not red (red is reserved
    for errors), not necessarily green. The style may not visibly recolor
    the glyph in every terminal font, but it must be applied and must not
    be red."""
    text = format_activity_preview(_call_activity(recording_path=None))
    plain = text.plain
    assert plain.startswith("\U0001F4DE")
    assert "\U0001F4FC" not in plain

    spans = [s for s in text.spans if s.start == 0 and s.end == len("\U0001F4DE")]
    assert len(spans) == 1
    assert spans[0].style != "red"


def test_call_recording_uses_distinct_cassette_icon_not_plain_phone():
    """Regression: calls and recordings previously rendered with the
    identical icon, making them indistinguishable in the Activity list."""
    plain_call = format_activity_preview(_call_activity(recording_path=None)).plain
    recording_call = format_activity_preview(
        _call_activity(recording_path="recordings/RE123.wav")
    ).plain

    assert recording_call.startswith("\U0001F4FC")
    assert plain_call[0] != recording_call[0]

    # Recording icon isn't stylized green - only the plain-call phone is.
    recording_text = format_activity_preview(_call_activity(recording_path="recordings/RE123.wav"))
    assert not any(s.style == "green" for s in recording_text.spans)


def test_activity_table_uses_row_cursor_so_preview_column_highlights_too():
    """Regression: DataTable defaults to cursor_type="cell" - with only
    Date/Preview columns, that highlighted just the Date cell and never
    the Preview cell of the selected row."""
    from cocli.tui.widgets.company_detail import ActivityTable

    assert ActivityTable.cursor_type == "row"
