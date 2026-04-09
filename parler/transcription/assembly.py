"""Chunk assembly helpers for Voxtral transcript responses."""

from __future__ import annotations

from collections.abc import Iterable

from ..models import RawVoxtralChunkResponse, Transcript, TranscriptSegment
from ..util.hashing import stable_fingerprint


def _normalized_text(text: str) -> str:
    return " ".join(text.lower().split())


def _is_silence(segment: TranscriptSegment) -> bool:
    return segment.no_speech_prob >= 0.9 or not segment.text.strip()


def _segments_overlap(left: TranscriptSegment, right: TranscriptSegment) -> bool:
    return left.start_s <= right.end_s and right.start_s <= left.end_s


def _segments_are_duplicate(left: TranscriptSegment, right: TranscriptSegment) -> bool:
    if _is_silence(left) and _is_silence(right):
        return _segments_overlap(left, right)
    return (
        bool(_normalized_text(left.text))
        and _normalized_text(left.text) == _normalized_text(right.text)
        and _segments_overlap(left, right)
    )


def _choose_segment(left: TranscriptSegment, right: TranscriptSegment) -> TranscriptSegment:
    if _is_silence(left) and _is_silence(right):
        return left if left.no_speech_prob >= right.no_speech_prob else right
    return left if left.confidence >= right.confidence else right


def _reindex_segments(segments: Iterable[TranscriptSegment]) -> tuple[TranscriptSegment, ...]:
    return tuple(
        TranscriptSegment(
            id=index,
            start_s=segment.start_s,
            end_s=segment.end_s,
            text=segment.text,
            language=segment.language,
            speaker_id=segment.speaker_id,
            speaker_confidence=segment.speaker_confidence,
            confidence=segment.confidence,
            no_speech_prob=segment.no_speech_prob,
            code_switch=segment.code_switch,
            words=segment.words,
        )
        for index, segment in enumerate(segments)
    )


def assemble_chunks(
    chunk_responses: list[RawVoxtralChunkResponse],
    *,
    content_hash: str = "",
    model: str = "",
) -> Transcript:
    """Merge chunk responses into one canonical transcript."""

    if not chunk_responses:
        raise ValueError("assemble_chunks requires at least one chunk response")

    merged: list[TranscriptSegment] = []
    seen_languages: list[str] = []

    for chunk in chunk_responses:
        if chunk.language and chunk.language not in seen_languages:
            seen_languages.append(chunk.language)

        for segment in chunk.segments:
            if segment.language and segment.language not in seen_languages:
                seen_languages.append(segment.language)

            if merged and _segments_are_duplicate(merged[-1], segment):
                merged[-1] = _choose_segment(merged[-1], segment)
                continue
            merged.append(segment)

    merged.sort(key=lambda segment: (segment.start_s, segment.end_s, segment.id))
    reindexed = _reindex_segments(merged)
    transcript_text = " ".join(segment.text for segment in reindexed if segment.text.strip())
    primary_language = seen_languages[0] if seen_languages else chunk_responses[0].language
    duration = max(
        (chunk.duration for chunk in chunk_responses),
        default=reindexed[-1].end_s if reindexed else 0.0,
    )
    effective_hash = content_hash or stable_fingerprint(
        model,
        transcript_text,
        tuple((segment.start_s, segment.end_s, segment.text) for segment in reindexed),
    )

    return Transcript(
        text=transcript_text,
        language=primary_language,
        duration_s=duration,
        segments=reindexed,
        detected_languages=tuple(seen_languages),
        model=model,
        content_hash=effective_hash,
    )
