"""Transcript quality evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..models import Transcript

_LOW_CONFIDENCE_THRESHOLD = 0.60
_NO_SPEECH_THRESHOLD = 0.90


class QualityVerdict(StrEnum):
    OK = "OK"
    WARN = "WARN"
    POOR = "POOR"


@dataclass(frozen=True)
class TranscriptQualityReport:
    mean_confidence: float
    no_speech_ratio: float
    low_confidence_spans: list[tuple[float, float]]
    verdict: QualityVerdict
    suggestion: str | None = None


class TranscriptQualityChecker:
    """Evaluate transcript confidence and silence coverage without raising."""

    def evaluate(self, transcript: Transcript) -> TranscriptQualityReport:
        segments = transcript.segments
        if not segments:
            return TranscriptQualityReport(
                mean_confidence=0.0,
                no_speech_ratio=1.0,
                low_confidence_spans=[],
                verdict=QualityVerdict.WARN,
                suggestion="No speech detected. Check the recording or try specifying --lang.",
            )

        total_duration = max(transcript.duration_s, segments[-1].end_s - segments[0].start_s, 0.0)
        if total_duration <= 0:
            total_duration = sum(max(segment.end_s - segment.start_s, 0.0) for segment in segments)

        weighted_confidence = 0.0
        speech_duration = 0.0
        silence_duration = 0.0
        low_confidence_spans: list[tuple[float, float]] = []
        current_span: list[float] | None = None

        for segment in segments:
            duration = max(segment.end_s - segment.start_s, 0.0)

            if segment.no_speech_prob >= _NO_SPEECH_THRESHOLD:
                silence_duration += duration
            else:
                weighted_confidence += duration * segment.confidence
                speech_duration += duration

            if (
                segment.no_speech_prob < _NO_SPEECH_THRESHOLD
                and segment.confidence < _LOW_CONFIDENCE_THRESHOLD
            ):
                if current_span is None:
                    current_span = [segment.start_s, segment.end_s]
                else:
                    current_span[1] = max(current_span[1], segment.end_s)
            elif current_span is not None:
                low_confidence_spans.append((current_span[0], current_span[1]))
                current_span = None

        if current_span is not None:
            low_confidence_spans.append((current_span[0], current_span[1]))

        duration_denominator = total_duration if total_duration > 0 else 1.0
        confidence_denominator = speech_duration if speech_duration > 0 else 1.0
        mean_confidence = weighted_confidence / confidence_denominator
        no_speech_ratio = silence_duration / duration_denominator

        if mean_confidence < 0.50:
            verdict = QualityVerdict.POOR
            suggestion = "Use a higher-quality recording or specify --lang for better results."
        elif mean_confidence >= 0.75 and no_speech_ratio < 0.30:
            verdict = QualityVerdict.OK
            suggestion = None
        else:
            verdict = QualityVerdict.WARN
            if no_speech_ratio >= 0.30:
                suggestion = (
                    "Large silent spans detected. Check the recording and consider using --lang."
                )
            elif low_confidence_spans:
                suggestion = "Some regions were low-confidence. Consider a cleaner recording or explicit language hints."
            else:
                suggestion = None

        return TranscriptQualityReport(
            mean_confidence=mean_confidence,
            no_speech_ratio=no_speech_ratio,
            low_confidence_spans=low_confidence_spans,
            verdict=verdict,
            suggestion=suggestion,
        )
