"""
Shared pytest fixtures for parler test suite.

Provides:
  - sample_transcript_fr: a short French transcript (10 segments)
  - sample_transcript_bilingual: FR/EN mixed transcript
  - sample_decision_log: a full DecisionLog with decisions, commitments, etc.
  - mock_mistral_client: a pre-configured MagicMock of the MistralClient
  - mock_voxtral_response: factory fixture for building Voxtral API responses
  - tmp_cache_dir: a fresh temporary directory for each test
  - parler_config: a minimal ParlerConfig suitable for unit tests (no real API key)
"""

import pytest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from parler.models import (
    Transcript,
    TranscriptSegment,
    DecisionLog,
    Decision,
    Commitment,
    CommitmentDeadline,
    Rejection,
    OpenQuestion,
    ExtractionMetadata,
)


# ─── TranscriptSegment helpers ───────────────────────────────────────────────

def _make_segment(
    id: int,
    start: float,
    end: float,
    text: str,
    language: str = "fr",
    speaker_id: str | None = None,
    confidence: float = 0.9,
    no_speech_prob: float = 0.01,
    code_switch: bool = False,
) -> TranscriptSegment:
    return TranscriptSegment(
        id=id,
        start_s=start,
        end_s=end,
        text=text,
        language=language,
        speaker_id=speaker_id,
        speaker_confidence="high" if speaker_id else None,
        confidence=confidence,
        no_speech_prob=no_speech_prob,
        code_switch=code_switch,
        words=None,
    )


# ─── Transcript fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def sample_transcript_fr():
    """
    A 10-segment French transcript representing a ~10-minute product meeting.
    Contains:
      - 2 speakers (Pierre and Sophie)
      - 1 implicit decision (around segment 4)
      - 1 explicit commitment with a French deadline (around segment 7)
    """
    segments = (
        _make_segment(0, 0.0, 5.0, "Bonjour à tous, on commence.", speaker_id="Pierre"),
        _make_segment(1, 5.0, 12.0,
                      "Pierre à l'ordre du jour : le lancement produit.",
                      speaker_id="Pierre"),
        _make_segment(2, 12.0, 20.0,
                      "Sophie, où en est-on avec le déploiement ?",
                      speaker_id="Pierre"),
        _make_segment(3, 20.0, 35.0,
                      "Le déploiement est prêt. Il reste juste à finaliser les tests.",
                      speaker_id="Sophie"),
        _make_segment(4, 35.0, 50.0,
                      "Bien. On part sur le 15 mai pour le lancement, c'est décidé.",
                      speaker_id="Pierre"),
        _make_segment(5, 50.0, 62.0,
                      "D'accord, je note : lancement le 15 mai.",
                      speaker_id="Sophie"),
        _make_segment(6, 62.0, 75.0,
                      "Sophie, peux-tu revoir la checklist de déploiement ?",
                      speaker_id="Pierre"),
        _make_segment(7, 75.0, 90.0,
                      "Oui, je vais revoir la checklist avant vendredi prochain.",
                      speaker_id="Sophie"),
        _make_segment(8, 90.0, 100.0,
                      "Parfait. Des questions ?",
                      speaker_id="Pierre"),
        _make_segment(9, 100.0, 108.0,
                      "Non, c'est clair. Merci tout le monde.",
                      speaker_id="Sophie"),
    )
    return Transcript(
        text=" ".join(s.text for s in segments),
        language="fr",
        duration_s=108.0,
        segments=segments,
    )


@pytest.fixture
def sample_transcript_bilingual():
    """
    A bilingual FR/EN transcript with code-switching.
    Simulates a French startup meeting where English technical terms bleed in.
    """
    segments = (
        _make_segment(0, 0.0, 5.0, "Bonjour, on commence la réunion.", language="fr",
                      speaker_id="Pierre"),
        _make_segment(1, 5.0, 14.0,
                      "So, regarding the Python SDK — je pense qu'on devrait l'adopter.",
                      language="fr", speaker_id="Pierre", code_switch=True),
        _make_segment(2, 14.0, 25.0,
                      "Agreed. The SDK approach is much cleaner than direct API calls.",
                      language="en", speaker_id="Alice"),
        _make_segment(3, 25.0, 38.0,
                      "On a décidé : on va avec le Python SDK. C'est officiel.",
                      language="fr", speaker_id="Pierre"),
        _make_segment(4, 38.0, 52.0,
                      "Alice, can you prepare the migration guide by EOW?",
                      language="en", speaker_id="Pierre", code_switch=False),
        _make_segment(5, 52.0, 65.0,
                      "Sure, I'll have it ready by Friday.",
                      language="en", speaker_id="Alice"),
    )
    return Transcript(
        text=" ".join(s.text for s in segments),
        language="fr",  # dominant language
        duration_s=65.0,
        segments=segments,
    )


@pytest.fixture
def sample_transcript_empty():
    """An empty transcript (no segments) for edge case testing."""
    return Transcript(
        text="",
        language="fr",
        duration_s=0.0,
        segments=(),
    )


# ─── DecisionLog fixture ─────────────────────────────────────────────────────

@pytest.fixture
def sample_decision_log():
    """
    A fully-populated DecisionLog matching the content of sample_transcript_fr.
    Suitable for rendering, serialization, and export tests.
    """
    return DecisionLog(
        decisions=(
            Decision(
                id="D1",
                summary="Launch date set to May 15",
                timestamp_s=42.0,
                speaker="Pierre",
                confirmed_by=("Sophie",),
                quote="On part sur le 15 mai pour le lancement, c'est décidé.",
                confidence="high",
                language="fr",
            ),
        ),
        commitments=(
            Commitment(
                id="C1",
                owner="Sophie",
                action="Review the deployment checklist",
                deadline=CommitmentDeadline(
                    raw="vendredi prochain",
                    resolved_date=date(2026, 4, 17),
                    is_explicit=False,
                ),
                timestamp_s=82.0,
                quote="Je vais revoir la checklist avant vendredi prochain.",
                confidence="high",
                language="fr",
            ),
        ),
        rejected=(),
        open_questions=(),
        metadata=ExtractionMetadata(
            model="mistral-large-latest",
            prompt_version="v1.2.0",
            meeting_date=date(2026, 4, 9),
            extracted_at="2026-04-09T10:30:00Z",
            input_tokens=512,
            output_tokens=128,
        ),
    )


@pytest.fixture
def sample_decision_log_empty():
    """An empty DecisionLog for edge case testing."""
    return DecisionLog(
        decisions=(),
        commitments=(),
        rejected=(),
        open_questions=(),
        metadata=ExtractionMetadata(
            model="mistral-large-latest",
            prompt_version="v1.2.0",
            meeting_date=date(2026, 4, 9),
            extracted_at="2026-04-09T10:30:00Z",
            input_tokens=0,
            output_tokens=0,
        ),
    )


@pytest.fixture
def sample_decision_log_full():
    """A DecisionLog with all four item types populated."""
    return DecisionLog(
        decisions=(
            Decision(
                id="D1", summary="Launch on May 15", timestamp_s=42.0,
                speaker="Pierre", confirmed_by=("Sophie",),
                quote="On lance le 15 mai.", confidence="high", language="fr"
            ),
            Decision(
                id="D2", summary="Budget approved at €50k", timestamp_s=240.0,
                speaker="Sophie", confirmed_by=(),
                quote="Le budget est approuvé à 50k.", confidence="medium", language="fr"
            ),
        ),
        commitments=(
            Commitment(
                id="C1", owner="Sophie", action="Review deployment checklist",
                deadline=CommitmentDeadline(
                    raw="vendredi prochain", resolved_date=date(2026, 4, 17), is_explicit=False
                ),
                timestamp_s=82.0, quote="Je vais revoir la checklist.",
                confidence="high", language="fr"
            ),
            Commitment(
                id="C2", owner="Marc", action="Send Q2 report to board",
                deadline=CommitmentDeadline(
                    raw="2026-04-15", resolved_date=date(2026, 4, 15), is_explicit=True
                ),
                timestamp_s=360.0, quote="Je vais envoyer le rapport avant le 15.",
                confidence="high", language="fr"
            ),
        ),
        rejected=(
            Rejection(
                id="R1",
                summary="March soft launch rejected due to team capacity",
                timestamp_s=600.0,
                quote="Non, on ne peut pas faire ça en mars.",
                confidence="high",
                language="fr"
            ),
        ),
        open_questions=(
            OpenQuestion(
                id="Q1",
                question="Who owns the database schema migration?",
                asked_by="Pierre",
                timestamp_s=1200.0,
                quote="Qui s'occupe de la migration de la base ?",
                language="fr"
            ),
        ),
        metadata=ExtractionMetadata(
            model="mistral-large-latest",
            prompt_version="v1.2.0",
            meeting_date=date(2026, 4, 9),
            extracted_at="2026-04-09T10:30:00Z",
            input_tokens=1024,
            output_tokens=256,
        ),
    )


# ─── Mock API clients ────────────────────────────────────────────────────────

@pytest.fixture
def mock_mistral_client():
    """A MagicMock configured to mimic the MistralClient interface."""
    client = MagicMock()
    # Default: chat returns empty extraction
    import json
    client.chat.complete.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "decisions": [], "commitments": [], "rejected": [], "open_questions": []
        })))]
    )
    # Default: transcription returns empty
    client.audio.transcriptions.create.return_value = MagicMock(
        text="",
        language="fr",
        duration=0.0,
        segments=[],
    )
    return client


@pytest.fixture
def mock_voxtral_response_factory():
    """
    Factory fixture for building mock Voxtral API responses.

    Usage:
        response = mock_voxtral_response_factory(
            segments=[
                {"id": 0, "start": 0.0, "end": 5.0, "text": "Bonjour.",
                 "avg_logprob": -0.1, "no_speech_prob": 0.02},
            ],
            language="fr",
            duration=60.0,
        )
    """
    def factory(segments, language="fr", duration=600.0):
        mock = MagicMock()
        mock.text = " ".join(s.get("text", "") for s in segments)
        mock.language = language
        mock.duration = duration
        mock.segments = [
            MagicMock(
                id=s.get("id", i),
                start=s.get("start", 0.0),
                end=s.get("end", 5.0),
                text=s.get("text", ""),
                avg_logprob=s.get("avg_logprob", -0.1),
                no_speech_prob=s.get("no_speech_prob", 0.02),
            )
            for i, s in enumerate(segments)
        ]
        return mock
    return factory


# ─── Temp directories ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_cache_dir(tmp_path):
    """A fresh temporary directory for cache testing."""
    d = tmp_path / "parler_cache"
    d.mkdir()
    return d


@pytest.fixture
def tmp_output_dir(tmp_path):
    """A fresh temporary directory for output file testing."""
    d = tmp_path / "parler_output"
    d.mkdir()
    return d


# ─── Minimal config fixture ──────────────────────────────────────────────────

@pytest.fixture
def parler_config(tmp_cache_dir, tmp_output_dir):
    """
    A minimal ParlerConfig suitable for unit and integration tests.
    Uses a dummy API key (tests must mock the HTTP layer separately).
    """
    from parler.config import ParlerConfig, TranscriptionConfig, ChunkingConfig
    from parler.config import AttributionConfig, ExtractionConfig, CacheConfig
    from parler.config import OutputConfig, CostConfig

    return ParlerConfig(
        api_key="test-key-not-real",
        transcription=TranscriptionConfig(
            model="voxtral-v1-5",
            languages=["fr"],
            timeout_s=30,
            max_retries=1,
        ),
        chunking=ChunkingConfig(
            max_chunk_s=600,
            overlap_s=30,
            silence_threshold_db=-40,
            prefer_silence_splits=True,
        ),
        attribution=AttributionConfig(
            enabled=True,
            confidence_threshold=0.70,
            model="mistral-large-latest",
        ),
        extraction=ExtractionConfig(
            model="mistral-large-latest",
            temperature=0.0,
            max_tokens=4096,
            prompt_version="v1.2.0",
            multi_pass_threshold=25000,
        ),
        cache=CacheConfig(
            enabled=True,
            directory=tmp_cache_dir,
            max_size_gb=1.0,
            ttl_days=30,
        ),
        output=OutputConfig(
            format="markdown",
            output_path=tmp_output_dir / "report.md",
            anonymize_speakers=False,
        ),
        cost=CostConfig(
            max_usd=5.0,
            confirm_above_usd=1.0,
        ),
        participants=[],
        meeting_date=date(2026, 4, 9),
    )
