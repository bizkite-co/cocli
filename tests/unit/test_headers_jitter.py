from cocli.utils.headers import jittered_delay_ms


def test_jittered_delay_stays_within_range() -> None:
    base = 1000
    for _ in range(200):
        d = jittered_delay_ms(base, jitter_pct=0.4)
        assert 600 <= d <= 1400


def test_jittered_delay_is_not_always_the_same_value() -> None:
    """The whole point: a fixed-interval script is a detectable
    fingerprint. Enough samples must not collapse to one repeated value."""
    values = {jittered_delay_ms(1000) for _ in range(50)}
    assert len(values) > 5


def test_jittered_delay_returns_int() -> None:
    assert isinstance(jittered_delay_ms(500), int)
