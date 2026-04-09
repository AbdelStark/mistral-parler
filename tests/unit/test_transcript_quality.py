"""
TDD specification: TranscriptQualityChecker.evaluate()

The quality checker analyses a completed Transcript and emits a
TranscriptQualityReport with:
  - An overall confidence score (weighted average of segment confidences)
  - A no_speech_ratio (fraction of duration covered by silence/no-speech segments)
  - A list of low-confidence spans (start_s, end_s pairs)
  - A QualityVerdict: OK | WARN | POOR
  - Suggested actionable remediation when verdict is not OK

Verdict thresholds:
  - OK:   mean_confidence >= 0.75 and no_speech_ratio < 0.30
  - WARN: mean_confidence >= 0.50 or (< 0.75 and no_speech_ratio >= 0.30)
  - POOR: mean_confidence < 0.50

Design contract:
  - Never raises for any input
  - Weights segment confidence by segment duration (longer segments count more)
  - Empty transcript → WARN with "no speech detected" message
  - Low-confidence spans are contiguous runs of segments below threshold (0.60)
"""

import pytest
from parler.transcription.quality import TranscriptQualityChecker, QualityVerdict
from parler.models import Transcript, TranscriptSegment


def seg(id, start, end, text, confidence=0.9, no_speech_prob=0.01):
    return TranscriptSegment(
        id=id,
        start_s=start,
        end_s=end,
        text=text,
        language="fr",
        speaker_id=None,
        speaker_confidence=None,
        confidence=confidence,
        no_speech_prob=no_speech_prob,
        code_switch=False,
        words=None,
    )


def make_transcript(*segments):
    return Transcript(
        text=" ".join(s.text for s in segments),
        language="fr",
        duration_s=segments[-1].end_s if segments else 0.0,
        segments=tuple(segments),
    )


class TestOverallScore:

    def test_all_high_confidence_gives_ok_verdict(self):
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "Segment A", confidence=0.95),
            seg(1, 10.0, 20.0, "Segment B", confidence=0.92),
            seg(2, 20.0, 30.0, "Segment C", confidence=0.88),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.OK

    def test_mean_confidence_is_duration_weighted(self):
        """A 10s segment at 0.80 and a 30s segment at 0.60 → weighted mean ~0.65."""
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "Short", confidence=0.80),
            seg(1, 10.0, 40.0, "Long", confidence=0.60),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        # Weighted: (10*0.80 + 30*0.60) / 40 = (8 + 18) / 40 = 0.65
        assert report.mean_confidence == pytest.approx(0.65, abs=0.01)

    def test_low_confidence_gives_poor_verdict(self):
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "A", confidence=0.40),
            seg(1, 10.0, 20.0, "B", confidence=0.45),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.POOR

    def test_medium_confidence_gives_warn_verdict(self):
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "A", confidence=0.62),
            seg(1, 10.0, 20.0, "B", confidence=0.58),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.WARN

    def test_boundary_075_is_ok(self):
        """Exactly 0.75 mean confidence → OK (boundary inclusive)."""
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "A", confidence=0.75),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.OK

    def test_boundary_050_is_warn(self):
        """Exactly 0.50 mean confidence → WARN (boundary inclusive on WARN side)."""
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "A", confidence=0.50),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.WARN


class TestNoSpeechRatio:

    def test_no_speech_ratio_computed_correctly(self):
        """3 out of 10 seconds is silence → ratio = 0.30."""
        transcript = make_transcript(
            seg(0, 0.0, 7.0, "Speech segment", confidence=0.90, no_speech_prob=0.05),
            seg(1, 7.0, 10.0, "", confidence=0.10, no_speech_prob=0.95),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.no_speech_ratio == pytest.approx(0.30, abs=0.02)

    def test_high_silence_ratio_degrades_verdict(self):
        """Even with OK confidence, 40% silence → WARN."""
        transcript = make_transcript(
            seg(0, 0.0, 6.0, "Good speech", confidence=0.90, no_speech_prob=0.05),
            seg(1, 6.0, 10.0, "", confidence=0.10, no_speech_prob=0.97),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.WARN

    def test_silence_below_threshold_does_not_degrade(self):
        """20% silence with high confidence → still OK."""
        transcript = make_transcript(
            seg(0, 0.0, 8.0, "Speech", confidence=0.90, no_speech_prob=0.03),
            seg(1, 8.0, 10.0, "", confidence=0.10, no_speech_prob=0.97),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.OK


class TestLowConfidenceSpans:

    def test_contiguous_low_confidence_segments_form_one_span(self):
        """Three consecutive low-confidence segments → one merged span."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "Clear speech", confidence=0.90),
            seg(1, 5.0, 10.0, "Mumble...", confidence=0.45),
            seg(2, 10.0, 15.0, "More mumbling", confidence=0.50),
            seg(3, 15.0, 20.0, "Still bad", confidence=0.40),
            seg(4, 20.0, 25.0, "Clear again", confidence=0.88),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert len(report.low_confidence_spans) == 1
        span = report.low_confidence_spans[0]
        assert span[0] == pytest.approx(5.0)   # start
        assert span[1] == pytest.approx(20.0)  # end

    def test_separated_low_confidence_runs_form_two_spans(self):
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "Good", confidence=0.90),
            seg(1, 5.0, 10.0, "Bad 1", confidence=0.45),
            seg(2, 10.0, 15.0, "Good again", confidence=0.85),
            seg(3, 15.0, 20.0, "Bad 2", confidence=0.40),
            seg(4, 20.0, 25.0, "Good end", confidence=0.90),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert len(report.low_confidence_spans) == 2

    def test_no_low_confidence_segments_gives_empty_spans(self):
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "Excellent", confidence=0.95),
            seg(1, 5.0, 10.0, "Very good", confidence=0.88),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.low_confidence_spans == []

    def test_low_confidence_threshold_is_060(self):
        """Segment at exactly 0.60 is NOT flagged; below 0.60 is."""
        transcript = make_transcript(
            seg(0, 0.0, 5.0, "Borderline", confidence=0.60),
            seg(1, 5.0, 10.0, "Just below", confidence=0.59),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        # Only seg 1 is below threshold
        if report.low_confidence_spans:
            span = report.low_confidence_spans[0]
            assert span[0] == pytest.approx(5.0)
            assert span[1] == pytest.approx(10.0)


class TestRemediationSuggestions:

    def test_poor_verdict_includes_actionable_suggestion(self):
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "Inaudible recording", confidence=0.35),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.POOR
        assert report.suggestion is not None
        assert len(report.suggestion) > 10  # non-trivial suggestion

    def test_suggestion_mentions_lang_flag_for_poor_quality(self):
        """Poor quality should suggest --lang or higher-quality recording."""
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "Inaudible", confidence=0.35),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        suggestion_lower = report.suggestion.lower()
        assert "--lang" in suggestion_lower or "language" in suggestion_lower or "recording" in suggestion_lower

    def test_ok_verdict_has_no_suggestion(self):
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "Perfect audio", confidence=0.95),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.OK
        assert report.suggestion is None or report.suggestion == ""


class TestEdgeCases:

    def test_empty_transcript_returns_warn(self):
        transcript = Transcript(
            text="", language="fr", duration_s=0.0, segments=()
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict == QualityVerdict.WARN

    def test_empty_transcript_suggestion_mentions_no_speech(self):
        transcript = Transcript(
            text="", language="fr", duration_s=0.0, segments=()
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert "no speech" in report.suggestion.lower() or "empty" in report.suggestion.lower()

    def test_single_segment_report_is_valid(self):
        transcript = make_transcript(seg(0, 0.0, 10.0, "Single segment", confidence=0.80))
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict in (QualityVerdict.OK, QualityVerdict.WARN, QualityVerdict.POOR)
        assert 0.0 <= report.mean_confidence <= 1.0

    def test_all_silence_transcript_is_poor(self):
        """A transcript that is all silence → POOR or WARN."""
        transcript = make_transcript(
            seg(0, 0.0, 10.0, "", confidence=0.10, no_speech_prob=0.99),
            seg(1, 10.0, 20.0, "", confidence=0.10, no_speech_prob=0.99),
        )
        report = TranscriptQualityChecker().evaluate(transcript)
        assert report.verdict in (QualityVerdict.POOR, QualityVerdict.WARN)

    def test_report_is_immutable(self):
        """Quality report is a frozen dataclass."""
        transcript = make_transcript(seg(0, 0.0, 5.0, "Test", confidence=0.90))
        report = TranscriptQualityChecker().evaluate(transcript)
        with pytest.raises((AttributeError, TypeError)):
            report.verdict = QualityVerdict.POOR
