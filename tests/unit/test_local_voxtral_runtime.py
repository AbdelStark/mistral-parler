"""Tests for the local Voxtral runtime wrapper."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import numpy as np
from parler.local.voxtral import LocalVoxtralRuntime


class _FakeTorch:
    def inference_mode(self):
        return nullcontext()


class _FakeProcessor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.tokenizer = _FakeTokenizer()

    def apply_transcription_request(self, **kwargs: object) -> _FakeInputs:
        self.calls.append(kwargs)
        assert kwargs["model_id"] == "mistralai/Voxtral-Mini-3B-2507"
        assert kwargs["language"] == "fr"
        assert kwargs["sampling_rate"] == 16_000
        assert kwargs["format"] == ["wav"]
        waveform = kwargs["audio"]
        assert isinstance(waveform, np.ndarray)
        return _FakeInputs()

    @staticmethod
    def batch_decode(predicted_ids: object, *, skip_special_tokens: bool) -> list[str]:
        assert skip_special_tokens is True
        assert isinstance(predicted_ids, np.ndarray)
        return ["Bonjour tout le monde."]


class _FakeInputs(dict[str, object]):
    def __init__(self) -> None:
        super().__init__(
            input_ids=np.array([[11, 12]]),
            input_features="fake-features",
        )
        self.input_ids = self["input_ids"]

    def to(self, device: str, dtype: str) -> _FakeInputs:
        assert device == "cpu"
        assert dtype == "float32"
        return self


class _FakeTextInputs(dict[str, object]):
    def __init__(self) -> None:
        super().__init__(
            input_ids=np.array([[11, 12]]),
            attention_mask=np.array([[1, 1]]),
        )
        self.input_ids = self["input_ids"]

    def to(self, device: str, dtype: str) -> _FakeTextInputs:
        assert device == "cpu"
        assert dtype == "float32"
        return self


class _FakeTokenizer:
    chat_template = None

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, prompts: list[str], *, return_tensors: str, padding: bool) -> _FakeInputs:
        self.calls.append(
            {
                "prompts": prompts,
                "return_tensors": return_tensors,
                "padding": padding,
            }
        )
        assert len(prompts) == 1
        assert "System instructions:" in prompts[0]
        assert "User request:" in prompts[0]
        assert prompts[0].endswith("Assistant response:\n")
        assert return_tensors == "pt"
        assert padding is True
        return _FakeTextInputs()


class _FakeModel:
    @staticmethod
    def to(device: str):
        return _FakeModel()

    @staticmethod
    def eval() -> None:
        return None

    @staticmethod
    def generate(**kwargs: object) -> np.ndarray:
        assert isinstance(kwargs["input_ids"], np.ndarray)
        if "input_features" in kwargs:
            assert kwargs["input_features"] == "fake-features"
            assert kwargs["max_new_tokens"] == 500
        else:
            assert kwargs["max_new_tokens"] == 64
        assert kwargs["do_sample"] is False
        return np.array([[11, 12, 1, 2, 3]])


def test_transcribe_file_uses_transcription_request_and_generate() -> None:
    processor = _FakeProcessor()
    with (
        patch("parler.local.voxtral._load_bundle", return_value=(processor, _FakeModel(), _FakeTorch(), "cpu", "float32")),
        patch("parler.local.voxtral._ensure_local_transcription_dependencies"),
        patch(
            "parler.local.voxtral._load_audio_waveform",
            return_value=np.array([0.1, -0.1], dtype=np.float32),
        ),
    ):
        runtime = LocalVoxtralRuntime("mistralai/Voxtral-Mini-3B-2507")
        result = runtime.transcribe_file(Path("/tmp/meeting.wav"), language="fr")

    assert result == "Bonjour tout le monde."
    assert len(processor.calls) == 1
    waveform = processor.calls[0]["audio"]
    assert isinstance(waveform, np.ndarray)


def test_generate_text_falls_back_to_plain_tokenizer_when_chat_template_missing() -> None:
    processor = _FakeProcessor()
    with patch(
        "parler.local.voxtral._load_bundle",
        return_value=(processor, _FakeModel(), _FakeTorch(), "cpu", "float32"),
    ):
        runtime = LocalVoxtralRuntime("mistralai/Voxtral-Mini-3B-2507")
        result = runtime.generate_text(
            [
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": "Extract decisions."},
            ],
            max_new_tokens=32,
            temperature=0.0,
        )

    assert result == "Bonjour tout le monde."
    assert len(processor.tokenizer.calls) == 1
