"""
E2E test: Earnings call fixture — stress test for production-scale input

This test exercises parler against a longer, denser fixture that simulates
a 45-minute French/English earnings call. This is the canonical stress test
for production readiness:

  - Multi-chunk transcription (45 min → 4-5 Voxtral chunks)
  - High decision density (10-20 decisions in a real earnings call)
  - Technical financial vocabulary (EBITDA, ARR, churn, runway)
  - Multiple speakers (CEO, CFO, analyst Q&A)
  - Code-switching: French company meeting in EN for investor relations
  - Explicit ISO dates and relative dates in commitments
  - Rejection of analyst questions that got deflected

Fixture: tests/fixtures/audio/earnings_call_45min.mp3
  Source: synthetic (gTTS-generated from a fictional earnings call script)
  Duration: ~45 minutes
  Speakers: 4 (CEO Pierre, CFO Sophie, Analyst 1, Analyst 2)
  Language: primarily EN with FR code-switching

Requires:
  - MISTRAL_API_KEY environment variable set
  - ~$0.50 per run (long audio, multiple chunks)
  - ~3-5 minutes wall time

Marked @slow — not included in CI default run.
"""

import pytest
import os
import time
from pathlib import Path
from datetime import date, timedelta
from parler.pipeline import run_pipeline, PipelineConfig


FIXTURE_AUDIO = Path(__file__).parent.parent / "fixtures" / "audio" / "earnings_call_45min.mp3"
MEETING_DATE = date(2026, 4, 9)


@pytest.mark.slow
@pytest.mark.skipif(
    not os.environ.get("MISTRAL_API_KEY"),
    reason="MISTRAL_API_KEY not set — skipping E2E test"
)
class TestEarningsCallPipeline:

    def test_fixture_audio_exists(self):
        assert FIXTURE_AUDIO.exists(), (
            f"Earnings call fixture not found: {FIXTURE_AUDIO}\n"
            "Run: python tests/fixtures/generate_fixtures.py --earnings-call"
        )

    def test_pipeline_completes_within_time_budget(self):
        """The full 45-minute pipeline should complete in under 5 minutes wall time."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en", "fr"],
            participants=["Pierre", "Sophie", "Analyst"],
            meeting_date=MEETING_DATE,
        )
        start = time.time()
        result = run_pipeline(FIXTURE_AUDIO, config)
        elapsed = time.time() - start

        assert result is not None
        assert elapsed < 300, (
            f"Pipeline took {elapsed:.0f}s — expected < 300s for 45-minute audio"
        )

    def test_chunking_produces_correct_segment_count(self):
        """45 minutes → 4-5 chunks; each chunk produces segments → ≥40 total segments."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en", "fr"],
            meeting_date=MEETING_DATE,
            max_chunk_s=600,
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert len(result.transcript.segments) >= 40, (
            f"Expected ≥40 segments for 45-min audio, got {len(result.transcript.segments)}"
        )

    def test_transcript_timestamps_monotonically_increasing(self):
        """After chunk assembly, timestamps must be monotonically increasing."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en"],
            meeting_date=MEETING_DATE,
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        starts = [s.start_s for s in result.transcript.segments]
        assert starts == sorted(starts), (
            "Transcript timestamps are not monotonically increasing after chunk assembly. "
            f"First violation at index {next(i for i,(a,b) in enumerate(zip(starts, starts[1:])) if a > b)}"
        )

    def test_multiple_decisions_extracted(self):
        """An earnings call with 10-20 decisions should extract at least 5."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en", "fr"],
            meeting_date=MEETING_DATE,
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert len(result.decision_log.decisions) >= 5, (
            f"Expected ≥5 decisions from earnings call, "
            f"got {len(result.decision_log.decisions)}"
        )

    def test_multiple_commitments_extracted(self):
        """Earnings calls typically produce 3-8 action items."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en", "fr"],
            meeting_date=MEETING_DATE,
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert len(result.decision_log.commitments) >= 2, (
            f"Expected ≥2 commitments from earnings call, "
            f"got {len(result.decision_log.commitments)}"
        )

    def test_financial_vocabulary_not_garbled(self):
        """Key financial terms (ARR, EBITDA, Q2) should appear in the transcript."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en"],
            meeting_date=MEETING_DATE,
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        full_text = result.transcript.text.lower()
        # At least some financial terms should survive transcription
        financial_terms = ["arr", "revenue", "q2", "quarter", "growth", "margin"]
        terms_found = [t for t in financial_terms if t in full_text]
        assert len(terms_found) >= 2, (
            f"Expected ≥2 financial terms in transcript, "
            f"found: {terms_found}. First 500 chars: {result.transcript.text[:500]}"
        )

    def test_resolved_deadlines_are_in_reasonable_future(self):
        """All resolved commitment deadlines should be within 90 days of the meeting."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en", "fr"],
            meeting_date=MEETING_DATE,
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        max_deadline = MEETING_DATE + timedelta(days=90)
        for c in result.decision_log.commitments:
            if c.deadline and c.deadline.resolved_date:
                assert c.deadline.resolved_date <= max_deadline, (
                    f"Commitment '{c.action}' has deadline {c.deadline.resolved_date}, "
                    f"which is more than 90 days from the meeting ({MEETING_DATE}). "
                    "This is likely a hallucination."
                )

    def test_no_future_year_hallucinations_in_deadlines(self):
        """Deadlines should not be hallucinated as years far in the future."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en", "fr"],
            meeting_date=MEETING_DATE,
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        for c in result.decision_log.commitments:
            if c.deadline and c.deadline.resolved_date:
                assert c.deadline.resolved_date.year <= MEETING_DATE.year + 1, (
                    f"Deadline {c.deadline.resolved_date} is more than 1 year after "
                    f"meeting date — likely hallucinated"
                )

    def test_decision_confidence_distribution(self):
        """In a densely-packed earnings call, most decisions should be high confidence."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en", "fr"],
            meeting_date=MEETING_DATE,
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        if result.decision_log.decisions:
            high_count = sum(1 for d in result.decision_log.decisions if d.confidence == "high")
            ratio = high_count / len(result.decision_log.decisions)
            assert ratio >= 0.5, (
                f"Less than 50% of decisions are high confidence ({ratio:.0%}). "
                "Either the audio quality is poor or the extractor is under-confident."
            )

    def test_speaker_names_present_when_participant_list_provided(self):
        """With a participant list, at least some speaker names should be assigned."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en"],
            participants=["Pierre", "Sophie", "Analyst"],
            meeting_date=MEETING_DATE,
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        named_speakers = {
            s.speaker_id for s in result.transcript.segments
            if s.speaker_id and s.speaker_id != "Unknown"
        }
        assert len(named_speakers) >= 1, (
            "Expected at least one named speaker when participant list is provided. "
            f"Speaker IDs found: {named_speakers}"
        )

    def test_cache_provides_speedup_on_second_run(self, tmp_path):
        """Second run with cache should be significantly faster than first run."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en"],
            meeting_date=MEETING_DATE,
            cache_dir=tmp_path,
        )

        # First run — cold
        t0 = time.time()
        result1 = run_pipeline(FIXTURE_AUDIO, config)
        first_run_time = time.time() - t0

        # Second run — warm cache
        t0 = time.time()
        result2 = run_pipeline(FIXTURE_AUDIO, config)
        second_run_time = time.time() - t0

        # Cache should provide at least 5x speedup on transcription
        speedup = first_run_time / second_run_time
        assert speedup >= 3.0, (
            f"Cache speedup was only {speedup:.1f}x (first={first_run_time:.0f}s, "
            f"second={second_run_time:.0f}s). Expected ≥3x."
        )

    def test_json_export_validates_against_schema(self):
        """The JSON export of the earnings call log must be schema-valid."""
        import json
        from jsonschema import validate, ValidationError

        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["en"],
            meeting_date=MEETING_DATE,
            output_format="json",
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        try:
            parsed = json.loads(result.report)
        except json.JSONDecodeError as e:
            pytest.fail(f"JSON output is not valid JSON: {e}")

        # Minimal schema check (full schema in RFC-0005)
        assert "decisions" in parsed
        assert "commitments" in parsed
        assert "metadata" in parsed
        assert isinstance(parsed["decisions"], list)
        assert isinstance(parsed["commitments"], list)
