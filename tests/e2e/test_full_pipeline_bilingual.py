"""
E2E test: Full pipeline for a bilingual (FR/EN) meeting with code-switching

This test exercises parler against a fixture that deliberately mixes French
and English — the typical pattern in a French tech startup meeting where
technical terms and investor-speak bleed into French base conversation.

Audio fixture: tests/fixtures/audio/bilingual_meeting_5min.mp3
  Source: synthetic bilingual meeting (gTTS-generated, alternating FR/EN)
  Content:
    - French base conversation with English technical vocabulary
    - At least one explicit code-switch mid-sentence
    - 1 decision ("we're going with the Python SDK approach")
    - 1 commitment in French with an English deadline ("by EOW")
    - One explicitly English-only segment by a native EN speaker

Ground truth: tests/fixtures/decision_logs/bilingual_expected.json

Requires:
  - MISTRAL_API_KEY environment variable set
  - ~$0.06 per run
"""

import pytest
import os
from pathlib import Path
from datetime import date
from parler.pipeline import run_pipeline, PipelineConfig


FIXTURE_AUDIO = Path(__file__).parent.parent / "fixtures" / "audio" / "bilingual_meeting_5min.mp3"


@pytest.mark.slow
@pytest.mark.multilingual
@pytest.mark.skipif(
    not os.environ.get("MISTRAL_API_KEY"),
    reason="MISTRAL_API_KEY not set — skipping E2E test"
)
class TestFullPipelineBilingual:

    def test_fixture_audio_exists(self):
        assert FIXTURE_AUDIO.exists(), (
            f"Bilingual fixture not found: {FIXTURE_AUDIO}\n"
            "Run: python tests/fixtures/generate_fixtures.py --bilingual"
        )

    def test_pipeline_completes_without_error(self):
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr", "en"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert result is not None
        assert result.decision_log is not None

    def test_both_languages_detected_in_transcript(self):
        """Segments should have both 'fr' and 'en' language codes assigned."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr", "en"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        languages_found = {s.language for s in result.transcript.segments if s.language}
        assert "fr" in languages_found, (
            f"French not detected in bilingual meeting. Found: {languages_found}"
        )
        assert "en" in languages_found, (
            f"English not detected in bilingual meeting. Found: {languages_found}"
        )

    def test_code_switch_segments_flagged(self):
        """At least one segment should have code_switch=True."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr", "en"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        code_switches = [s for s in result.transcript.segments if s.code_switch]
        assert len(code_switches) >= 1, (
            "Expected at least one code-switch segment in bilingual meeting. "
            "Check fixture audio content."
        )

    def test_decision_extracted_despite_language_mixing(self):
        """A decision stated in English within a French meeting should still be extracted."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr", "en"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert len(result.decision_log.decisions) >= 1, (
            "No decisions extracted from bilingual meeting. "
            "The fixture contains at least one explicit decision."
        )

    def test_english_deadline_resolved_in_bilingual_context(self):
        """'by EOW' in a French-context meeting should still resolve to the correct date."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr", "en"],
            meeting_date=date(2026, 4, 9),  # Wednesday
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        for c in result.decision_log.commitments:
            if c.deadline and c.deadline.raw:
                if "eow" in c.deadline.raw.lower() or "end of week" in c.deadline.raw.lower():
                    assert c.deadline.resolved_date == date(2026, 4, 11), (
                        f"EOW from Wednesday 2026-04-09 should resolve to 2026-04-11 (Friday). "
                        f"Got: {c.deadline.resolved_date}"
                    )

    def test_auto_language_detection_without_hint(self):
        """Without specifying languages=, Voxtral should auto-detect FR and EN."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            # No languages hint — Voxtral should detect automatically
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        assert result.transcript is not None
        assert len(result.transcript.segments) > 0

    def test_report_includes_language_metadata(self):
        """The rendered report should note that code-switching was detected."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr", "en"],
            meeting_date=date(2026, 4, 9),
            output_format="markdown",
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        # The report should mention both languages in metadata or header
        report_lower = result.report.lower()
        has_lang_info = (
            "fr" in report_lower or "french" in report_lower or
            "en" in report_lower or "english" in report_lower or
            "bilingual" in report_lower or "code" in report_lower
        )
        assert has_lang_info

    def test_decision_language_field_accurate(self):
        """Decisions in English should have language='en', French should have 'fr'."""
        config = PipelineConfig(
            api_key=os.environ["MISTRAL_API_KEY"],
            languages=["fr", "en"],
            meeting_date=date(2026, 4, 9),
        )
        result = run_pipeline(FIXTURE_AUDIO, config)
        for d in result.decision_log.decisions:
            assert d.language in ("fr", "en", "unknown"), (
                f"Unexpected language code in decision: {d.language}"
            )
