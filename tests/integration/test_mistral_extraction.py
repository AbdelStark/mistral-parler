"""
Integration tests: DecisionExtractor with mocked Mistral Chat API

These tests verify that the extraction layer:
  - Builds the correct prompt from a Transcript + meeting context
  - Sends it to the Mistral Chat API with the right model/temperature
  - Parses the JSON response into a typed DecisionLog
  - Handles multi-pass extraction for long transcripts (>25,000 words)
  - Includes the correct system prompt from the prompt version registry
  - Validates JSON schema and retries once on parse failure

All HTTP calls are mocked. No real API key required.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from parler.extraction.extractor import DecisionExtractor
from parler.models import DecisionLog, Transcript, TranscriptSegment

# ─── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def short_transcript():
    """A transcript short enough for single-pass extraction (~50 words)."""
    segments = [
        TranscriptSegment(
            id=i,
            start_s=float(i * 10),
            end_s=float((i + 1) * 10),
            text=f"Segment {i} content here.",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        )
        for i in range(5)
    ]
    return Transcript(
        text=" ".join(s.text for s in segments),
        language="fr",
        duration_s=50.0,
        segments=tuple(segments),
    )


@pytest.fixture
def long_transcript():
    """A transcript long enough to trigger multi-pass extraction (>25,000 words)."""
    # Simulate a transcript with ~30,000 words
    long_text = "The team decided to launch the product next month. " * 600
    segment = TranscriptSegment(
        id=0,
        start_s=0.0,
        end_s=3600.0,
        text=long_text,
        language="en",
        speaker_id=None,
        speaker_confidence=None,
        confidence=0.9,
        no_speech_prob=0.01,
        code_switch=False,
        words=None,
    )
    return Transcript(
        text=long_text,
        language="en",
        duration_s=3600.0,
        segments=(segment,),
    )


@pytest.fixture
def many_segment_transcript():
    """A transcript with many short segments should use segment-windowed multi-pass extraction."""
    segments = tuple(
        TranscriptSegment(
            id=i,
            start_s=float(i * 5),
            end_s=float(i * 5 + 5),
            text=f"Segment {i}. The team confirmed milestone {i}.",
            language="en",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        )
        for i in range(50)
    )
    return Transcript(
        text=" ".join(segment.text for segment in segments),
        language="en",
        duration_s=250.0,
        segments=segments,
    )


@pytest.fixture
def explicit_local_recovery_transcript():
    segments = (
        TranscriptSegment(
            id=0,
            start_s=0.0,
            end_s=5.0,
            text="Bonjour à tous, nous allons commencer la réunion d'aujourd'hui.",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        ),
        TranscriptSegment(
            id=1,
            start_s=5.0,
            end_s=10.0,
            text="Du coup, Antoine, est-ce que tu peux t'en charger ?",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        ),
        TranscriptSegment(
            id=2,
            start_s=10.0,
            end_s=15.0,
            text="Oui, je vais m'en charger.",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        ),
        TranscriptSegment(
            id=3,
            start_s=15.0,
            end_s=20.0,
            text="À quelle date nous lançons la phase de test ?",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        ),
        TranscriptSegment(
            id=4,
            start_s=20.0,
            end_s=25.0,
            text="Et la deuxième question, quand est-ce que nous déclenchons la phase de lancement ?",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        ),
        TranscriptSegment(
            id=5,
            start_s=25.0,
            end_s=30.0,
            text="Il avait été également considéré de stopper le développement une fois le lancement.",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        ),
        TranscriptSegment(
            id=6,
            start_s=30.0,
            end_s=35.0,
            text="Nous rejetons cette décision.",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        ),
        TranscriptSegment(
            id=7,
            start_s=35.0,
            end_s=40.0,
            text="Nous allons donc continuer le développement après la phase de lancement.",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        ),
        TranscriptSegment(
            id=8,
            start_s=40.0,
            end_s=45.0,
            text="Et enfin, la dernière décision du conseil est que nous allons établir une réunion hebdomadaire pour consulter l'avancement du projet jusqu'à la phase de lancement.",
            language="fr",
            speaker_id=None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        ),
    )
    return Transcript(
        text=" ".join(segment.text for segment in segments),
        language="fr",
        duration_s=45.0,
        segments=segments,
    )


def make_extraction_response(decisions=None, commitments=None):
    """Build a minimal valid extraction response dict."""
    return {
        "decisions": decisions or [],
        "commitments": commitments or [],
        "rejected": [],
        "open_questions": [],
    }


# ─── Single-pass extraction ───────────────────────────────────────────────────


class TestSinglePassExtraction:
    def test_extract_calls_mistral_chat_api(self, short_transcript):
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=json.dumps(make_extraction_response())))
                ]
            )
            extractor = DecisionExtractor(api_key="test-key", model="mistral-large-latest")
            extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        mock_instance.chat.complete.assert_called_once()

    def test_extract_uses_correct_model(self, short_transcript):
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=json.dumps(make_extraction_response())))
                ]
            )
            extractor = DecisionExtractor(api_key="test-key", model="mistral-large-latest")
            extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        call_kwargs = mock_instance.chat.complete.call_args
        assert (
            call_kwargs.kwargs.get("model") == "mistral-large-latest"
            or (call_kwargs.args and call_kwargs.args[0] == "mistral-large-latest")
            or "mistral-large-latest" in str(call_kwargs)
        )

    def test_extract_temperature_is_zero(self, short_transcript):
        """Temperature must be 0 for deterministic extraction."""
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=json.dumps(make_extraction_response())))
                ]
            )
            extractor = DecisionExtractor(api_key="test-key", model="mistral-large-latest")
            extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        call_kwargs = mock_instance.chat.complete.call_args
        assert call_kwargs.kwargs.get("temperature") == 0.0 or "temperature=0" in str(call_kwargs)

    def test_extract_returns_decision_log(self, short_transcript):
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content=json.dumps(
                                make_extraction_response(
                                    decisions=[
                                        {
                                            "id": "D1",
                                            "summary": "Launch in May",
                                            "confidence": "high",
                                            "language": "fr",
                                            "quote": "On lance en mai.",
                                            "timestamp_s": 10.0,
                                            "speaker": "Pierre",
                                            "confirmed_by": [],
                                        }
                                    ]
                                )
                            )
                        )
                    )
                ]
            )
            extractor = DecisionExtractor(api_key="test-key", model="mistral-large-latest")
            result = extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        assert isinstance(result, DecisionLog)
        assert len(result.decisions) == 1
        assert result.decisions[0].summary == "Launch in May"

    def test_extract_includes_transcript_text_in_prompt(self, short_transcript):
        """The user message must include the actual transcript text."""
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=json.dumps(make_extraction_response())))
                ]
            )
            extractor = DecisionExtractor(api_key="test-key", model="mistral-large-latest")
            extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        call_args = mock_instance.chat.complete.call_args
        prompt_str = str(call_args)
        assert "Segment 0 content here." in prompt_str or "Segment" in prompt_str

    def test_extract_local_model_uses_hugging_face_runtime(self, short_transcript):
        with (
            patch("parler.extraction.extractor.LocalVoxtralRuntime") as MockRuntime,
            patch("parler.extraction.extractor.MistralClient") as MockClient,
        ):
            MockRuntime.return_value.generate_text.return_value = json.dumps(
                make_extraction_response(
                    decisions=[
                        {
                            "id": "D1",
                            "summary": "Launch in May",
                            "confidence": "high",
                            "language": "fr",
                            "quote": "On lance en mai.",
                            "timestamp_s": 10.0,
                            "speaker": "Pierre",
                            "confirmed_by": [],
                        }
                    ]
                )
            )
            extractor = DecisionExtractor(
                api_key="ignored-in-local-mode",
                model="local:mistralai/Voxtral-Mini-3B-2507",
            )
            result = extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        MockClient.assert_not_called()
        MockRuntime.return_value.generate_text.assert_called_once()
        assert isinstance(result, DecisionLog)
        assert result.decisions[0].summary == "Launch in May"
        assert result.metadata.model == "local:mistralai/Voxtral-Mini-3B-2507"

    def test_extract_local_model_parses_code_fenced_json(self, short_transcript):
        fenced_payload = {
            "decisions": [
                {
                    "decision": "Launch in May",
                    "confidence": "high",
                    "language": "fr",
                    "quote": "On lance en mai.",
                }
            ],
            "commitments": [
                {
                    "owner": "Pierre",
                    "action": "Prepare the launch checklist",
                    "confidence": "high",
                    "language": "fr",
                    "quote": "Je prépare la checklist de lancement.",
                }
            ],
            "rejected": [],
            "open_questions": [],
        }
        with (
            patch("parler.extraction.extractor.LocalVoxtralRuntime") as MockRuntime,
            patch("parler.extraction.extractor.MistralClient") as MockClient,
        ):
            MockRuntime.return_value.generate_text.return_value = (
                "```json\n" + json.dumps(fenced_payload) + "\n```"
            )
            extractor = DecisionExtractor(
                api_key="ignored-in-local-mode",
                model="local:mistralai/Voxtral-Mini-3B-2507",
            )
            result = extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        MockClient.assert_not_called()
        assert isinstance(result, DecisionLog)
        assert len(result.decisions) == 1
        assert result.decisions[0].summary == "Launch in May"
        assert len(result.commitments) == 1
        assert result.commitments[0].owner == "Pierre"

    def test_extract_local_model_recovers_explicit_items_from_transcript(
        self, explicit_local_recovery_transcript
    ):
        sparse_payload = {
            "decisions": [
                {
                    "summary": "Reject decision to stop development after launch",
                    "quote": "Nous rejetons cette décision. Nous allons donc continuer le développement après la phase de lancement.",
                    "confidence": "high",
                    "language": "fr",
                }
            ],
            "commitments": [],
            "rejected": [],
            "open_questions": [],
        }
        with (
            patch("parler.extraction.extractor.LocalVoxtralRuntime") as MockRuntime,
            patch("parler.extraction.extractor.MistralClient") as MockClient,
        ):
            MockRuntime.return_value.generate_text.return_value = (
                "```json\n" + json.dumps(sparse_payload) + "\n```"
            )
            extractor = DecisionExtractor(
                api_key="ignored-in-local-mode",
                model="local:mistralai/Voxtral-Mini-3B-2507",
            )
            result = extractor.extract(
                explicit_local_recovery_transcript,
                meeting_date=date(2026, 4, 9),
                participants=["Pierre", "Sophie"],
            )

        MockClient.assert_not_called()
        assert len(result.decisions) >= 2
        assert any(
            "continuer le développement après la phase de lancement" in item.summary
            for item in result.decisions
        )
        assert any("réunion hebdomadaire" in item.summary for item in result.decisions)
        assert len(result.commitments) == 1
        assert result.commitments[0].owner == "Antoine"
        assert "je vais m'en charger" in result.commitments[0].action.lower()
        assert len(result.rejected) == 1
        assert len(result.open_questions) == 2
        assert any(
            item.question == "À quelle date nous lançons la phase de test ?"
            for item in result.open_questions
        )
        assert any(
            "quand est-ce que nous déclenchons la phase de lancement ?" in item.question.lower()
            for item in result.open_questions
        )


# ─── Multi-pass extraction ────────────────────────────────────────────────────


class TestMultiPassExtraction:
    def test_long_transcript_triggers_multiple_api_calls(self, long_transcript):
        """A 30,000-word transcript should trigger at least 2 extraction passes."""
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=json.dumps(make_extraction_response())))
                ]
            )
            extractor = DecisionExtractor(
                api_key="test-key", model="mistral-large-latest", multi_pass_threshold=25000
            )
            extractor.extract(long_transcript, meeting_date=date(2026, 4, 9))

        assert mock_instance.chat.complete.call_count >= 2

    def test_multi_pass_decisions_merged_and_deduplicated(self, long_transcript):
        """If the same decision appears in two passes, it should appear only once."""
        call_count = [0]
        decisions_per_pass = [
            [
                {
                    "id": "D1",
                    "summary": "Launch decision",
                    "confidence": "high",
                    "language": "en",
                    "quote": ".",
                    "timestamp_s": 1.0,
                    "speaker": None,
                    "confirmed_by": [],
                }
            ],
            # Second pass returns the same decision (duplicate)
            [
                {
                    "id": "D1",
                    "summary": "Launch decision",
                    "confidence": "high",
                    "language": "en",
                    "quote": ".",
                    "timestamp_s": 1.0,
                    "speaker": None,
                    "confirmed_by": [],
                }
            ],
        ]

        def side_effect(**kwargs):
            resp = make_extraction_response(decisions=decisions_per_pass[call_count[0]])
            call_count[0] += 1
            return MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps(resp)))])

        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.side_effect = side_effect
            extractor = DecisionExtractor(
                api_key="test-key", model="mistral-large-latest", multi_pass_threshold=25000
            )
            result = extractor.extract(long_transcript, meeting_date=date(2026, 4, 9))

        # Deduplicated: only one "Launch decision"
        assert len(result.decisions) == 1

    def test_many_segment_transcript_triggers_multiple_api_calls(self, many_segment_transcript):
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=json.dumps(make_extraction_response())))
                ]
            )
            extractor = DecisionExtractor(api_key="test-key", model="mistral-large-latest")
            extractor.extract(many_segment_transcript, meeting_date=date(2026, 4, 9))

        assert mock_instance.chat.complete.call_count >= 2


# ─── JSON parse failure handling ─────────────────────────────────────────────


class TestJSONParseFailureHandling:
    def test_invalid_json_retried_once(self, short_transcript):
        """If the API returns invalid JSON, it should retry once before returning empty log."""
        call_count = [0]

        def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(
                    choices=[MagicMock(message=MagicMock(content="This is not JSON at all"))]
                )
            return MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=json.dumps(make_extraction_response())))
                ]
            )

        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.side_effect = side_effect
            extractor = DecisionExtractor(api_key="test-key", model="mistral-large-latest")
            result = extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        assert call_count[0] == 2  # retried once
        assert isinstance(result, DecisionLog)

    def test_two_consecutive_parse_failures_returns_empty_log(self, short_transcript):
        """After 2 parse failures, return empty log rather than crashing."""
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="totally invalid"))]
            )
            extractor = DecisionExtractor(api_key="test-key", model="mistral-large-latest")
            result = extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        assert result.is_empty


# ─── Prompt versioning ────────────────────────────────────────────────────────


class TestPromptVersioning:
    def test_system_prompt_is_non_empty(self, short_transcript):
        """The system prompt passed to the API must not be empty."""
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=json.dumps(make_extraction_response())))
                ]
            )
            extractor = DecisionExtractor(api_key="test-key", model="mistral-large-latest")
            extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        call_args = mock_instance.chat.complete.call_args
        messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
        system_messages = [m for m in messages if m.get("role") == "system"]
        assert len(system_messages) == 1
        assert len(system_messages[0]["content"]) > 100

    def test_extraction_metadata_records_model_and_version(self, short_transcript):
        """The returned DecisionLog.metadata should record model and prompt_version."""
        with patch("parler.extraction.extractor.MistralClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.chat.complete.return_value = MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content=json.dumps(make_extraction_response())))
                ]
            )
            extractor = DecisionExtractor(
                api_key="test-key", model="mistral-large-latest", prompt_version="v1.2.0"
            )
            result = extractor.extract(short_transcript, meeting_date=date(2026, 4, 9))

        assert result.metadata.model == "mistral-large-latest"
        assert result.metadata.prompt_version == "v1.2.0"
