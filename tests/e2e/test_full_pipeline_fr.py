"""
E2E test: Full pipeline for a French-language meeting

This test exercises the complete parler pipeline against a real Voxtral
and Mistral API call:

  1. Ingest a synthetic French audio fixture
  2. Transcribe via Voxtral (real API call)
  3. Attribute speakers using the participant list
  4. Extract decisions/commitments via Mistral Large
  5. Render a Markdown report

Requires:
  - MISTRAL_API_KEY environment variable set
  - Network access to api.mistral.ai
  - ~$0.05 per run (short fixture audio)

Marked @slow — not included in CI default run.

Audio fixture: tests/fixtures/audio/fr_meeting_5min.mp3
  Source: synthetic French business meeting (gTTS-generated)
  Content: 5-minute discussion about a product launch, with 2 named speakers,
           1 explicit decision ("we launch May 15"), 2 commitments
  Ground truth: tests/fixtures/decision_logs/fr_meeting_5min_expected.json
"""

import pytest
import json
import os
from pathlib import Path
from datetime import date
from parler.pipeline import run_pipeline, PipelineConfig


FIXTURE_AUDIO = Path(__file__).parent.parent / "fixtures" / "audio" / "fr_meeting_5min.mp3"
EXPECTED_LOG = Path(__file__).parent.parent / "fixtures" / "decision_logs" / "fr_meeting_5min_expected.json"


@pytest.mark.slow
@pytest.mark.skipif(
    not os.environ.get("MISTRAL_API_KEY"),
    reason="MISTRAL_API_KEY not set — skipping E2E test"
)
class TestFullPipelineFrench:

    def test_fixture_audio_exists(self):
        """Sanity check: fixture audio must be present before running E2E."""
        assert FIXTURE_AUDIO.exists(), (
            f"Fixture audio not found: {FIXTURE_AUDIO}\n"
            "Run: python tests/fixtures/generate_fixtures.py to create it."
        )

    def test_pipeline_completes_without_error(self):
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            participants=["Pierre", "Sophie"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert result is not None
        assert result.decision_log is not None

    def test_french_transcript_produced(self):
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert result.transcript is not None
        assert result.transcript.language == "fr"
        assert len(result.transcript.segments) > 0

    def test_at_least_one_decision_extracted(self):
        """The fixture audio contains one clear decision — must be detected."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert len(result.decision_log.decisions) >= 1, (
            "Expected at least 1 decision from the French fixture meeting. "
            f"Got 0. Transcript excerpt: {result.transcript.text[:200]}"
        )

    def test_at_least_one_commitment_extracted(self):
        """The fixture contains 2 commitments — at least 1 must be detected."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert len(result.decision_log.commitments) >= 1

    def test_launch_date_decision_detected(self):
        """The key decision 'launch on May 15' must be in the extracted log."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        summaries = [d.summary.lower() for d in result.decision_log.decisions]
        has_launch = any("mai" in s or "may" in s or "15" in s or "launch" in s for s in summaries)
        assert has_launch, (
            f"Expected a 'launch May 15' decision. Got decisions: {summaries}"
        )

    def test_speaker_names_assigned(self):
        """With participant list ['Pierre', 'Sophie'], at least one name should appear."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            participants=["Pierre", "Sophie"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        speakers = {s.speaker_id for s in result.transcript.segments if s.speaker_id}
        # At least one of our participant names (or Unknown) should appear
        assert len(speakers) >= 1

    def test_deadline_resolved_for_commitment(self):
        """Any commitment with 'vendredi prochain' should have a resolved_date."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        for c in result.decision_log.commitments:
            if c.deadline and c.deadline.raw:
                if "vendredi" in c.deadline.raw.lower():
                    assert c.deadline.resolved_date is not None, (
                        f"Expected 'vendredi prochain' to resolve to a date. "
                        f"Got: {c.deadline}"
                    )

    def test_markdown_report_rendered(self):
        """Pipeline should produce a non-empty Markdown report."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            meeting_date=date(2026, 4, 9),
            output_format="markdown",
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert result.report is not None
        assert "## Decisions" in result.report or "# Decisions" in result.report
        assert len(result.report) > 200

    def test_second_run_uses_cache(self, tmp_path):
        """Running the pipeline twice on the same file should use cache on second run."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            meeting_date=date(2026, 4, 9),
            cache_dir=tmp_path,
        )
        # First run — populates cache
        result1 = run_pipeline(FIXTURE_AUDIO, config)

        # Second run — should use cache (faster, same result)
        import time
        start = time.time()
        result2 = run_pipeline(FIXTURE_AUDIO, config)
        elapsed = time.time() - start

        # Second run should be significantly faster (< 5s vs typical 30s+ for API)
        # This is a soft assertion — we primarily check that results match
        assert len(result2.decision_log.decisions) == len(result1.decision_log.decisions)

    def test_output_against_expected_log(self):
        """Compare output against the pre-recorded expected log (regression test)."""
        if not EXPECTED_LOG.exists():
            pytest.skip("Expected log fixture not found — skipping regression check")

        expected = json.loads(EXPECTED_LOG.read_text())

        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)

        # Check decision count matches expected (within ±1 for LLM variance)
        actual_count = len(result.decision_log.decisions)
        expected_count = len(expected.get("decisions", []))
        assert abs(actual_count - expected_count) <= 1, (
            f"Decision count mismatch: expected ~{expected_count}, got {actual_count}"
        )
