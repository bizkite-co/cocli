import logging

from cocli.core.logging_config import RollingErrorCounter


def _make_record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test", level=logging.ERROR, pathname="x.py", lineno=1,
        msg=msg, args=None, exc_info=None,
    )


def test_default_max_messages_is_50() -> None:
    """Bumped from 20 -> 50: repeated cluster degradations showed 20 recent
    lines wasn't enough context when a node is throwing many distinct
    error types back-to-back."""
    counter = RollingErrorCounter()
    for i in range(60):
        counter.emit(_make_record(f"error {i}"))

    messages = counter.recent_messages()
    assert len(messages) == 50
    # oldest 10 of 60 (0-9) must have been dropped to keep the newest 50.
    assert any("error 59" in m for m in messages)
    assert not any(m == "error 9" for m in messages)


def test_recent_messages_returns_formatted_messages_oldest_first() -> None:
    counter = RollingErrorCounter(max_messages=20)
    counter.emit(_make_record("first error"))
    counter.emit(_make_record("second error"))

    messages = counter.recent_messages()
    assert len(messages) == 2
    assert "first error" in messages[0]
    assert "second error" in messages[1]


def test_recent_messages_is_bounded_and_drops_oldest() -> None:
    counter = RollingErrorCounter(max_messages=3)
    for i in range(5):
        counter.emit(_make_record(f"error {i}"))

    messages = counter.recent_messages()
    assert len(messages) == 3
    # oldest two (0, 1) must have been dropped, not the newest
    assert any("error 2" in m for m in messages)
    assert any("error 4" in m for m in messages)
    assert not any("error 0" in m for m in messages)


def test_count_since_unaffected_by_message_capture() -> None:
    """The two responsibilities (rolling count, bounded message sample)
    must stay independent - a full message buffer must not affect the
    time-windowed count."""
    counter = RollingErrorCounter(max_messages=2)
    for i in range(10):
        counter.emit(_make_record(f"error {i}"))

    assert counter.count_since(3600) == 10
    assert len(counter.recent_messages()) == 2
