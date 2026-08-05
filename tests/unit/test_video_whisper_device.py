"""Whisper CUDA/CPU device selection fingerprint."""

from unittest.mock import MagicMock, patch

from cocli.core.video.transcriber import _load_whisper_model


def test_load_whisper_prefers_cuda() -> None:
    mock_model = MagicMock()
    with patch(
        "cocli.core.video.transcriber.WhisperModel", return_value=mock_model
    ) as ctor:
        model, device, compute = _load_whisper_model("small")
    assert model is mock_model
    assert device == "cuda"
    assert compute == "float16"
    ctor.assert_called_once_with("small", device="cuda", compute_type="float16")


def test_load_whisper_falls_back_to_cpu() -> None:
    mock_cpu = MagicMock()

    def side_effect(*args: object, **kwargs: object) -> MagicMock:
        if kwargs.get("device") == "cuda":
            raise RuntimeError("no CUDA")
        return mock_cpu

    with patch(
        "cocli.core.video.transcriber.WhisperModel", side_effect=side_effect
    ) as ctor:
        model, device, compute = _load_whisper_model("small")
    assert model is mock_cpu
    assert device == "cpu"
    assert compute == "int8"
    assert ctor.call_count == 2
